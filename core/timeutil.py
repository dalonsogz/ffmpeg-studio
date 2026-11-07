"""Conversión entre segundos y cadenas de tiempo de FFmpeg."""

from __future__ import annotations


def parse_time(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", ".")
    if not text:
        return None
    parts = [p.strip() for p in text.split(":")]
    if any(p == "" for p in parts):
        return None
    try:
        total = 0.0
        for part in parts:
            total = total * 60 + float(part)
        return total
    except ValueError:
        return None


def format_time(seconds) -> str:
    try:
        seconds = max(0.0, float(seconds))
    except (TypeError, ValueError):
        seconds = 0.0
    total_ms = int(round(seconds * 1000))
    ms = total_ms % 1000
    rest = total_ms // 1000
    hours, rest = divmod(rest, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{ms:03d}"


def format_size(num_bytes) -> str:
    if not num_bytes:
        return "—"
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(num_bytes)
    index = 0
    while value >= 1024 and index < len(units) - 1:
        value /= 1024
        index += 1
    return f"{value:.0f} {units[index]}" if value >= 100 else f"{value:.1f} {units[index]}"
