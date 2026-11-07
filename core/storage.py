"""Estimación del tamaño de salida y comprobación de espacio libre."""

from __future__ import annotations

import os
import shutil

MB = 1024 * 1024


def parse_bitrate(value) -> float:
    """Convierte '2M' o '160k' en bits por segundo."""
    if not value:
        return 0.0
    text = str(value).strip().lower()
    multiplier = 1.0
    if text.endswith("k"):
        multiplier = 1000.0
        text = text[:-1]
    elif text.endswith("m"):
        multiplier = 1_000_000.0
        text = text[:-1]
    try:
        return float(text) * multiplier
    except ValueError:
        return 0.0


def _video_estimate(options, duration, source_bytes):
    if options.get("qualityMode") == "bitrate" and options.get("videoBitrate"):
        total = parse_bitrate(options["videoBitrate"]) + parse_bitrate(options.get("audioBitrate") or "192k")
        if duration and total:
            return max(50 * MB, total * duration / 8 * 1.1)
    return max(100 * MB, source_bytes * 1.25)


def estimate_output_bytes(options, medias, source_bytes=None) -> int:
    """Estimación prudente del espacio necesario para un trabajo."""
    task = options.get("task", "video")
    medias = medias or []
    duration = sum(float(media.get("duration") or 0) for media in medias)
    if source_bytes is None:
        source_bytes = sum(float(media.get("size") or 0) for media in medias)

    if task == "image":
        return 30 * MB

    if task == "sheet":
        return 40 * MB

    if task == "capture":
        try:
            duration = float(options.get("captureDuration") or 0)
        except (TypeError, ValueError):
            duration = 0
        if duration > 0:
            return max(100 * MB, int(duration * 0.5 * MB))
        return 2 * 1024 * MB

    if task == "subs":
        mode = options.get("subsMode", "extract")
        if mode == "extract":
            return 20 * MB
        if mode == "mux":
            return int(source_bytes * 1.02) + 30 * MB
        return int(_video_estimate(options, duration, source_bytes))

    if task == "audio":
        bitrate = parse_bitrate(options.get("audioBitrate") or "192k")
        if duration and bitrate:
            return max(20 * MB, int(bitrate * duration / 8 * 1.1))
        return max(20 * MB, int(source_bytes * 0.35))

    if task == "gif":
        return max(30 * MB, int(source_bytes * 1.2))

    if task == "concat":
        if options.get("concatMode", "copy") == "copy":
            return int(source_bytes * 1.05) + 50 * MB
        return int(_video_estimate(options, duration, source_bytes))

    codec = options.get("videoCodec")
    if codec == "copy" and (options.get("audioCodec") or "aac") == "copy":
        return int(source_bytes * 1.02) + 30 * MB
    return int(_video_estimate(options, duration, source_bytes))


def free_bytes(path: str) -> int:
    directory = path if os.path.isdir(path) else os.path.dirname(os.path.abspath(path))
    while directory and not os.path.isdir(directory):
        parent = os.path.dirname(directory)
        if parent == directory:
            break
        directory = parent
    try:
        return shutil.disk_usage(directory or ".").free
    except OSError:
        return 0


def format_size(num_bytes: float) -> str:
    value = float(num_bytes or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} TB"


def has_space(output_path: str, needed_bytes: int) -> bool:
    return free_bytes(output_path) >= needed_bytes


def space_error_message(output_path: str, needed_bytes: int) -> str:
    free = free_bytes(output_path)
    return (
        f"Espacio insuficiente en el disco de destino: se estiman {format_size(needed_bytes)} "
        f"y quedan {format_size(free)} libres. Libera espacio o elige otra carpeta de salida."
    )
