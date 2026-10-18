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


DITHER_MODES = {
    "floyd": Image.Dither.FLOYDSTEINBERG,   # error diffusion: best for photos, gradients, charts
    "none": Image.Dither.NONE,              # nearest colour: crisp text and flat fills
}


def dither(png: bytes, w: int, h: int, mode: str = "floyd") -> bytes:
    img = Image.open(io.BytesIO(png)).convert("RGB")
    if img.size != (w, h):
        img = img.resize((w, h), Image.LANCZOS)
    q = img.quantize(palette=_palette_image(), dither=DITHER_MODES.get(mode, Image.Dither.FLOYDSTEINBERG))
    out = io.BytesIO()
    q.convert("RGB").save(out, format="PNG", optimize=True)
    return out.getvalue()


async def render_ha(puppet_url: str, path: str, w: int, h: int, wait_ms: int = 3000,
                    next_s: int = 0, timeout: float = 60.0) -> bytes:
    """HA dashboard path via the Puppet add-on. Puppet does the login; we do the dithering.
    wait_ms: how long Puppet waits after load before the screenshot (lets cards hydrate).
    next_s: hint so Puppet keeps its browser warm until the next expected request."""
    path = path.lstrip("/")
    sep = "&" if "?" in path else "?"
    url = f"{puppet_url.rstrip('/')}/{path}{sep}viewport={w}x{h}&format=png&wait={int(wait_ms)}"
    if next_s:
        url += f"&next={int(next_s)}"
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


async def render_url(url: str, w: int, h: int, wait_ms: int = 3000, timeout: float = 60.0) -> bytes:
    """Arbitrary web page via headless Chromium's --screenshot. wait_ms = virtual time budget."""
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "shot.png")
        cmd = [
            CHROMIUM, "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
            "--hide-scrollbars", "--force-device-scale-factor=1", f"--window-size={w},{h}",
            f"--user-data-dir={td}/profile", f"--virtual-time-budget={int(wait_ms) + 2000}", f"--screenshot={out}", url,
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


async def render_screen(screen: dict, puppet_url: str, w: int, h: int, default_wait_ms: int = 3000,
                        next_s: int = 0, default_dither: str = "floyd") -> bytes:
    wait_ms = int(screen.get("wait_ms") or default_wait_ms)
    if screen["type"] == "ha":
        raw = await render_ha(puppet_url, screen["target"], w, h, wait_ms, next_s)
    else:
        raw = await render_url(screen["target"], w, h, wait_ms)
    return dither(raw, w, h, screen.get("dither") or default_dither)


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


def sleep_card(title: str, subtitle: str, w: int, h: int) -> bytes:
    """Low-ink panel shown while idle or at night: moon + title + next wake time."""
    from PIL import ImageDraw, ImageFont

    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)

    def font(size: int):
        try:
            return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
        except Exception:
            return ImageFont.load_default()

    # crescent moon: black disc with a white disc cut out
    cx, cy, r = w // 2, h // 2 - 70, 46
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill="black")
    d.ellipse((cx - r + 26, cy - r - 14, cx + r + 26, cy + r - 14), fill="white")
    d.text((w // 2, h // 2 + 30), title, fill="black", anchor="mm", font=font(40))
    d.text((w // 2, h // 2 + 90), subtitle, fill="black", anchor="mm", font=font(26))
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()
