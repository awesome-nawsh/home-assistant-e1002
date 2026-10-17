# E1002 Scheduler

Serves an 800×480 six-colour PNG to a deep-sleeping e-paper display and tells it how long to sleep,
based on screens and schedules you configure in the add-on's web UI.

## Options
- `puppet_url` — where the Puppet add-on is reachable from this container. Default is Puppet's
  add-on hostname. If HA-dashboard screens fail to render, try `http://172.30.32.1:10000`.
- `timezone` — schedules are interpreted in this zone.
- `width`/`height` — panel size.

## Device API (host port as mapped in the add-on; default 8098)
- `GET /api/image?device=<id>` → PNG of the currently scheduled screen (or the fallback screen)
- `GET /api/sleep?device=<id>` → integer seconds to sleep before the next wake
- `POST /api/report?device=<id>` → JSON `{battery_pct, battery_v, rssi}`; shown in the UI

## Schedules
Each screen has one or more windows (days + start/end, same day, no midnight crossing).
Saving is refused if windows of two enabled screens overlap, so at most one screen is active at any time.
When no screen is active the device sleeps until the next window opens (max 6 h).
