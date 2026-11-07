"""Opciones por defecto de cada tarea."""

from __future__ import annotations

import copy

TASKS = ["video", "audio", "gif", "image", "concat", "subs", "sheet", "capture"]

_DEFAULTS = {
    "task": "video",
    "container": "mp4",
    "videoCodec": "libx264",
    "quality": 21,
    "qualityMode": "crf",
    "videoBitrate": "2M",
    "preset": "medium",
    "maxWidth": 1920,
    "maxHeight": 1080,
    "audioCodec": "aac",
    "audioBitrate": "160k",
    "audioChannels": None,
    "normalizeLoudness": False,
    "loudnessTarget": -16,
    "includeSubtitles": False,
    "twoPass": False,
    "speed": 1.0,
    "fps": 0,
    "rotate": 0,
    "flip": "none",
    "crop": {"left": 0, "top": 0, "right": 0, "bottom": 0},
    "sheetCount": 9,
    "sheetWidth": 480,
    "audioTrack": -1,
    "subtitleTrack": -1,
    "concatTransition": "none",
    "concatTransitionDuration": 1.0,
    "captureSource": "screen",
    "captureFps": 30,
    "captureDuration": 10,
    "captureTitle": "",
    "captureDevice": "",
    "trim": {"enabled": False, "start": 0, "end": 0, "mode": "exact"},
    "gifFps": 12,
    "gifWidth": 480,
    "imageTime": 1,
    "concatMode": "copy",
    "subsMode": "extract",
    "subtitleStream": 0,
    "subtitleFormat": "srt",
    "subtitleFile": None,
    "subtitleLanguage": "spa",
    "subtitleTitle": "",
    "subtitleDefault": False,
    "burnStyle": {
        "font": "Arial",
        "size": 24,
        "color": "blanco",
        "position": "abajo",
        "bold": False,
        "outline": True,
    },
    "filterChain": "",
    "audioFilter": "",
    "extraArgs": [],
}


def default_options(**overrides) -> dict:
    options = copy.deepcopy(_DEFAULTS)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(options.get(key), dict):
            options[key].update(value)
        else:
            options[key] = value
    return options


def defaults_for_task(task: str) -> dict:
    if task == "audio":
        return default_options(task="audio", container="mp3", videoCodec="none",
                               audioCodec="libmp3lame", audioBitrate="192k")
    if task == "gif":
        return default_options(task="gif", container="gif", videoCodec="gif")
    if task == "image":
        return default_options(task="image", container="jpg", videoCodec="mjpeg", maxWidth=1280)
    if task == "concat":
        return default_options(task="concat", container="mp4", videoCodec="libx264", concatMode="copy")
    if task == "subs":
        return default_options(task="subs", container="mp4", videoCodec="libx264")
    if task == "sheet":
        return default_options(task="sheet", container="jpg", videoCodec="mjpeg", audioCodec="none")
    if task == "capture":
        return default_options(task="capture", container="mp4", videoCodec="libx264", audioCodec="none")
    return default_options(task="video")
