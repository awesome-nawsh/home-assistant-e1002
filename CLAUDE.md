# reTerminal E1002 hallway panel

Seeed reTerminal E1002 (ESP32-S3, 7.3" Spectra-6 e-paper, 800×480, battery) showing a
Home Assistant dashboard. Firmware: ESPHome. Image source: Puppet add-on screenshot of
the Lovelace view in `dashboard.yaml`. Device wakes, fetches PNG, draws, deep-sleeps.

## Files
- `e1002-hallway.yaml` — ESPHome config (the deliverable)
- `dashboard.yaml` — Lovelace view (storage-mode dashboard `e1002-hallway`, view `hallway`)
- `secrets.yaml.example` — keys the config expects; real `secrets.yaml` is gitignored

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

## Open / unverified
- 40 s `refresh_settle` before sleep is a guess for Spectra-6 full refresh; tune from logs.
- Battery life at 10-min cycles not yet measured.
