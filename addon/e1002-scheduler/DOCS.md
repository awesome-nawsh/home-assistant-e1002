# E1002 Scheduler

Serves an 800×480 six-colour PNG to a deep-sleeping e-paper display and tells it how long to sleep,
based on screens and schedules you configure in the add-on's web UI.

## Options
- `puppet_url` — where the Puppet add-on is reachable from this container. Default is Puppet's
  add-on hostname. If HA-dashboard screens fail to render, try `http://172.30.32.1:10000`.
- `timezone` — schedules are interpreted in this zone.
- `width`/`height` — panel size.
- `battery_mah`, `awake_mah_per_wake`, `draw_mah`, `sleep_ma` — battery model used for the estimate
  shown in the UI. Defaults are rough; adjust once real voltage readings give you a drain rate.

## Device API (host port as mapped in the add-on; default 8098)
- `GET /api/image?device=<id>` → PNG of the currently scheduled screen (or the fallback screen)
- `GET /api/sleep?device=<id>` → integer seconds to sleep before the next wake
- `POST /api/report?device=<id>` → JSON `{battery_pct, battery_v, rssi}`; shown in the UI

## Schedules
Each screen has one or more windows (days + start/end within one day). Screens whose windows
overlap rotate in list order; each stays up for its dwell (2–10 min, per screen or the default).
A window starting or ending cuts the current dwell short so the schedule is honoured.
When no screen is active the panel is blanked (or shows the fallback screen) and the device sleeps
until the next window (6 h hops). The night schedule (may cross midnight) blanks the panel once and
sleeps the device through to its end.
