"""Saving and loading of settings and highscores (plain JSON, no Flet needed)."""

import json
import math
import os
from datetime import date
from pathlib import Path

MAX_SCORES = 5  # how many times are kept per difficulty

# Packaged Flet apps get their own data folder; otherwise use the home folder.
# Change SAVE_FILE if you want the save next to the game instead.
_base = os.getenv("FLET_APP_STORAGE_DATA")
SAVE_FILE = (Path(_base) if _base else Path.home() / ".minesweeper") / "save.json"


def load() -> dict:
    """Read the save file. A missing or broken file gives an empty dict."""
    try:
        data = json.loads(SAVE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save(data: dict) -> None:
    """Write the save file atomically, so a crash can't leave it half-written."""
    try:
        SAVE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = SAVE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(SAVE_FILE)
    except OSError:
        pass  # the game keeps working even if the disk is read-only


def clean_scores(raw, modes) -> dict[str, list[dict]]:
    """Turn whatever was in the file into a valid {mode: [best times]} dict."""
    result: dict[str, list[dict]] = {mode: [] for mode in modes}
    if not isinstance(raw, dict):
        return result
    for mode in modes:
        items = raw.get(mode)
        if not isinstance(items, list):
            continue
        good = []
        for item in items:
            if not isinstance(item, dict):
                continue
            t = item.get("time")
            if (
                isinstance(t, (int, float))
                and not isinstance(t, bool)
                and math.isfinite(t)
                and 0 < t < 360_000
            ):
                good.append({"time": float(t), "date": str(item.get("date", ""))[:10]})
        result[mode] = sorted(good, key=lambda e: e["time"])[:MAX_SCORES]
    return result


def add_score(entries: list[dict], seconds: float) -> int | None:
    """Insert a time into a sorted top list.

    Returns its 0-based place, or None if it didn't make the list.
    Equal times keep the older entry in front.
    """
    place = sum(e["time"] <= seconds for e in entries)
    if place >= MAX_SCORES:
        return None
    entries.insert(place, {"time": seconds, "date": date.today().isoformat()})
    del entries[MAX_SCORES:]
    return place