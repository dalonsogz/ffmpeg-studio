"""Lectura de metadatos con ffprobe."""

from __future__ import annotations

import json
import os
import subprocess

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _to_number(value):
    try:
        number = float(value)
        return number if number == number else None  # descarta NaN
    except (TypeError, ValueError):
        return None


def _ratio(value):
    if not value or not isinstance(value, str):
        return None
    if "/" in value:
        num, den = value.split("/", 1)
        num, den = _to_number(num), _to_number(den)
        if num is None:
            return None
        if not den:
            return num
        return num / den
    return _to_number(value)


def _normalize_stream(stream: dict) -> dict:
    tags = stream.get("tags") or {}
    disposition = stream.get("disposition") or {}
    return {
        "index": stream.get("index"),
        "type": stream.get("codec_type"),
        "codec": stream.get("codec_name"),
        "codecLong": stream.get("codec_long_name"),
        "profile": stream.get("profile"),
        "bitRate": _to_number(stream.get("bit_rate")),
        "duration": _to_number(stream.get("duration")),
        "width": stream.get("width"),
        "height": stream.get("height"),
        "fps": _ratio(stream.get("avg_frame_rate")) or _ratio(stream.get("r_frame_rate")),
        "pixFmt": stream.get("pix_fmt"),
        "sampleRate": _to_number(stream.get("sample_rate")),
        "channels": stream.get("channels"),
        "channelLayout": stream.get("channel_layout"),
        "language": tags.get("language"),
        "title": tags.get("title"),
        "default": bool(disposition.get("default")),
        "forced": bool(disposition.get("forced")),
    }


def probe_file(ffprobe_path: str, file_path: str, timeout: float = 25) -> dict:
    args = [
        "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        "-show_chapters",
        file_path,
    ]
    result = subprocess.run(
        [ffprobe_path] + args,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, creationflags=CREATE_NO_WINDOW,
    )
    if result.returncode != 0:
        detail = (result.stderr or "").strip().splitlines()
        raise RuntimeError(detail[-1] if detail else "ffprobe no pudo leer el archivo")

    data = json.loads(result.stdout or "{}")
    fmt = data.get("format") or {}
    streams = [_normalize_stream(s) for s in (data.get("streams") or [])]
    video = next((s for s in streams if s["type"] == "video"), None)
    audios = [s for s in streams if s["type"] == "audio"]
    subtitles = [s for s in streams if s["type"] == "subtitle"]

    duration = _to_number(fmt.get("duration"))
    if duration is None and video:
        duration = video.get("duration")
    if duration is None and audios:
        duration = audios[0].get("duration")

    return {
        "path": file_path,
        "name": os.path.basename(file_path),
        "size": _to_number(fmt.get("size")),
        "duration": duration,
        "formatName": fmt.get("format_name"),
        "formatLong": fmt.get("format_long_name"),
        "bitRate": _to_number(fmt.get("bit_rate")),
        "video": video,
        "audios": audios,
        "subtitles": subtitles,
        "chapters": [
            {
                "start": _to_number(c.get("start_time")),
                "end": _to_number(c.get("end_time")),
                "title": (c.get("tags") or {}).get("title") or "Capítulo",
            }
            for c in (data.get("chapters") or [])
        ],
        "streams": streams,
    }
