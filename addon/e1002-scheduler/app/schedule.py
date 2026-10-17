"""Screen store, schedule engine and sleep calculation.

Data model (screens.json):
{
  "default_interval_min": 10,
  "fallback_screen": "<screen id or null>",
  "screens": [
    {"id": "...", "name": "Hallway", "type": "ha" | "url", "target": "e1002-hallway/hallway",
     "enabled": true, "interval_min": 10 | null,
     "windows": [{"days": [0..6], "start": "07:00", "end": "23:00"}]}
  ],
  "devices": {"e1002": {"last_seen": iso, "last_screen": id, "battery_pct": .., "battery_v": .., "rssi": ..}}
}
Days: 0 = Monday … 6 = Sunday (Python weekday()).
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


def _hm(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


class Store:
    def __init__(self, path: str, tz: str):
        self.path = path
        self.tz = ZoneInfo(tz)
        self._lock = threading.Lock()
        self.data: dict[str, Any] = {
            "default_interval_min": 10,
            "fallback_screen": None,
            "screens": [],
            "devices": {},
        }
        if os.path.exists(path):
            with open(path) as f:
                self.data.update(json.load(f))

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
        iv = s.get("interval_min")
        if iv is not None and (not isinstance(iv, int) or iv < 1 or iv > 1440):
            errs.append("interval_min must be 1–1440 or empty")
        for i, w in enumerate(s.get("windows", [])):
            days = w.get("days", [])
            if not days or any(d not in range(7) for d in days):
                errs.append(f"window {i+1}: pick at least one day")
            try:
                if _hm(w["start"]) >= _hm(w["end"]):
                    errs.append(f"window {i+1}: start must be before end (no midnight crossing)")
            except Exception:
                errs.append(f"window {i+1}: times must be HH:MM")
        return errs

    def find_conflicts(self, candidate: dict) -> list[str]:
        """Return human-readable conflicts between candidate and other enabled screens."""
        if not candidate.get("enabled", True):
            return []
        out = []
        for other in self.data["screens"]:
            if other["id"] == candidate.get("id") or not other.get("enabled", True):
                continue
            for w in candidate.get("windows", []):
                for ow in other.get("windows", []):
                    shared = set(w["days"]) & set(ow["days"])
                    if not shared:
                        continue
                    if _hm(w["start"]) < _hm(ow["end"]) and _hm(ow["start"]) < _hm(w["end"]):
                        out.append(
                            f"{w['start']}–{w['end']} overlaps '{other['name']}' "
                            f"{ow['start']}–{ow['end']} on {', '.join(DAY_NAMES[d] for d in sorted(shared))}"
                        )
        return out

    # ---------- CRUD ----------
    def upsert_screen(self, s: dict) -> dict:
        with self._lock:
            s = {**s}
            s.setdefault("id", uuid.uuid4().hex[:8])
            s.setdefault("enabled", True)
            s.setdefault("windows", [])
            s["name"] = s["name"].strip()
            s["target"] = s["target"].strip()
            errs = self.validate_screen(s) + self.find_conflicts(s)
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

    def set_globals(self, default_interval_min: int | None, fallback_screen: str | None) -> None:
        with self._lock:
            if default_interval_min is not None:
                if default_interval_min < 1 or default_interval_min > 1440:
                    raise ValueError("default_interval_min must be 1–1440")
                self.data["default_interval_min"] = default_interval_min
            if fallback_screen is not None:
                self.data["fallback_screen"] = fallback_screen or None
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

    def active_screen(self, at: datetime | None = None) -> tuple[dict | None, datetime | None]:
        """Return (screen, window_end) active at `at`, else (None, None)."""
        at = at or self.now()
        day, minute = at.weekday(), at.hour * 60 + at.minute
        for s in self.data["screens"]:
            if not s.get("enabled", True):
                continue
            for w in s.get("windows", []):
                if day in w["days"] and _hm(w["start"]) <= minute < _hm(w["end"]):
                    end = at.replace(hour=_hm(w["end"]) // 60, minute=_hm(w["end"]) % 60, second=0, microsecond=0)
                    return s, end
        return None, None

    def next_window_start(self, at: datetime | None = None) -> datetime | None:
        """Earliest future window start across enabled screens (searches 8 days)."""
        at = at or self.now()
        best = None
        for offset in range(8):
            day_dt = (at + timedelta(days=offset)).replace(second=0, microsecond=0)
            day = day_dt.weekday()
            for s in self.data["screens"]:
                if not s.get("enabled", True):
                    continue
                for w in s.get("windows", []):
                    if day not in w["days"]:
                        continue
                    start = day_dt.replace(hour=_hm(w["start"]) // 60, minute=_hm(w["start"]) % 60)
                    if start > at and (best is None or start < best):
                        best = start
            if best is not None:
                return best
        return None

    def sleep_seconds(self, at: datetime | None = None) -> tuple[int, str]:
        """Seconds to sleep and a reason string."""
        at = at or self.now()
        screen, end = self.active_screen(at)
        if screen:
            interval = (screen.get("interval_min") or self.data["default_interval_min"]) * 60
            to_end = int((end - at).total_seconds())
            # if the window ends sooner than the interval, wake at the window end (+ a few s) to
            # pick up whatever is scheduled next (or go to long sleep)
            secs = min(interval, max(to_end, MIN_SLEEP_S) + 5)
            return _clamp(secs), f"active '{screen['name']}', interval {interval // 60} min, window ends {end:%H:%M}"
        nxt = self.next_window_start(at)
        if nxt is None:
            return MAX_SLEEP_S, "no schedules — long sleep"
        secs = int((nxt - at).total_seconds()) + 5
        return _clamp(secs), f"idle until {nxt:%a %H:%M}"

    def fallback(self) -> dict | None:
        fid = self.data.get("fallback_screen")
        for s in self.data["screens"]:
            if s["id"] == fid:
                return s
        return None


def _clamp(secs: int) -> int:
    return max(MIN_SLEEP_S, min(MAX_SLEEP_S, secs))


DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
