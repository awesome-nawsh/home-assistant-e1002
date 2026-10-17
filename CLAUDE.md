# reTerminal E1002 hallway panel

Seeed reTerminal E1002 (ESP32-S3, 7.3" Spectra-6 e-paper, 800×480, battery) showing a
Home Assistant dashboard. Firmware: ESPHome. Image source: Puppet add-on screenshot of
the Lovelace view in `dashboard.yaml`. Device wakes, fetches PNG, draws, deep-sleeps.

## Files
- `e1002-hallway.yaml` — ESPHome config. Fetches `/api/image`, posts `/api/report`, reads `/api/sleep`
  from the add-on, then deep-sleeps for the returned seconds (fallback 10 min if unreachable).
- `dashboard.yaml` — Lovelace view (storage-mode dashboard `e1002-hallway`, view `hallway`)
- `addon/e1002-scheduler/` — HA add-on: screens (HA path via Puppet, or URL via headless Chromium),
  non-overlapping schedules, per-screen interval, 6-colour Floyd–Steinberg dithering, device API on
  port 8098, Ingress UI. Data in `/data/screens.json`. `repository.yaml` at repo root installs it.
- `secrets.yaml.example` — keys the config expects; real `secrets.yaml` is gitignored

## Add-on dev loop
- Edit under `addon/e1002-scheduler/`, bump `version` in `config.yaml`, push, then HA store → Update.
- Local smoke test (no Chromium/Puppet needed; renders fall back to a placeholder PNG):
  `OPTIONS_PATH=/x DATA_PATH=/tmp/s.json python3 -m uvicorn main:app --app-dir addon/e1002-scheduler/app`
- Scheduler semantics: at most one active screen (overlap rejected on save); sleep =
  min(interval, time to window end) when active, else time to next window start, clamped 60 s–6 h.

## Hardware facts (Seeed cookbooks, ESPHome 2026.9)
- Display: `epaper_spi` model `Seeed-reTerminal-E1002`; SPI CLK 7 / MOSI 9; CS 10, DC 11, RESET 12, BUSY 13 (inverted)
- PSRAM must be `octal` — quad fails to load the image
- Battery: ADC GPIO1 ×2.0, enable GPIO21 on at boot; LED GPIO6; buzzer GPIO45
- Buttons (INPUT_PULLUP, inverted): green 3, right white 4 (deep-sleep wake), left white 5
- Serial logs need `logger: hardware_uart: UART0`
- Wi-Fi 2.4 GHz only

## Rules
1. Don't assume; surface tradeoffs; ask before research-heavy changes.
2. Minimum change. Touch only what you must.
3. Validate YAML before delivering. Flash over USB first, then OTA.
4. Hardware-verified facts beat documentation — append dated lessons below when verified.
5. Deep sleep + OTA: hold the right white button to wake the device before uploading.

## Lessons (dated, hardware-verified)
- 2026-10-11 — button-card `styles.grid` + `grid-template-areas` with several `custom_fields`
  collapsed everything into one cell on HA 2026.10. Working pattern: one custom field
  returning the whole panel as inline-styled HTML. `triggers_update` must list every entity
  the template reads.
- 2026-10-12 — `utility_meter` daily on `…energy_cumulative` →
  `sensor.mains_house_monitor_singapore_house_energy_today_ha` (the old today sensor never reset).

- 2026-10-17 — First USB flash of `e1002-hallway.yaml` on ESPHome 2026.9.1 built clean with
  `esp-idf` + `psram: octal`; `epaper_spi` model `Seeed-reTerminal-E1002` + `online_image`
  (PNG, RGB565, 800x480 from Puppet via `homeassistant.local`) rendered the colour panel
  first try. Pins in this file are therefore hardware-verified.

- 2026-10-17 — Scheduler add-on 0.1.1 verified end-to-end with OTA firmware: image → draw →
  report → sleep from `/api/sleep`. Puppet reachable from the add-on at `http://172.30.32.1:10000`
  (set via the `puppet_url` option); the add-on hostname did not resolve. Host port mapped to 8198
  (8098 clashed with OpenDisplay Wi-Fi add-on) — firmware `scheduler_url` must match. HA screens
  need the `dashboard/view` path form. Puppet 404s on a cold render → add-on retries once.

## Open / unverified
- 40 s `refresh_settle` before sleep is a guess for Spectra-6 full refresh; tune from logs.
- Battery life not yet measured; Energy screen currently at 5-min interval for testing.
- Web-URL screens (headless Chromium path) not yet exercised on real hardware.
