"""Traducción de errores de FFmpeg a mensajes comprensibles."""

from __future__ import annotations

import re

RULES = [
    (re.compile(r"no such file or directory|the system cannot find the file", re.I),
     "No se encuentra un archivo o una ruta. Revisa la ruta de entrada, la carpeta de salida "
     "o los archivos de subtítulos."),
    (re.compile(r"moov atom not found|invalid data found when processing input", re.I),
     "El archivo de entrada está incompleto, dañado o no es realmente un vídeo."),
    (re.compile(r"unknown encoder|encoder .* not found|unknown codec", re.I),
     "Ese códec no existe en la build de FFmpeg instalada. Prueba con otro códec o actualiza FFmpeg."),
    (re.compile(r"does not contain any stream|matches no streams", re.I),
     "La selección de pistas quedó vacía: el archivo no tiene la pista que se intentó usar."),
    (re.compile(r"permission denied|access is denied", re.I),
     "Windows ha denegado el acceso al archivo. Puede estar abierto en otro programa o "
     "protegido por el antivirus."),
    (re.compile(r"no space left|not enough space", re.I), "No hay espacio suficiente en el disco de destino."),
    (re.compile(r"already exists\. overwrite|file .* already exists", re.I),
     "El archivo de salida ya existe y no se permite sobrescribirlo."),
    (re.compile(r"invalid argument|error parsing|unable to parse", re.I),
     "Algún parámetro o filtro tiene un valor no válido. Revisa la configuración avanzada."),
    (re.compile(r"cannot open|error opening output", re.I),
     "No se pudo crear el archivo de salida. Comprueba la carpeta de destino y sus permisos."),
    (re.compile(r"hwaccel|nvenc|qsv|amf|cuda|device not found", re.I),
     "La aceleración por hardware no está disponible en este equipo. Prueba a codificar con la CPU."),
    (re.compile(r"subtitle|libass", re.I),
     "Problema con los subtítulos: formato no compatible o ruta no accesible desde el filtro."),
    (re.compile(r"conversion failed", re.I),
     "La conversión falló. Suele deberse a una combinación de códec y contenedor no válida."),
]

CODE_HINTS = {
    -1: "FFmpeg terminó con un error genérico.",
    -2: "No se encontró un archivo o ruta.",
    -5: "Error de entrada/salida (disco, permisos o archivo bloqueado).",
    -13: "Permiso denegado.",
    -22: "Argumento no válido (parámetro o filtro).",
    -28: "Disco lleno.",
    -1313558101: "Dispositivo de hardware no disponible.",
}

HARDWARE_FAILURE = re.compile(
    r"nvenc|qsv|amf|vaapi|cuda|d3d11|d3d12|vulkan|openencodesession|no capable devices|"
    r"device not found|hardware",
    re.IGNORECASE,
)


def looks_like_hardware_failure(log_lines, error=None) -> bool:
    """¿El fallo apunta a la GPU y merece un reintento en CPU?"""
    if HARDWARE_FAILURE.search("\n".join(log_lines or [])):
        return True
    if error and "hardware" in str(error.get("title", "")).lower():
        return True
    return False


def _last_meaningful(log_lines):
    for line in reversed(log_lines):
        text = str(line).strip()
        if text and not re.match(r"^(frame=|fps=|bitrate=|total_size=|out_time=|speed=|progress=|"
                                 r"dup_frames=|drop_frames=)", text):
            return text[:400]
    return ""


def explain_failure(code, log_lines) -> dict:
    text = "\n".join(log_lines or [])
    for pattern, message in RULES:
        if pattern.search(text):
            return {"title": message, "detail": _last_meaningful(log_lines)}

    signed = int(code) if code is not None else 0
    if signed > 2 ** 31:
        signed -= 2 ** 32
    hint = CODE_HINTS.get(signed) or CODE_HINTS.get(int(code or 0))
    return {
        "title": hint or "FFmpeg no pudo completar la operación.",
        "detail": _last_meaningful(log_lines),
    }
