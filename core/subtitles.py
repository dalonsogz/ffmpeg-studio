"""Lectura y escritura de subtítulos para el editor (SRT y WebVTT)."""

from __future__ import annotations

import os
import re
import tempfile

TIME_PATTERN = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})")
SHORT_PATTERN = re.compile(r"(\d{1,2}):(\d{2})[,.](\d{1,3})")
CUE_LINE = re.compile(
    r"\s*(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3}|\d{1,2}:\d{2}[,.]\d{1,3})"
    r"\s*-->\s*"
    r"(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3}|\d{1,2}:\d{2}[,.]\d{1,3})"
)

EXTENSIONS = (".srt", ".vtt")


def parse_time(value):
    """Convierte «HH:MM:SS,mmm» (o MM:SS,mmm) a milisegundos."""
    text = (value or "").strip().replace(".", ",")
    match = TIME_PATTERN.search(text)
    if match:
        hours, minutes, seconds, millis = match.groups()
        return ((int(hours) * 60 + int(minutes)) * 60 + int(seconds)) * 1000 + int(millis.ljust(3, "0"))
    match = SHORT_PATTERN.search(text)
    if match:
        minutes, seconds, millis = match.groups()
        return (int(minutes) * 60 + int(seconds)) * 1000 + int(millis.ljust(3, "0"))
    return None


def format_time(milliseconds, separator=","):
    milliseconds = max(0, int(milliseconds))
    hours, rest = divmod(milliseconds, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    seconds, millis = divmod(rest, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{separator}{millis:03d}"


def parse_cues(text):
    """Extrae los subtítulos de un SRT o WebVTT ya leído como texto."""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if text.upper().startswith("WEBVTT"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.lstrip("\n")

    cues = []
    for block in re.split(r"\n\s*\n", text):
        lines = block.split("\n")
        while lines and not lines[0].strip():
            lines.pop(0)
        if not lines:
            continue
        if lines[0].strip().isdigit():
            lines = lines[1:]
        if not lines:
            continue
        match = CUE_LINE.match(lines[0])
        if not match:
            continue
        start = parse_time(match.group(1))
        end = parse_time(match.group(2))
        if start is None or end is None:
            continue
        body = "\n".join(lines[1:]).strip()
        cues.append({"start": start, "end": end, "text": body})
    return cues


def write_srt(cues):
    blocks = []
    for index, cue in enumerate(cues, start=1):
        blocks.append(str(index))
        blocks.append(f"{format_time(cue['start'])} --> {format_time(cue['end'])}")
        blocks.append(cue.get("text") or "")
        blocks.append("")
    return "\n".join(blocks)


def write_vtt(cues):
    blocks = ["WEBVTT", ""]
    for cue in cues:
        blocks.append(f"{format_time(cue['start'], '.')} --> {format_time(cue['end'], '.')}")
        blocks.append(cue.get("text") or "")
        blocks.append("")
    return "\n".join(blocks)


def normalize_cues(cues):
    normalized = []
    for index, cue in enumerate(cues or [], start=1):
        try:
            start = int(cue.get("start"))
            end = int(cue.get("end"))
        except (TypeError, ValueError):
            raise ValueError(f"Subtítulo {index}: las horas no son válidas.")
        if start < 0 or end < 0:
            raise ValueError(f"Subtítulo {index}: las horas no pueden ser negativas.")
        if end <= start:
            raise ValueError(f"Subtítulo {index}: el fin debe ser posterior al inicio.")
        normalized.append({"start": start, "end": end, "text": (cue.get("text") or "").strip()})
    return normalized


def load_subtitles(path):
    extension = os.path.splitext(path)[1].lower()
    if extension in (".ass", ".ssa"):
        return {
            "ok": False,
            "error": "Los archivos ASS/SSA llevan estilos y no se editan aquí. "
                     "Extráelos primero a SRT desde la pestaña Subs.",
        }
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as handle:
            text = handle.read()
    except OSError as error:
        return {"ok": False, "error": f"No se pudo leer el archivo: {error.strerror or error}"}

    cues = parse_cues(text)
    fmt = "vtt" if extension == ".vtt" or text.lstrip().upper().startswith("WEBVTT") else "srt"
    return {"ok": True, "cues": cues, "format": fmt, "path": path}


def save_subtitles(path, cues):
    normalized = normalize_cues(cues)
    fmt = "vtt" if path.lower().endswith(".vtt") else "srt"
    text = write_vtt(normalized) if fmt == "vtt" else write_srt(normalized)

    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".ffgui-subs-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.replace(temporary, path)
    except OSError:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise

    return {"ok": True, "path": path, "count": len(normalized), "format": fmt}
