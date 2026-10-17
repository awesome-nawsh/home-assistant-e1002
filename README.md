# E1002 Hallway — Home Assistant e-paper panel

ESPHome firmware for a Seeed reTerminal E1002 that shows a Home Assistant dashboard,
refreshes every 10 min and deep-sleeps in between (battery powered).

## Setup
1. HA: install **Puppet** add-on (repo `https://github.com/balloob/home-assistant-addons`),
   set its `access_token`, start it.
2. HA: create dashboard `e1002-hallway` from `dashboard.yaml` (needs `button-card` + `kiosk-mode` from HACS).
   Check `http://homeassistant.local:10000/e1002-hallway/hallway?kiosk&viewport=800x480&format=png` renders.
3. ESPHome: copy `secrets.yaml.example` → add-on secrets, fill in values.
4. ESPHome: add `e1002-hallway.yaml`, flash over USB first (replaces OpenDisplay firmware).
5. Watch logs for `Dashboard image downloaded, drawing`.

## Success criteria
- Colour panel appears within ~90 s of boot
- `sensor.e1002_hallway_battery` reports in HA
- Device sleeps (unavailable in HA) and refreshes every 10 min

## Operating notes
- Hold the right white button to wake for OTA; green button forces a refresh while awake.
- Battery life scales with `sleep_minutes`; 10 min ≈ weeks, 30 min ≈ 2–3× longer (estimate).
