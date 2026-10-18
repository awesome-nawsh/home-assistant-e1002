"""E1002 Scheduler — HA add-on serving a web UI (Ingress) and a device API (port 8098)."""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from render import placeholder, render_screen, sleep_card
from schedule import Store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("e1002")

OPTIONS_PATH = os.environ.get("OPTIONS_PATH", "/data/options.json")
DATA_PATH = os.environ.get("DATA_PATH", "/data/screens.json")
STATIC = os.path.join(os.path.dirname(__file__), "static")

opts: dict[str, Any] = {
    "puppet_url": "http://0f1cc410-puppet:10000", "timezone": "Asia/Singapore", "width": 800, "height": 480,
    # battery model — rough defaults for the E1002's 2000 mAh pack; calibrate from real readings
    "battery_mah": 2000, "awake_mah_per_wake": 1.5, "draw_mah": 1.0, "sleep_ma": 0.12,
    "render_wait_ms": 3000,   # default settle time before screenshot; per-screen override in the UI
    "dither": "floyd",        # default dither: "floyd" (error diffusion) or "none" (nearest colour)
}
if os.path.exists(OPTIONS_PATH):
    with open(OPTIONS_PATH) as f:
        opts.update(json.load(f))
W, H = int(opts["width"]), int(opts["height"])

store = Store(DATA_PATH, opts["timezone"])
app = FastAPI(title="E1002 Scheduler", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC), name="static")

_cache: dict[str, tuple[float, bytes]] = {}  # screen id -> (ts, png)
CACHE_TTL = 120
_device_url: dict[str, Any] = {"port": None, "checked": 0.0}


async def device_base_url() -> dict:
    """Host port the Supervisor mapped for 8098/tcp, so the UI can show the exact device URL."""
    import httpx
    tok = os.environ.get("SUPERVISOR_TOKEN")
    if tok and time.time() - _device_url["checked"] > 300:
        _device_url["checked"] = time.time()
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.get("http://supervisor/addons/self/info", headers={"Authorization": f"Bearer {tok}"})
                net = (r.json().get("data") or {}).get("network") or {}
                _device_url["port"] = net.get("8098/tcp")
        except Exception as e:  # not fatal — UI just can't show the port
            log.warning("supervisor port lookup failed: %s", e)
    port = _device_url["port"] or 8098
    return {"port": port, "url": f"http://homeassistant.local:{port}"}


async def _render(screen: dict, force: bool = False, next_s: int = 0) -> bytes:
    ts, png = _cache.get(screen["id"], (0, b""))
    if not force and time.time() - ts < CACHE_TTL:
        return png
    png = await render_screen(screen, opts["puppet_url"], W, H, int(opts.get("render_wait_ms", 3000)), next_s,
                              str(opts.get("dither", "floyd")))
    _cache[screen["id"]] = (time.time(), png)
    return png


# ---------------- UI ----------------
@app.get("/")
async def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


@app.get("/api/config")
async def get_config(device: str = Query("e1002")):
    active = store.active_screens()
    secs, why = store.sleep_seconds(device)
    nxt, how = store.pick_next(device)
    boundary = store.next_boundary()
    return {
        "default_dwell_min": store.data["default_dwell_min"],
        "render_wait_ms": int(opts.get("render_wait_ms", 3000)),
        "dither": str(opts.get("dither", "floyd")),
        "fallback_screen": store.data.get("fallback_screen"),
        "night": store.data.get("night"),
        "screens": store.data["screens"],
        "devices": store.data["devices"],
        "status": {
            "now": store.now().isoformat(timespec="seconds"),
            "night": store.in_night(store.now()),
            "active_screens": [s["id"] for s in active],
            "next_screen": nxt["id"] if nxt else None,
            "next_how": how,
            "next_boundary": boundary.isoformat(timespec="minutes") if boundary else None,
            "next_sleep_s": secs,
            "reason": why,
        },
        "panel": {"width": W, "height": H},
        "device_url": await device_base_url(),
        "battery": store.battery_estimate(float(opts["battery_mah"]), float(opts["awake_mah_per_wake"]),
                                          float(opts["draw_mah"]), float(opts["sleep_ma"])),
    }


@app.post("/api/screens")
async def upsert_screen(screen: dict = Body(...)):
    try:
        return store.upsert_screen(screen)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/screens/{sid}")
async def delete_screen(sid: str):
    store.delete_screen(sid)
    _cache.pop(sid, None)
    return {"ok": True}


@app.post("/api/screens/order")
async def reorder(ids: list[str] = Body(...)):
    store.reorder(ids)
    return {"ok": True}


@app.post("/api/globals")
async def set_globals(body: dict = Body(...)):
    try:
        store.set_globals(body)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.get("/api/preview/{sid}")
async def preview(sid: str, force: bool = False):
    screen = next((s for s in store.data["screens"] if s["id"] == sid), None)
    if not screen:
        raise HTTPException(404, "no such screen")
    try:
        png = await _render(screen, force=force)
    except Exception as e:  # show the error on the thumbnail rather than a broken image
        log.warning("preview %s failed: %s", screen["name"], e)
        png = placeholder(f"Render failed: {str(e)[:60]}", W, H)
    return Response(png, media_type="image/png", headers={"Cache-Control": "no-store"})


# ---------------- Device API ----------------
@app.get("/api/image")
async def device_image(device: str = Query("e1002"), nav: str = Query("")):
    screen, how = store.pick_next(device, nav=nav if nav in ("next", "prev", "refresh") else "")
    if screen is None:
        # night, or idle with no fallback: show the sleep card (moon + next wake time) once;
        # on later wakes with the same next-wake time answer 204 so the panel isn't refreshed
        now = store.now()
        nxt = store.next_window_start(now)
        if nxt and store.in_night(nxt):          # window starts inside night → first shown at night end
            nxt = store.night_end(nxt)
        title = "Sleeping" if how == "night" else "Nothing scheduled"
        sub = f"Next screen {nxt:%a %H:%M}" if nxt else "No schedules set"
        key = f"sleep:{title}:{sub}"
        last = (store.data["devices"].get(device) or {}).get("last_screen", "unset")
        if last == key:
            log.info("device %s -> sleep card unchanged (%s), 204", device, how)
            return Response(status_code=204)
        store.mark_shown(device, key)
        log.info("device %s -> sleep card '%s / %s' (%s)", device, title, sub, how)
        return Response(sleep_card(title, sub, W, H), media_type="image/png", headers={"Cache-Control": "no-store"})
    try:
        png = await _render(screen, force=True, next_s=store.sleep_seconds(device)[0])
    except Exception as e:
        log.error("render %s failed: %s", screen["name"], e)
        png = placeholder(f"{screen['name']}: render failed", W, H)
    store.mark_shown(device, screen["id"])
    log.info("device %s -> %s (%s)", device, screen["name"], how)
    return Response(png, media_type="image/png", headers={"Cache-Control": "no-store"})


@app.get("/api/sleep")
async def device_sleep(device: str = Query("e1002")):
    secs, why = store.sleep_seconds(device)
    log.info("device %s sleep %ss (%s)", device, secs, why)
    return Response(str(secs), media_type="text/plain")


@app.post("/api/report")
async def device_report(request: Request, device: str = Query("e1002")):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    store.report(device, payload)
    return {"ok": True}


@app.get("/api/health")
async def health():
    return {"ok": True, "screens": len(store.data["screens"])}
