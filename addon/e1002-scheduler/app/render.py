"""Render a screen to a WxH PNG dithered to the Spectra-6 palette."""
from __future__ import annotations

import asyncio
import io
import logging
import os
import tempfile
from urllib.parse import quote

import httpx
from PIL import Image

log = logging.getLogger("render")

# Spectra 6 palette: black, white, red, green, blue, yellow
PALETTE = [0, 0, 0, 255, 255, 255, 255, 0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 0]
CHROMIUM = os.environ.get("CHROMIUM", "/usr/bin/chromium")


def _palette_image() -> Image.Image:
    p = Image.new("P", (1, 1))
    p.putpalette(PALETTE + [0] * (768 - len(PALETTE)))
    return p


def dither(png: bytes, w: int, h: int) -> bytes:
    img = Image.open(io.BytesIO(png)).convert("RGB")
    if img.size != (w, h):
        img = img.resize((w, h), Image.LANCZOS)
    q = img.quantize(palette=_palette_image(), dither=Image.Dither.FLOYDSTEINBERG)
    out = io.BytesIO()
    q.convert("RGB").save(out, format="PNG", optimize=True)
    return out.getvalue()


async def render_ha(puppet_url: str, path: str, w: int, h: int, timeout: float = 45.0) -> bytes:
    """HA dashboard path via the Puppet add-on. Puppet does the login; we do the dithering."""
    path = path.lstrip("/")
    sep = "&" if "?" in path else "?"
    url = f"{puppet_url.rstrip('/')}/{path}{sep}viewport={w}x{h}&format=png&wait=1500"
    log.info("puppet GET %s", url)
    async with httpx.AsyncClient(timeout=timeout) as c:
        for attempt in (1, 2):  # Puppet can 404/5xx on a cold start; one retry covers it
            r = await c.get(url)
            if r.status_code == 200:
                return r.content
            log.warning("puppet %s on attempt %d", r.status_code, attempt)
            await asyncio.sleep(3)
        r.raise_for_status()
        return r.content


async def render_url(url: str, w: int, h: int, timeout: float = 60.0) -> bytes:
    """Arbitrary web page via headless Chromium's --screenshot."""
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "shot.png")
        cmd = [
            CHROMIUM, "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
            "--hide-scrollbars", "--force-device-scale-factor=1", f"--window-size={w},{h}",
            f"--user-data-dir={td}/profile", "--virtual-time-budget=8000", f"--screenshot={out}", url,
        ]
        log.info("chromium %s", url)
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
        try:
            _, err = await asyncio.wait_for(proc.communicate(), timeout)
        except asyncio.TimeoutError:
            proc.kill()
            raise RuntimeError("chromium timed out")
        if not os.path.exists(out):
            raise RuntimeError(f"chromium produced no screenshot: {err.decode(errors='ignore')[-400:]}")
        with open(out, "rb") as f:
            return f.read()


async def render_screen(screen: dict, puppet_url: str, w: int, h: int) -> bytes:
    if screen["type"] == "ha":
        raw = await render_ha(puppet_url, screen["target"], w, h)
    else:
        raw = await render_url(screen["target"], w, h)
    return dither(raw, w, h)


def placeholder(text: str, w: int, h: int) -> bytes:
    """Plain panel used when nothing is scheduled and no fallback is set, or rendering failed."""
    from PIL import ImageDraw, ImageFont

    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
    except Exception:
        font = ImageFont.load_default()
    d.text((w // 2, h // 2), text, fill="black", anchor="mm", font=font)
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def blank(w: int, h: int) -> bytes:
    """All-white panel (night / nothing scheduled)."""
    out = io.BytesIO()
    Image.new("RGB", (w, h), "white").save(out, format="PNG")
    return out.getvalue()
