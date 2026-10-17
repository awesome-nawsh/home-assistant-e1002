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

