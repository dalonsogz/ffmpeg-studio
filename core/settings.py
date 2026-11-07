"""Ajustes persistentes en %APPDATA%."""

from __future__ import annotations

import json
import os

DEFAULTS = {
    "ffmpegPath": None,
    "ffprobePath": None,
    "outputDir": None,
    "lastTask": "video",
    "openOutputWhenDone": False,
    "hardwareCache": None,
}


def settings_path() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "FFmpegStudio", "settings.json")


def load_settings(path: str = None) -> dict:
    path = path or settings_path()
    data = dict(DEFAULTS)
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data.update(json.load(handle))
        except (OSError, json.JSONDecodeError):
            pass
    return data


def save_settings(settings: dict, path: str = None) -> bool:
    path = path or settings_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(settings, handle, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False
