# E1002 Hallway — Home Assistant e-paper panel

ESPHome firmware for a Seeed reTerminal E1002 plus the **E1002 Scheduler** HA add-on that
decides what it shows and when it sleeps. The display wakes, fetches one PNG from the add-on,
draws it, reports battery, asks how long to sleep, and deep-sleeps.

```
ESP32 (deep sleep) ──GET /api/image──▶ E1002 Scheduler add-on ──▶ Puppet (HA dashboards)
                   ──POST /api/report─▶   screens + schedules   ──▶ headless Chromium (web URLs)
                   ◀─GET /api/sleep────   6-colour dithering
```

## Repo layout
- `e1002-hallway.yaml` — ESPHome config
- `dashboard.yaml` — the Lovelace "hallway" view (storage dashboard `e1002-hallway`)
- `addon/e1002-scheduler/` — the add-on (FastAPI + single-page UI)
- `repository.yaml` — makes this repo installable as an HA add-on repository

## Install the add-on
1. HA → Settings → Apps → Store → ⋮ → Repositories → add `https://github.com/awesome-nawsh/home-assistant-e1002`
2. Install **E1002 Scheduler** (first build ≈ 5 min: it compiles nothing but pulls Chromium), start it.
3. Open its panel (sidebar **E1002 Screens**). Add a screen:
   - type **HA dashboard**, path `e1002-hallway/hallway?kiosk`, windows e.g. Mon–Sun 07:00–23:00
   - or type **Web URL** with a full `https://…` address
   Schedules of enabled screens may not overlap; the editor tells you what clashes.
4. Set a fallback screen if you want something shown outside all windows.

Requires the **Puppet** add-on (balloob) for HA-dashboard screens.

## Firmware
1. ESPHome Device Builder → Secrets: `wifi_ssid`, `wifi_password`, `api_encryption_key`.
2. Add `e1002-hallway.yaml`; first install over USB; later installs OTA (hold the right white
   button to wake the device first).
3. Adopt the discovered ESPHome device in HA.

## Success criteria
- Panel shows the scheduled screen within ~90 s of boot
- Add-on's device panel shows battery / last seen after each wake
- Outside all windows the device sleeps through to the next window (≤ 6 h hops)

## Operating notes
- No way to wake a deep-sleeping device over Wi-Fi: the green button forces a refresh.
- Battery life scales with the interval; 10 min ≈ weeks, 30 min ≈ 2–3× longer (estimate).
