"""Localización de FFmpeg y detección real de aceleración por hardware."""

from __future__ import annotations

import os
import re
import shutil
import subprocess

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
EXE = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
PROBE_EXE = "ffprobe.exe" if os.name == "nt" else "ffprobe"
NULL_DEVICE = "NUL" if os.name == "nt" else "/dev/null"


def _run(exe, args, timeout=20):
    try:
        result = subprocess.run(
            [exe] + list(args),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, creationflags=CREATE_NO_WINDOW,
        )
        return result.returncode, result.stdout or "", result.stderr or ""
    except Exception as error:  # noqa: BLE001
        return -1, "", str(error)


def find_ffmpeg(app_root: str, settings: dict, search_roots=None):
    """Busca ffmpeg: ajuste guardado, carpetas junto al ejecutable y PATH."""
    candidates = []
    saved = (settings or {}).get("ffmpegPath")
    if saved:
        candidates.append(saved)

    roots = [app_root] + [root for root in (search_roots or []) if root]
    seen = set()
    for root in roots:
        if not root or root in seen:
            continue
        seen.add(root)
        candidates.append(os.path.join(root, "ffmpeg", "bin", EXE))
        candidates.append(os.path.join(root, "ffmpeg", EXE))
        candidates.append(os.path.join(root, "vendor", EXE))

    # Build de desarrollo junto al proyecto.
    candidates.append(os.path.join(app_root, "..", "ffmpeg-master-latest-win64-gpl", "bin", EXE))

    # Carpeta indicada por entorno (CI o instalaciones portables).
    configured_dir = os.environ.get("FFMPEG_DIR")
    if configured_dir:
        candidates.append(os.path.join(configured_dir, EXE))
        candidates.append(os.path.join(configured_dir, "bin", EXE))

    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return os.path.normpath(candidate)

    from_path = shutil.which(EXE)
    return os.path.normpath(from_path) if from_path else None


def ffprobe_beside(ffmpeg_path):
    if not ffmpeg_path:
        return None
    candidate = os.path.join(os.path.dirname(ffmpeg_path), PROBE_EXE)
    return candidate if os.path.isfile(candidate) else None


def ffmpeg_version(ffmpeg_path):
    if not ffmpeg_path:
        return None
    code, out, err = _run(ffmpeg_path, ["-hide_banner", "-version"], timeout=15)
    first = ((out or err).splitlines() or [""])[0].strip()
    return first or None


def list_encoders(ffmpeg_path) -> set:
    _, out, err = _run(ffmpeg_path, ["-hide_banner", "-encoders"], timeout=20)
    encoders = set()
    for line in (out + err).splitlines():
        match = re.match(r"^\s*[VAS][A-Z.]{5}\s+(\S+)", line)
        if match:
            encoders.add(match.group(1))
    return encoders


def trial_encode(ffmpeg_path, codec) -> bool:
    args = [
        "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=black:s=320x240:r=1",
        "-frames:v", "1",
        "-c:v", codec,
        "-f", "null", NULL_DEVICE,
    ]
    code, _, _ = _run(ffmpeg_path, args, timeout=10)
    return code == 0


def detect_hardware(ffmpeg_path) -> dict:
    encoders = list_encoders(ffmpeg_path)
    candidates = [
        "h264_nvenc", "hevc_nvenc", "av1_nvenc",
        "h264_qsv", "hevc_qsv", "av1_qsv",
        "h264_amf", "hevc_amf", "av1_amf",
    ]
    available = {}
    for codec in candidates:
        if codec not in encoders:
            available[codec] = {"present": False, "works": False}
            continue
        available[codec] = {"present": True, "works": trial_encode(ffmpeg_path, codec)}

    working = [codec for codec, data in available.items() if data["works"]]
    summary = "Solo CPU"
    if any(codec.endswith("_nvenc") for codec in working):
        summary = "GPU NVIDIA (NVENC)"
    elif any(codec.endswith("_qsv") for codec in working):
        summary = "GPU Intel (QuickSync)"
    elif any(codec.endswith("_amf") for codec in working):
        summary = "GPU AMD (AMF)"

    return {"available": available, "working": working, "summary": summary}
