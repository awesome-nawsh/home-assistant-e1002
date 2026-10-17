## 0.2.0
- Overlapping schedules now rotate round-robin; per-screen dwell 2–10 min with a global default.
- Night schedule (may cross midnight): panel cleared once, device sleeps through.
- Blank panel when nothing is scheduled and no fallback; no redraw on later idle wakes (204).
- Migrates 0.1.x `interval_min` → `dwell_min`.

