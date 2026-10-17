"""Screen store, schedule engine and sleep calculation.

Data model (screens.json):
{
  "default_dwell_min": 5,                 # 2..10, used by screens with dwell_min = null
  "fallback_screen": "<screen id or null>",   # null = blank panel when nothing is scheduled
  "night": {"enabled": true, "start": "23:00", "end": "06:30"},   # may cross midnight
  "screens": [
    {"id": "...", "name": "Hallway", "type": "ha" | "url", "target": "e1002-hallway/hallway",
     "enabled": true, "dwell_min": 5 | null,
     "windows": [{"days": [0..6], "start": "08:00", "end": "10:00"}, ...]}
  ],
  "devices": {"e1002": {"last_seen": iso, "last_screen": id | null, "battery_pct": .., ...}}
}
Days: 0 = Monday … 6 = Sunday.
Rotation: screens whose window covers "now" (and are enabled) are shown round-robin in list
order; each stays up for its dwell (2–10 min). Window boundaries cut a dwell short.
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

MAX_SLEEP_S = 6 * 3600
MIN_SLEEP_S = 60
DWELL_MIN, DWELL_MAX = 2, 10
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _hm(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def _at(day_dt: datetime, minutes: int) -> datetime:
    return day_dt.replace(hour=minutes // 60, minute=minutes % 60, second=0, microsecond=0)


class Store:
    def __init__(self, path: str, tz: str):
        self.path = path
        self.tz = ZoneInfo(tz)
        self._lock = threading.Lock()
        self.data: dict[str, Any] = {
            "default_dwell_min": 5,
            "fallback_screen": None,
            "night": {"enabled": False, "start": "23:00", "end": "06:30"},
            "screens": [],
            "devices": {},
        }
        if os.path.exists(path):
            with open(path) as f:
                saved = json.load(f)
            # migrate 0.1.x keys
            if "default_interval_min" in saved and "default_dwell_min" not in saved:
                saved["default_dwell_min"] = max(DWELL_MIN, min(DWELL_MAX, int(saved.pop("default_interval_min") or 5)))
            for s in saved.get("screens", []):
                if "interval_min" in s and "dwell_min" not in s:
                    iv = s.pop("interval_min")
                    s["dwell_min"] = None if iv is None else max(DWELL_MIN, min(DWELL_MAX, int(iv)))
            self.data.update(saved)

    # ---------- persistence ----------
    def save(self) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.data, f, indent=2)
        os.replace(tmp, self.path)

    # ---------- validation ----------
    @staticmethod
    def validate_screen(s: dict) -> list[str]:
        errs = []
        if not s.get("name", "").strip():
            errs.append("name is required")
        if s.get("type") not in ("ha", "url"):
            errs.append("type must be 'ha' or 'url'")
        t = s.get("target", "").strip()
        if not t:
            errs.append("target is required")
        elif s.get("type") == "url" and not t.startswith(("http://", "https://")):
            errs.append("url target must start with http:// or https://")
        d = s.get("dwell_min")
        if d is not None and (not isinstance(d, int) or d < DWELL_MIN or d > DWELL_MAX):
            errs.append(f"dwell must be {DWELL_MIN}–{DWELL_MAX} min or empty")
        for i, w in enumerate(s.get("windows", [])):
            days = w.get("days", [])
            if not days or any(d not in range(7) for d in days):
                errs.append(f"window {i+1}: pick at least one day")
            try:
                if _hm(w["start"]) >= _hm(w["end"]):
                    errs.append(f"window {i+1}: start must be before end (use the night schedule for overnight)")
            except Exception:
                errs.append(f"window {i+1}: times must be HH:MM")
        return errs

    # ---------- CRUD ----------
    def upsert_screen(self, s: dict) -> dict:
        with self._lock:
            s = {**s}
            s.setdefault("id", uuid.uuid4().hex[:8])
            s.setdefault("enabled", True)
            s.setdefault("windows", [])
            s.setdefault("dwell_min", None)
            s["name"] = s["name"].strip()
            s["target"] = s["target"].strip()
            errs = self.validate_screen(s)
            if errs:
                raise ValueError("; ".join(errs))
            screens = self.data["screens"]
            for i, old in enumerate(screens):
                if old["id"] == s["id"]:
                    screens[i] = s
                    break
            else:
                screens.append(s)
            self.save()
            return s

    def delete_screen(self, sid: str) -> None:
        with self._lock:
            self.data["screens"] = [s for s in self.data["screens"] if s["id"] != sid]
            if self.data.get("fallback_screen") == sid:
                self.data["fallback_screen"] = None
            self.save()

    def reorder(self, ids: list[str]) -> None:
        with self._lock:
            by_id = {s["id"]: s for s in self.data["screens"]}
            self.data["screens"] = [by_id[i] for i in ids if i in by_id] + [
                s for s in self.data["screens"] if s["id"] not in ids
            ]
            self.save()

    def set_globals(self, body: dict) -> None:
        with self._lock:
            if "default_dwell_min" in body and body["default_dwell_min"] is not None:
                d = int(body["default_dwell_min"])
                if d < DWELL_MIN or d > DWELL_MAX:
                    raise ValueError(f"default dwell must be {DWELL_MIN}–{DWELL_MAX} min")
                self.data["default_dwell_min"] = d
            if "fallback_screen" in body:
                self.data["fallback_screen"] = body["fallback_screen"] or None
            if "night" in body and body["night"] is not None:
                n = body["night"]
                try:
                    _hm(n["start"]); _hm(n["end"])
                except Exception:
                    raise ValueError("night start/end must be HH:MM")
                self.data["night"] = {"enabled": bool(n.get("enabled")), "start": n["start"], "end": n["end"]}
            self.save()

    def report(self, device: str, payload: dict) -> None:
        with self._lock:
            d = self.data["devices"].setdefault(device, {})
            d.update({k: v for k, v in payload.items() if k in ("battery_pct", "battery_v", "rssi")})
            d["last_seen"] = datetime.now(self.tz).isoformat(timespec="seconds")
            self.save()

    def mark_shown(self, device: str, sid: str | None) -> None:
        with self._lock:
            d = self.data["devices"].setdefault(device, {})
            d["last_screen"] = sid
            d["last_seen"] = datetime.now(self.tz).isoformat(timespec="seconds")
            self.save()

    # ---------- schedule engine ----------
    def now(self) -> datetime:
        return datetime.now(self.tz)

    def dwell_s(self, screen: dict) -> int:
        return int(screen.get("dwell_min") or self.data["default_dwell_min"]) * 60

    def in_night(self, at: datetime) -> bool:
        n = self.data.get("night") or {}
        if not n.get("enabled"):
            return False
        m, s, e = at.hour * 60 + at.minute, _hm(n["start"]), _hm(n["end"])
        return (s <= m < e) if s < e else (m >= s or m < e)

    def night_end(self, at: datetime) -> datetime:
        """Next moment the night window ends (only meaningful when in_night)."""
        n = self.data["night"]
        end = _at(at, _hm(n["end"]))
        if end <= at:
            end += timedelta(days=1)
        return end

    def active_screens(self, at: datetime | None = None) -> list[dict]:
        """Enabled screens whose window covers `at`, in list order. Empty during night."""
        at = at or self.now()
        if self.in_night(at):
            return []
        day, minute = at.weekday(), at.hour * 60 + at.minute
        out = []
        for s in self.data["screens"]:
            if not s.get("enabled", True):
                continue
            if any(day in w["days"] and _hm(w["start"]) <= minute < _hm(w["end"]) for w in s.get("windows", [])):
                out.append(s)
        return out

    def next_boundary(self, at: datetime | None = None) -> datetime | None:
        """Earliest future moment the active set can change: any window start/end, or night start/end."""
        at = at or self.now()
        best = None

        def consider(t: datetime) -> None:
            nonlocal best
            if t > at and (best is None or t < best):
                best = t

        for offset in range(8):
            day_dt = at + timedelta(days=offset)
            day = day_dt.weekday()
            for s in self.data["screens"]:
                if not s.get("enabled", True):
                    continue
                for w in s.get("windows", []):
                    if day in w["days"]:
                        consider(_at(day_dt, _hm(w["start"])))
                        consider(_at(day_dt, _hm(w["end"])))
            n = self.data.get("night") or {}
            if n.get("enabled"):
                consider(_at(day_dt, _hm(n["start"])))
                consider(_at(day_dt, _hm(n["end"])))
            if best is not None:
                return best
        return None

    def pick_next(self, device: str, at: datetime | None = None) -> tuple[dict | None, str]:
        """Choose what the device should show now. Returns (screen or None, reason)."""
        at = at or self.now()
        if self.in_night(at):
            return None, "night"
        active = self.active_screens(at)
        if not active:
            fb = self.fallback()
            return fb, "fallback" if fb else "idle"
        last = (self.data["devices"].get(device) or {}).get("last_screen")
        ids = [s["id"] for s in active]
        idx = (ids.index(last) + 1) % len(active) if last in ids else 0
        return active[idx], f"rotation {idx + 1}/{len(active)}"

    def sleep_seconds(self, device: str, at: datetime | None = None) -> tuple[int, str]:
        """Seconds to sleep after the device has just drawn, and a reason string."""
        at = at or self.now()
        boundary = self.next_boundary(at)
        to_boundary = int((boundary - at).total_seconds()) + 5 if boundary else MAX_SLEEP_S
        if self.in_night(at):
            end = self.night_end(at)
            return _clamp(int((end - at).total_seconds()) + 5), f"night until {end:%a %H:%M}"
        active = self.active_screens(at)
        if active:
            last = (self.data["devices"].get(device) or {}).get("last_screen")
            shown = next((s for s in active if s["id"] == last), active[0])
            dwell = self.dwell_s(shown)
            secs = min(dwell, to_boundary)
            names = " → ".join(s["name"] for s in active)
            return _clamp(secs), f"showing '{shown['name']}' for {dwell // 60} min (active: {names})"
        if boundary is None:
            return MAX_SLEEP_S, "no schedules — long sleep"
        return _clamp(to_boundary), f"idle until {boundary:%a %H:%M}"

    def fallback(self) -> dict | None:
        fid = self.data.get("fallback_screen")
        return next((s for s in self.data["screens"] if s["id"] == fid), None)


def _clamp(secs: int) -> int:
    return max(MIN_SLEEP_S, min(MAX_SLEEP_S, secs))
