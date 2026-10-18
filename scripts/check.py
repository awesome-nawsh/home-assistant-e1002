#!/usr/bin/env python3
"""Pre-commit integrity check for the E1002 repo. Run from the repo root: python3 scripts/check.py
Fails (exit 1) on: empty files, missing features, stale leftovers, undefined UI ids, Python/YAML
parse errors, changelog not newest-first, config.yaml version != top CHANGELOG entry."""
import ast, re, sys, os
try:
    import yaml  # optional: `pip3 install pyyaml` enables YAML parse checks
except ImportError:
    yaml = None

os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
A = "addon/e1002-scheduler"
bad = 0
def ok(cond, msg):
    global bad
    print(("OK   " if cond else "FAIL ") + msg); bad += (not cond)

REQUIRED = {
 f"{A}/app/render.py": ["for attempt in (1, 2)", "DITHER_MODES", "def sleep_card", "def render_screen", "wait_ms", "default_dither"],
 f"{A}/app/schedule.py": ["DWELL_MIN, DWELL_MAX = 2, 60", "def simulate_week", "def battery_estimate", "def next_window_start",
                          "def in_night", 'nav == "refresh"', 'nav == "prev"', "wait_ms", "dither must be", "def _pick", "def _sleep"],
 f"{A}/app/main.py": ["sleep_card", "nav: str = Query", "device_base_url", "render_wait_ms", 'opts.get("dither"', "status_code=204",
                      "battery_estimate", '"Cache-Control": "no-store"'],
 f"{A}/app/static/index.html": ["fDither", "fWait", "fDwell", 'max="60"', "openPreview", "Est. battery life", "gNightOn", "Sleep card (moon", "devUrl", "pvReload"],
 f"{A}/config.yaml": ["hassio_api: true", "render_wait_ms: 3000", "dither: floyd", "dither: list(floyd|none)", "battery_mah", "sleep_ma: float"],
 f"{A}/Dockerfile": ["ENV TZ=", "chromium"],
 "e1002-hallway.yaml": ["fw_version:", "project:", "id: scheduler_url", "esp32_ext1_wakeup", 'nav) = "refresh"', 'nav) = "next"', 'nav) = "prev"',
                        "No new image", "platform: online_image", "allow_other_uses: true"],
}
FORBIDDEN = {
 f"{A}/app/static/index.html": ["Blank panel", 'max="10"', "interval_min", "gInterval"],
 f"{A}/app/main.py": ["from render import blank", "active_screen()"],
 "e1002-hallway.yaml": ["\nonline_image:\n", "wakeup_pin:"],
}
for f, needles in REQUIRED.items():
    s = open(f).read()
    ok(len(s) > 0, f"{f}: not empty")
    miss = [n for n in needles if n not in s]
    ok(not miss, f"{f}: features present" + (f" — missing {miss}" if miss else ""))
for f, needles in FORBIDDEN.items():
    s = open(f).read(); hit = [n for n in needles if n in s]
    ok(not hit, f"{f}: no leftovers" + (f" — found {hit}" if hit else ""))
for f in [f"{A}/app/main.py", f"{A}/app/schedule.py", f"{A}/app/render.py"]:
    try: ast.parse(open(f).read()); ok(True, f"{f}: compiles")
    except SyntaxError as e: ok(False, f"{f}: {e}")
for f in [f"{A}/config.yaml", "repository.yaml", "dashboard.yaml"]:
    if yaml is None:
        ok(len(open(f).read()) > 0, f"{f}: not empty (install pyyaml for a full parse check)"); continue
    try: yaml.safe_load(open(f)); ok(True, f"{f}: YAML ok")
    except Exception as e: ok(False, f"{f}: {e}")
h = open(f"{A}/app/static/index.html").read()
ids = set(re.findall(r"getElementById\('([^']+)'\)", h)); defined = set(re.findall(r'id="([^"]+)"', h))
ok(ids <= defined, "index.html: all getElementById ids defined" + (f" — {sorted(ids - defined)}" if ids - defined else ""))
cl = open(f"{A}/CHANGELOG.md").read()
vers = re.findall(r"^## (\d+\.\d+\.\d+)", cl, re.M)
key = lambda v: tuple(map(int, v.split(".")))
ok(vers == sorted(vers, key=key, reverse=True), f"CHANGELOG newest-first {vers[:3]}")
m = re.search(r"^version:\s*\"?([\d.]+)\"?", open(f"{A}/config.yaml").read(), re.M)
cfgv = m.group(1) if m else None
ok(vers and vers[0] == str(cfgv), f"config.yaml version {cfgv} == top changelog {vers[0] if vers else None}")
fw = re.search(r'fw_version: "([^"]+)"', open("e1002-hallway.yaml").read())
ok(fw and fw.group(1) in open("e1002-hallway.yaml").read().split("substitutions:")[0], f"fw_version {fw.group(1) if fw else None} listed in YAML changelog header")
print("\nALL CHECKS PASSED" if not bad else f"\n{bad} CHECK(S) FAILED")
sys.exit(1 if bad else 0)
