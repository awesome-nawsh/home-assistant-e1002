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

from render import placeholder, render_screen
from schedule import Store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("e1002")

OPTIONS_PATH = os.environ.get("OPTIONS_PATH", "/data/options.json")
DATA_PATH = os.environ.get("DATA_PATH", "/data/screens.json")
STATIC = os.path.join(os.path.dirname(__file__), "static")

opts: dict[str, Any] = {"puppet_url": "http://0f1cc410-puppet:10000", "timezone": "Asia/Singapore", "width": 800, "height": 480}
if os.path.exists(OPTIONS_PATH):
    with open(OPTIONS_PATH) as f:
        opts.update(json.load(f))
W, H = int(opts["width"]), int(opts["height"])

store = Store(DATA_PATH, opts["timezone"])
app = FastAPI(title="E1002 Scheduler", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC), name="static")

_cache: dict[str, tuple[float, bytes]] = {}  # screen id -> (ts, png)
CACHE_TTL = 120


async def _render(screen: dict, force: bool = False) -> bytes:
    ts, png = _cache.get(screen["id"], (0, b""))
    if not force and time.time() - ts < CACHE_TTL:
        return png
    png = await render_screen(screen, opts["puppet_url"], W, H)
    _cache[screen["id"]] = (time.time(), png)
    return png


# ---------------- UI ----------------
@app.get("/")
async def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


@app.get("/api/config")
async def get_config():
    active, end = store.active_screen()
    secs, why = store.sleep_seconds()
    return {
        "default_interval_min": store.data["default_interval_min"],
        "fallback_screen": store.data.get("fallback_screen"),
        "screens": store.data["screens"],
        "devices": store.data["devices"],
        "status": {
            "now": store.now().isoformat(timespec="seconds"),
            "active_screen": active["id"] if active else None,
            "active_until": end.isoformat(timespec="minutes") if end else None,
            "next_sleep_s": secs,
            "reason": why,
        },
        "panel": {"width": W, "height": H},
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
        store.set_globals(body.get("default_interval_min"), body.get("fallback_screen", None))
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
async def device_image(device: str = Query("e1002")):
    screen, _ = store.active_screen()
    source = "scheduled"
    if screen is None:
        screen = store.fallback()
        source = "fallback"
    if screen is None:
        store.mark_shown(device, None)
        return Response(placeholder("Nothing scheduled", W, H), media_type="image/png")
    try:
        png = await _render(screen)
    except Exception as e:
        log.error("render %s failed: %s", screen["name"], e)
        png = placeholder(f"{screen['name']}: render failed", W, H)
    store.mark_shown(device, screen["id"])
    log.info("device %s -> %s (%s)", device, screen["name"], source)
    return Response(png, media_type="image/png", headers={"Cache-Control": "no-store"})


@app.get("/api/sleep")
async def device_sleep(device: str = Query("e1002")):
    secs, why = store.sleep_seconds()
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
