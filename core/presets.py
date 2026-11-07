"""Carga del catálogo de presets declarativos."""

from __future__ import annotations

import json
import os

TASK_MAP = {
    "convert": "video",
    "compress": "video",
    "archive": "video",
    "remux": "video",
    "intermediate": "video",
    "normalize-audio": "video",
    "extract-audio": "audio",
    "gif": "gif",
    "thumbnail": "image",
    "concat": "concat",
}


def _normalize(preset: dict):
    if not preset or not preset.get("id") or not preset.get("label"):
        return None
    task = TASK_MAP.get(preset.get("task"))
    container = preset.get("container")
    if not task or not container or container == "auto":
        return None

    video = preset.get("video") or {}
    audio = preset.get("audio") or {}
    quality = video.get("crf")
    if not isinstance(quality, (int, float)):
        quality = video.get("cq")
    if not isinstance(quality, (int, float)):
        quality = 21

    return {
        "id": preset["id"],
        "label": preset["label"],
        "description": preset.get("description", ""),
        "task": task,
        "verified": preset.get("verified", True) is not False,
        "options": {
            "task": task,
            "container": container,
            "videoCodec": video.get("codec") if video.get("codec") not in (None, "none")
            else ("none" if task == "audio" else "libx264"),
            "quality": int(quality),
            "preset": str(video["preset"]) if video.get("preset") is not None else None,
            "maxWidth": video.get("maxWidth"),
            "maxHeight": video.get("maxHeight"),
            "audioCodec": audio.get("codec") if audio.get("codec") not in (None, "none")
            else ("libmp3lame" if task == "audio" else "aac"),
            "audioBitrate": audio.get("bitrate"),
            "twoPass": bool(preset.get("twoPass")),
            "concatMode": preset.get("concatMode", "copy") if task == "concat" else None,
            "filterChain": preset.get("filterChain", "") if preset.get("filterKind") != "af" else "",
            "audioFilter": preset.get("filterChain", "") if preset.get("filterKind") == "af" else "",
        },
    }


def load_presets(file_path: str) -> list:
    if not os.path.isfile(file_path):
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return []
    presets = [_normalize(item) for item in data.get("presets", [])]
    return [p for p in presets if p]
