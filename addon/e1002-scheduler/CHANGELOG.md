## 0.2.8
- Web-URL screens: Chromium time budget is max(8 s, render wait + 2 s) — restores the original 8 s floor.

## 0.2.7
- UI served with Cache-Control: no-store so updates show without a hard reload.

## 0.2.6
- Per-screen dither: Floyd–Steinberg or none (nearest colour); global default option `dither`.

## 0.2.5
- Per-screen render wait (ms) with a global default option `render_wait_ms` (3000); fixes half-drawn cards on cold renders.
- Device fetches always render fresh and pass Puppet a `next=` hint so its browser stays warm.

## 0.2.4
- Sleep card (moon + "Nothing scheduled"/"Sleeping" + next screen time) replaces the blank panel; redrawn only when the text changes.
- Firmware: 204 from the scheduler logged as "No new image", not a failure.

## 0.2.3
- UI shows the exact device API URL (host port read from the Supervisor).

## 0.2.2
- `nav=next|prev|refresh` on /api/image: right/left buttons step the rotation, green re-shows the current screen.

## 0.2.1
- Dwell range widened to 2–60 min.

## 0.2.0
- Overlapping schedules now rotate round-robin; per-screen dwell 2–60 min with a global default.
- Night schedule (may cross midnight): panel cleared once, device sleeps through.
- Blank panel when nothing is scheduled and no fallback; no redraw on later idle wakes (204).
- Migrates 0.1.x `interval_min` → `dwell_min`.
- Thumbnail click opens a full-size preview with a Re-render button.
- Estimated battery life from a simulated week of the schedule; model constants are add-on options.

