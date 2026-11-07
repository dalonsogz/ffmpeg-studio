"""Catálogo de contenedores, codificadores y construcción de comandos."""

from __future__ import annotations

import os

from .timeutil import format_time

CONTAINERS = {
    "mp4": {
        "label": "MP4", "ext": "mp4", "kind": "video", "faststart": True,
        "video": ["libx264", "libx265", "libsvtav1", "h264_nvenc", "hevc_nvenc", "av1_nvenc",
                  "h264_qsv", "hevc_qsv", "av1_qsv", "h264_amf", "hevc_amf", "av1_amf", "copy"],
        "audio": ["aac", "libmp3lame", "ac3", "eac3", "libopus", "copy", "none"],
        "subtitles": "mov_text",
    },
    "mkv": {
        "label": "MKV", "ext": "mkv", "kind": "video", "faststart": False,
        "video": ["libx264", "libx265", "libsvtav1", "libvpx-vp9", "h264_nvenc", "hevc_nvenc", "av1_nvenc",
                  "h264_qsv", "hevc_qsv", "av1_qsv", "h264_amf", "hevc_amf", "av1_amf", "prores_ks", "copy"],
        "audio": ["aac", "libmp3lame", "ac3", "eac3", "libopus", "libvorbis", "flac", "pcm_s16le", "copy", "none"],
        "subtitles": "copy",
    },
    "mov": {
        "label": "MOV", "ext": "mov", "kind": "video", "faststart": True,
        "video": ["libx264", "libx265", "prores_ks", "h264_nvenc", "hevc_nvenc", "copy"],
        "audio": ["aac", "alac", "pcm_s16le", "copy", "none"],
        "subtitles": "mov_text",
    },
    "webm": {
        "label": "WebM", "ext": "webm", "kind": "video", "faststart": False,
        "video": ["libvpx-vp9", "libsvtav1", "av1_nvenc", "av1_qsv", "copy"],
        "audio": ["libopus", "libvorbis", "copy", "none"],
        "subtitles": "webvtt",
    },
    "avi": {
        "label": "AVI", "ext": "avi", "kind": "video", "faststart": False,
        "video": ["libx264", "libxvid", "mpeg4", "copy"],
        "audio": ["libmp3lame", "ac3", "pcm_s16le", "copy", "none"],
        "subtitles": None,
    },
    "gif": {"label": "GIF", "ext": "gif", "kind": "animation", "faststart": False,
            "video": ["gif"], "audio": ["none"], "subtitles": None},
    "mp3": {"label": "MP3", "ext": "mp3", "kind": "audio", "faststart": False,
            "video": ["none"], "audio": ["libmp3lame", "copy"], "subtitles": None},
    "m4a": {"label": "M4A", "ext": "m4a", "kind": "audio", "faststart": True,
            "video": ["none"], "audio": ["aac", "alac", "copy"], "subtitles": None},
    "wav": {"label": "WAV", "ext": "wav", "kind": "audio", "faststart": False,
            "video": ["none"], "audio": ["pcm_s16le", "pcm_s24le"], "subtitles": None},
    "flac": {"label": "FLAC", "ext": "flac", "kind": "audio", "faststart": False,
             "video": ["none"], "audio": ["flac"], "subtitles": None},
    "opus": {"label": "Opus", "ext": "opus", "kind": "audio", "faststart": False,
             "video": ["none"], "audio": ["libopus"], "subtitles": None},
    "jpg": {"label": "JPG", "ext": "jpg", "kind": "image", "faststart": False,
            "video": ["mjpeg"], "audio": ["none"], "subtitles": None},
    "png": {"label": "PNG", "ext": "png", "kind": "image", "faststart": False,
            "video": ["png"], "audio": ["none"], "subtitles": None},
    "webp": {"label": "WebP", "ext": "webp", "kind": "image", "faststart": False,
             "video": ["libwebp"], "audio": ["none"], "subtitles": None},
}

X264_PRESETS = ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"]
NVENC_PRESETS = ["p1", "p2", "p3", "p4", "p5", "p6", "p7"]

VIDEO_ENCODERS = {
    "libx264": {"label": "H.264 · x264 (CPU)", "family": "crf", "quality": [14, 32, 21],
                "pix_fmt": "yuv420p", "presets": X264_PRESETS, "default_preset": "medium"},
    "libx265": {"label": "H.265 · x265 (CPU)", "family": "crf", "quality": [16, 34, 24],
                "pix_fmt": "yuv420p", "presets": X264_PRESETS, "default_preset": "medium"},
    "libsvtav1": {"label": "AV1 · SVT-AV1 (CPU)", "family": "crf", "quality": [20, 40, 30],
                  "pix_fmt": "yuv420p", "presets": [str(n) for n in range(13, -1, -1)], "default_preset": "8"},
    "libvpx-vp9": {"label": "VP9 · libvpx (CPU)", "family": "crf", "quality": [20, 45, 32],
                   "pix_fmt": "yuv420p", "presets": [str(n) for n in range(8, -1, -1)], "default_preset": "4",
                   "extra_args": ["-b:v", "0", "-row-mt", "1"]},
    "h264_nvenc": {"label": "H.264 · NVIDIA NVENC", "family": "nvenc", "quality": [14, 34, 23],
                   "pix_fmt": "yuv420p", "presets": NVENC_PRESETS, "default_preset": "p5"},
    "hevc_nvenc": {"label": "H.265 · NVIDIA NVENC", "family": "nvenc", "quality": [16, 36, 26],
                   "pix_fmt": "yuv420p", "presets": NVENC_PRESETS, "default_preset": "p5"},
    "av1_nvenc": {"label": "AV1 · NVIDIA NVENC", "family": "nvenc", "quality": [18, 40, 30],
                  "pix_fmt": "yuv420p", "presets": NVENC_PRESETS, "default_preset": "p5"},
    "h264_qsv": {"label": "H.264 · Intel QuickSync", "family": "qsv", "quality": [14, 34, 23],
                 "pix_fmt": "nv12", "presets": X264_PRESETS, "default_preset": "medium"},
    "hevc_qsv": {"label": "H.265 · Intel QuickSync", "family": "qsv", "quality": [16, 36, 26],
                 "pix_fmt": "nv12", "presets": X264_PRESETS, "default_preset": "medium"},
    "av1_qsv": {"label": "AV1 · Intel QuickSync", "family": "qsv", "quality": [18, 40, 30],
                "pix_fmt": "nv12", "presets": ["veryfast", "fast", "medium", "slow"], "default_preset": "medium"},
    "h264_amf": {"label": "H.264 · AMD AMF", "family": "amf", "quality": [14, 34, 23],
                 "pix_fmt": "yuv420p", "presets": ["speed", "balanced", "quality"], "default_preset": "balanced"},
    "hevc_amf": {"label": "H.265 · AMD AMF", "family": "amf", "quality": [16, 36, 26],
                 "pix_fmt": "yuv420p", "presets": ["speed", "balanced", "quality"], "default_preset": "balanced"},
    "av1_amf": {"label": "AV1 · AMD AMF", "family": "amf", "quality": [18, 40, 30],
                "pix_fmt": "yuv420p", "presets": ["speed", "balanced", "quality"], "default_preset": "balanced"},
    "prores_ks": {"label": "ProRes 422 HQ", "family": "none", "quality": None, "pix_fmt": "yuv422p10le",
                  "presets": [], "default_preset": None, "extra_args": ["-profile:v", "3"]},
    "libxvid": {"label": "MPEG-4 · Xvid", "family": "qscale", "quality": [1, 10, 4], "pix_fmt": "yuv420p",
                "presets": [], "default_preset": None},
    "mpeg4": {"label": "MPEG-4", "family": "qscale", "quality": [1, 10, 4], "pix_fmt": "yuv420p",
              "presets": [], "default_preset": None},
    "mjpeg": {"label": "JPEG", "family": "qscale", "quality": [1, 16, 3], "pix_fmt": "yuvj420p",
              "presets": [], "default_preset": None},
    "png": {"label": "PNG", "family": "none", "quality": None, "pix_fmt": "rgba",
            "presets": [], "default_preset": None},
    "libwebp": {"label": "WebP", "family": "qscale", "quality": [10, 100, 80], "pix_fmt": "yuv420p",
                "presets": [], "default_preset": None},
    "gif": {"label": "GIF", "family": "none", "quality": None, "pix_fmt": None,
            "presets": [], "default_preset": None},
    "copy": {"label": "Sin recodificar (copia exacta)", "family": "copy", "quality": None, "pix_fmt": None,
             "presets": [], "default_preset": None},
    "none": {"label": "Sin vídeo", "family": "none", "quality": None, "pix_fmt": None,
             "presets": [], "default_preset": None},
}

AUDIO_ENCODERS = {
    "aac": {"label": "AAC", "bitrates": ["96k", "128k", "160k", "192k", "256k", "320k"], "default_bitrate": "160k"},
    "libmp3lame": {"label": "MP3", "bitrates": ["128k", "160k", "192k", "256k", "320k"], "default_bitrate": "192k"},
    "ac3": {"label": "AC-3", "bitrates": ["192k", "256k", "384k", "448k"], "default_bitrate": "384k"},
    "eac3": {"label": "E-AC-3", "bitrates": ["192k", "256k", "384k", "640k"], "default_bitrate": "384k"},
    "libopus": {"label": "Opus", "bitrates": ["64k", "96k", "128k", "160k", "192k"], "default_bitrate": "96k"},
    "libvorbis": {"label": "Vorbis", "bitrates": ["96k", "128k", "160k", "192k"], "default_bitrate": "160k"},
    "flac": {"label": "FLAC (sin pérdida)", "bitrates": [], "default_bitrate": None},
    "alac": {"label": "ALAC (sin pérdida)", "bitrates": [], "default_bitrate": None},
    "pcm_s16le": {"label": "PCM 16 bits", "bitrates": [], "default_bitrate": None},
    "pcm_s24le": {"label": "PCM 24 bits", "bitrates": [], "default_bitrate": None},
    "copy": {"label": "Copiar sin recodificar", "bitrates": [], "default_bitrate": None},
    "none": {"label": "Sin audio", "bitrates": [], "default_bitrate": None},
}


def encoder_info(codec: str) -> dict:
    return VIDEO_ENCODERS.get(codec, VIDEO_ENCODERS["copy"])


# Codificadores de hardware y su alternativa en CPU para reintentos.
SOFTWARE_FALLBACK = {
    "h264_nvenc": "libx264",
    "hevc_nvenc": "libx265",
    "av1_nvenc": "libsvtav1",
    "h264_qsv": "libx264",
    "hevc_qsv": "libx265",
    "av1_qsv": "libsvtav1",
    "h264_amf": "libx264",
    "hevc_amf": "libx265",
    "av1_amf": "libsvtav1",
    "h264_vaapi": "libx264",
    "hevc_vaapi": "libx265",
}


def software_fallback_codec(codec: str):
    """Devuelve el codificador de CPU equivalente, o None si no es de hardware."""
    return SOFTWARE_FALLBACK.get(codec)


def container_info(container: str) -> dict:
    return CONTAINERS.get(container, CONTAINERS["mp4"])


def compute_scale(media, max_width, max_height, swap=False):
    """Dimensiones destino calculadas en Python (sin expresiones de filtro)."""
    video = (media or {}).get("video") or {}
    width, height = video.get("width"), video.get("height")
    if not width or not height:
        return None
    if swap:
        width, height = height, width
    limit_w = int(max_width) if max_width and int(max_width) > 0 else width
    limit_h = int(max_height) if max_height and int(max_height) > 0 else height
    factor = min(limit_w / width, limit_h / height, 1.0)
    if factor >= 0.999:
        return None
    target_w = max(2, int(round(width * factor / 2)) * 2)
    target_h = max(2, int(round(height * factor / 2)) * 2)
    if target_w == width and target_h == height:
        return None
    return f"scale={target_w}:{target_h}:flags=lanczos"


def _quality_args(codec: str, options: dict):
    info = encoder_info(codec)
    value = options.get("quality")
    if value is None or info["family"] in ("none", "copy"):
        return []
    value = int(value)
    family = info["family"]
    if family == "crf":
        return ["-crf", str(value)]
    if family == "nvenc":
        return ["-rc", "vbr", "-cq", str(value), "-b:v", "0"]
    if family == "qsv":
        return ["-global_quality", str(value)]
    if family == "amf":
        return ["-rc", "cqp", "-qp_i", str(value), "-qp_p", str(value)]
    if family == "qscale":
        return ["-quality", str(value)] if codec == "libwebp" else ["-q:v", str(value)]
    return []


def _preset_args(codec: str, preset):
    info = encoder_info(codec)
    if not preset or not info["presets"]:
        return []
    if codec == "libvpx-vp9":
        return ["-cpu-used", str(preset)]
    return ["-preset", str(preset)]


def quote_arg(arg: str) -> str:
    text = str(arg)
    if all(ch.isalnum() or ch in "_./:=+-" for ch in text):
        return text
    return f'"{text}"'


def preview_of(args) -> str:
    return " ".join([quote_arg("ffmpeg.exe")] + [quote_arg(a) for a in args])


def _int_option(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def speed_filters(options):
    """Devuelve (filtros de vídeo, filtros de audio) para cambiar la velocidad."""
    speed = float(options.get("speed") or 1.0)
    if speed <= 0:
        speed = 1.0
    if abs(speed - 1.0) < 1e-9:
        return [], []

    video = [f"setpts=PTS/{speed:g}"]

    # atempo solo admite 0.5–2.0 por instancia: se encadena si hace falta.
    remaining = speed
    parts = []
    while remaining > 2.0 + 1e-9:
        parts.append(2.0)
        remaining /= 2.0
    while remaining < 0.5 - 1e-9:
        parts.append(0.5)
        remaining /= 0.5
    parts.append(round(remaining, 6))
    audio = [f"atempo={value:g}" for value in parts]
    return video, audio


def audio_filters_for(options):
    """Cadena de audio: velocidad, normalización EBU R128 y filtro libre."""
    filters = list(speed_filters(options)[1])
    if options.get("normalizeLoudness"):
        target = float(options.get("loudnessTarget") or -16)
        filters.append(f"loudnorm=I={target:g}:TP=-1.5:LRA=11")
    if options.get("audioFilter"):
        filters.append(options["audioFilter"])
    return filters


def framing_filters(options):
    """Recorte, rotación y volteo, en ese orden."""
    filters = []
    crop = options.get("crop") or {}
    left = max(0, int(crop.get("left") or 0))
    top = max(0, int(crop.get("top") or 0))
    right = max(0, int(crop.get("right") or 0))
    bottom = max(0, int(crop.get("bottom") or 0))
    if left or top or right or bottom:
        filters.append(f"crop=iw-{left}-{right}:ih-{top}-{bottom}:{left}:{top}")

    rotate = int(options.get("rotate") or 0)
    if rotate == 90:
        filters.append("transpose=1")
    elif rotate == 180:
        filters.extend(["hflip", "vflip"])
    elif rotate == 270:
        filters.append("transpose=2")

    flip = options.get("flip") or "none"
    if flip in ("h", "both"):
        filters.append("hflip")
    if flip in ("v", "both"):
        filters.append("vflip")
    return filters


def build_video_filters(media, options):
    filters = framing_filters(options)
    speed_video, _ = speed_filters(options)
    filters += speed_video

    rotate = int(options.get("rotate") or 0)
    scale = compute_scale(
        media, options.get("maxWidth"), options.get("maxHeight"),
        swap=rotate in (90, 270),
    )
    if scale:
        filters.append(scale)
    if options.get("filterChain"):
        filters.append(options["filterChain"])
    return filters


SHEET_GRIDS = {4: (2, 2), 6: (3, 2), 9: (3, 3), 12: (4, 3), 16: (4, 4)}


def sheet_grid(count: int):
    if count in SHEET_GRIDS:
        return SHEET_GRIDS[count]
    cols = max(1, int(round(count ** 0.5)))
    rows = max(1, -(-count // cols))
    return cols, rows


def build_sheet_commands(*, media, options, output_path):
    """Hoja de contactos: N fotogramas repartidos en una rejilla."""
    count = int(options.get("sheetCount") or 9)
    cols, rows = sheet_grid(count)
    width = int(options.get("sheetWidth") or 480)
    duration = float(media.get("duration") or 0)
    interval = duration / max(1, count) if duration > 0 else 1.0
    interval = max(interval, 0.05)

    chain = f"fps=1/{interval:.6f},scale={width}:-2:flags=lanczos,tile={cols}x{rows}"
    args = [
        "-hide_banner", "-nostats", "-progress", "pipe:1", "-loglevel", "warning", "-y",
        "-i", media["path"],
        "-vf", chain,
        "-frames:v", "1", "-update", "1",
        "-q:v", "3",
        output_path,
    ]
    return {"commands": [args], "preview": preview_of(args), "durations": [None], "grid": (cols, rows)}


def _finish(base_args, output_path, container, options, passlog_base=None):
    fast = ["-movflags", "+faststart"] if container.get("faststart") else []

    if not options.get("twoPass"):
        full = base_args + fast + [output_path]
        return {"commands": [full], "preview": preview_of(full)}

    log = passlog_base or "ffmpeg-pass"
    null_device = "NUL"
    pass1 = base_args + ["-passlogfile", log, "-pass", "1", "-f", "null", null_device]
    pass2 = base_args + fast + ["-passlogfile", log, "-pass", "2", output_path]
    return {
        "commands": [pass1, pass2],
        "preview": preview_of(pass1) + "\n\n" + preview_of(pass2),
    }


def build_job_commands(*, input_path, output_path, options, media, passlog_base=None):
    container = container_info(options.get("container", "mp4"))
    task = options.get("task", "video")

    args = ["-hide_banner", "-nostats", "-progress", "pipe:1", "-loglevel", "warning", "-y"]

    input_args = []
    duration_limit = None
    trim = options.get("trim") or {}
    if trim.get("enabled"):
        start = float(trim.get("start") or 0)
        end = trim.get("end")
        if start > 0:
            input_args += ["-ss", format_time(start)]
        if end is not None and float(end) > start:
            duration_limit = float(end) - start

    if task == "image":
        input_args += ["-ss", f"{float(options.get('imageTime') or 0):.3f}"]

    args += input_args + ["-i", input_path]
    if duration_limit is not None:
        args += ["-t", f"{duration_limit:.3f}"]

    if task == "audio":
        args.append("-vn")
        audio_codec = options.get("audioCodec", "aac")
        if audio_codec == "copy":
            args += ["-c:a", "copy"]
        else:
            args += ["-c:a", audio_codec]
            bitrate = options.get("audioBitrate") or AUDIO_ENCODERS.get(audio_codec, {}).get("default_bitrate")
            if bitrate:
                args += ["-b:a", bitrate]
        _, speed_audio = speed_filters(options)
        audio_filters = audio_filters_for(options)
        if audio_filters:
            args += ["-af", ",".join(audio_filters)]
        return _finish(args, output_path, container, options, passlog_base)

    if task == "image":
        args += ["-frames:v", "1", "-update", "1"]
        scale = compute_scale(media, options.get("maxWidth") or 320, None)
        if scale:
            args += ["-vf", scale]
        if options.get("container") == "jpg":
            args += ["-q:v", "3"]
        return _finish(args, output_path, container, options, passlog_base)

    if task == "gif":
        width = int(options.get("gifWidth") or 480)
        fps = int(options.get("gifFps") or 12)
        chain = options.get("filterChain") or (
            f"fps={fps},scale={width}:-2:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"
        )
        args += ["-vf", chain, "-an"]
        return _finish(args, output_path, container, options, passlog_base)

    video_codec = options.get("videoCodec") or "libx264"
    audio_codec = options.get("audioCodec") or "aac"
    is_remux = video_codec == "copy" and audio_codec == "copy"

    audio_track = _int_option(options.get("audioTrack"), -1)
    sub_track = options.get("subtitleTrack")
    if sub_track is None:
        sub_track = 0 if options.get("includeSubtitles") else -1
    sub_track = _int_option(sub_track, -1)
    subtitle_selected = sub_track >= 0
    needs_map = audio_track != -1 or subtitle_selected

    if is_remux and not needs_map:
        args += ["-map", "0", "-c", "copy"]
        if options.get("container") in ("mp4", "mov"):
            args += ["-map_chapters", "0"]
        return _finish(args, output_path, container, options, passlog_base)

    if needs_map:
        args += ["-map", "0:v:0"]
        if audio_codec != "none":
            if audio_track == -2:
                args += ["-map", "0:a"]
            elif audio_track >= 0:
                args += ["-map", f"0:a:{audio_track}"]
            else:
                args += ["-map", "0:a?"]
        if subtitle_selected:
            args += ["-map", f"0:s:{sub_track}"]

    if video_codec == "copy":
        args += ["-c:v", "copy"]
    elif video_codec == "none":
        args.append("-vn")
    else:
        args += ["-c:v", video_codec]
        if options.get("qualityMode") == "bitrate" and options.get("videoBitrate"):
            args += ["-b:v", options["videoBitrate"]]
        else:
            args += _quality_args(video_codec, options)
        args += _preset_args(video_codec, options.get("preset"))
        info = encoder_info(video_codec)
        if info.get("extra_args"):
            args += info["extra_args"]
        if info.get("pix_fmt"):
            args += ["-pix_fmt", info["pix_fmt"]]

        filters = build_video_filters(media, options)
        if filters:
            args += ["-vf", ",".join(filters)]

    fps = int(options.get("fps") or 0)
    if fps > 0 and video_codec not in ("copy", "none"):
        args += ["-r", str(fps)]

    if audio_codec == "none":
        args.append("-an")
    elif audio_codec == "copy":
        args += ["-c:a", "copy"]
    else:
        args += ["-c:a", audio_codec]
        if options.get("audioBitrate"):
            args += ["-b:a", options["audioBitrate"]]
        if options.get("audioChannels"):
            args += ["-ac", str(options["audioChannels"])]

    audio_filters = audio_filters_for(options)
    if audio_filters:
        args += ["-af", ",".join(audio_filters)]

    if subtitle_selected:
        if container.get("subtitles") == "mov_text":
            args += ["-c:s", "mov_text"]
        elif options.get("container") == "webm":
            args += ["-c:s", "webvtt"]
        else:
            args += ["-c:s", "copy"]
    elif not needs_map and not is_remux:
        args.append("-sn")

    if is_remux and options.get("container") in ("mp4", "mov"):
        args += ["-map_chapters", "0"]

    return _finish(args, output_path, container, options, passlog_base)


def validate_job(*, options, media, output_path, input_path):
    issues = []
    container = container_info(options.get("container", "mp4"))
    task = options.get("task", "video")

    if not media:
        return [{"level": "error", "message": "No se pudo leer el archivo de entrada."}]

    if output_path and input_path and output_path.lower() == input_path.lower():
        issues.append({"level": "error", "message": "La salida no puede sobrescribir el archivo de entrada."})

    if task == "audio":
        if not media.get("audios"):
            issues.append({"level": "error", "message": "El archivo no contiene pistas de audio."})
        if options.get("normalizeLoudness") and (options.get("audioCodec") or "aac") == "copy":
            issues.append({
                "level": "error",
                "message": "Normalizar el volumen requiere recodificar el audio: elija AAC, MP3 u otro códec.",
            })
        return issues

    if task in ("gif", "video") and not media.get("video"):
        issues.append({"level": "error", "message": "El archivo no contiene pista de vídeo."})

    if task == "image":
        if not media.get("video"):
            issues.append({"level": "error", "message": "El archivo no contiene pista de vídeo."})
        return issues

    if task == "video":
        codec = options.get("videoCodec") or "libx264"
        is_remux = codec == "copy" and (options.get("audioCodec") or "aac") == "copy"

        audio_track = _int_option(options.get("audioTrack"), -1)
        sub_track = options.get("subtitleTrack")
        if sub_track is None:
            sub_track = 0 if options.get("includeSubtitles") else -1
        sub_track = _int_option(sub_track, -1)
        needs_map = audio_track != -1 or sub_track >= 0

        if is_remux and not needs_map and options.get("container") in ("mp4", "mov") and media.get("subtitles"):
            if any(s.get("codec") != "mov_text" for s in media["subtitles"]):
                issues.append({
                    "level": "error",
                    "message": f"El contenedor {container['label']} no admite los subtítulos originales sin "
                               "convertirlos. Use MKV o desactive la copia exacta.",
                })

        if codec not in container["video"]:
            issues.append({
                "level": "error",
                "message": f"{container['label']} no admite el códec de vídeo «{encoder_info(codec)['label']}».",
            })

        if (options.get("audioCodec") or "aac") not in container["audio"]:
            issues.append({
                "level": "error",
                "message": f"{container['label']} no admite el códec de audio seleccionado.",
            })

        audios = media.get("audios") or []
        if audio_track >= 0 and audio_track >= len(audios):
            issues.append({"level": "error", "message": "La pista de audio seleccionada no existe."})

        subs = media.get("subtitles") or []
        if sub_track >= 0:
            if sub_track >= len(subs):
                issues.append({"level": "error",
                               "message": "La pista de subtítulos seleccionada no existe."})
            elif container.get("subtitles") is None:
                issues.append({"level": "error",
                               "message": f"{container['label']} no admite subtítulos."})
            elif container.get("subtitles") == "mov_text" and subs[sub_track].get("codec") in IMAGE_SUBTITLE_CODECS:
                issues.append({"level": "error",
                               "message": "Los subtítulos de imagen no se pueden incluir en MP4/MOV; use MKV."})

        if codec == "copy" and (options.get("maxWidth") or options.get("maxHeight")):
            if compute_scale(media, options.get("maxWidth"), options.get("maxHeight")):
                issues.append({
                    "level": "error",
                    "message": "No se puede cambiar la resolución sin recodificar el vídeo.",
                })

        if codec == "copy" and options.get("filterChain"):
            issues.append({"level": "error", "message": "Los filtros requieren recodificar el vídeo."})

        trim = options.get("trim") or {}
        if codec == "copy" and trim.get("enabled") and trim.get("mode") != "fast":
            issues.append({
                "level": "warn",
                "message": "El corte sin recodificar se ajusta al fotograma clave anterior.",
            })

        speed = float(options.get("speed") or 1.0)
        fps = int(options.get("fps") or 0)
        has_framing = bool(framing_filters(options))
        if codec == "copy":
            if abs(speed - 1.0) > 1e-9:
                issues.append({"level": "error",
                               "message": "Cambiar la velocidad requiere recodificar el vídeo."})
            if fps:
                issues.append({"level": "error",
                               "message": "Cambiar los fotogramas por segundo requiere recodificar el vídeo."})
            if has_framing:
                issues.append({"level": "error",
                               "message": "El encuadre (recorte, rotación o volteo) requiere recodificar el vídeo."})
        elif abs(speed - 1.0) > 1e-9 and (options.get("audioCodec") or "aac") == "copy":
            issues.append({
                "level": "error",
                "message": "Cambiar la velocidad requiere recodificar el audio: elija AAC, MP3 u otro códec.",
            })

        if options.get("normalizeLoudness") and (options.get("audioCodec") or "aac") == "copy":
            issues.append({
                "level": "error",
                "message": "Normalizar el volumen requiere recodificar el audio: elija AAC, MP3 u otro códec.",
            })

    trim = options.get("trim") or {}
    if trim.get("enabled"):
        start = trim.get("start")
        end = trim.get("end")
        if start is None or end is None:
            issues.append({"level": "error", "message": "Indique un inicio y un final válidos para el recorte."})
        elif float(end) <= float(start):
            issues.append({"level": "error", "message": "El final del recorte debe ser posterior al inicio."})
        elif media.get("duration") and float(end) > media["duration"] + 0.5:
            issues.append({
                "level": "warn",
                "message": "El final supera la duración del vídeo; se recortará al final real.",
            })

    return issues


def validate_sheet(*, media, options, output_path, input_path):
    """Valida la hoja de contactos."""
    issues = []
    if not media or not media.get("video"):
        return [{"level": "error", "message": "La hoja de contactos necesita un archivo de vídeo."}]
    if not media.get("duration"):
        issues.append({"level": "error",
                       "message": "No se pudo determinar la duración del vídeo para repartir los fotogramas."})
    if output_path and input_path and output_path.lower() == input_path.lower():
        issues.append({"level": "error", "message": "La salida no puede sobrescribir el archivo de entrada."})
    return issues


# ----------------------------------------------------------------------
# Concatenación (unir clips)
# ----------------------------------------------------------------------

CONCAT_MODES = {
    "copy": "Copia directa (rápida, sin pérdida)",
    "reencode": "Recomponer (admite resoluciones distintas)",
}

# Parámetros de normalización para poder unir clips heterogéneos.
CONCAT_AUDIO_RATE = 48000
CONCAT_AUDIO_CHANNELS = "stereo"


def concat_escape_path(path: str) -> str:
    """Formato de ruta para el demuxer concat: barras normales y comillas simples escapadas."""
    return path.replace("\\", "/").replace("'", "'\\''")


def write_concat_list(paths, list_path: str) -> str:
    lines = [f"file '{concat_escape_path(path)}'" for path in paths]
    with open(list_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    return list_path


def concat_target_size(medias, options):
    """Tamaño de lienzo común: el primer clip, recortado al límite elegido y sin ampliar."""
    first = (medias[0].get("video") or {}) if medias else {}
    width, height = first.get("width"), first.get("height")
    if not width or not height:
        return 1280, 720
    limit_w = options.get("maxWidth")
    limit_h = options.get("maxHeight")
    if limit_w and limit_h:
        factor = min(int(limit_w) / width, int(limit_h) / height, 1.0)
        width = max(2, int(round(width * factor / 2)) * 2)
        height = max(2, int(round(height * factor / 2)) * 2)
    return int(width), int(height)


def concat_target_fps(medias) -> float:
    values = [(m.get("video") or {}).get("fps") for m in medias]
    values = [float(v) for v in values if v]
    if not values:
        return 30.0
    return round(min(max(max(values), 10.0), 60.0), 3)


def _format_fps(fps: float) -> str:
    return f"{fps:.3f}".rstrip("0").rstrip(".")


def build_concat_commands(*, inputs, output_path, options, medias, list_path=None, passlog_base=None):
    """Construye la unión de clips por copia directa o recomponiendo un lienzo común."""
    container = container_info(options.get("container", "mp4"))
    mode = options.get("concatMode", "copy")
    args = ["-hide_banner", "-nostats", "-progress", "pipe:1", "-loglevel", "warning", "-y"]

    if mode == "copy":
        if not list_path:
            raise ValueError("La unión por copia necesita un archivo de lista.")
        args += ["-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy"]
        return _finish(args, output_path, container, {"twoPass": False}, passlog_base)

    # ---- Recomposición: normalizar cada clip y concatenar con el filtro concat ----
    target_w, target_h = concat_target_size(medias, options)
    fps = concat_target_fps(medias)
    has_audio = any(m.get("audios") for m in medias)

    extra_inputs = []
    audio_source = {}
    next_index = len(medias)
    for index, media in enumerate(medias):
        if media.get("audios"):
            audio_source[index] = index
        elif has_audio:
            duration = media.get("duration") or 5
            extra_inputs.append(([
                "-f", "lavfi", "-t", f"{float(duration):.3f}",
                "-i", f"anullsrc=channel_layout={CONCAT_AUDIO_CHANNELS}:sample_rate={CONCAT_AUDIO_RATE}",
            ], next_index))
            audio_source[index] = next_index
            next_index += 1

    for path in inputs:
        args += ["-i", path]
    for extra, _ in extra_inputs:
        args += extra

    chains = []
    video_labels = []
    audio_labels = []
    for index in range(len(medias)):
        chains.append(
            f"[{index}:v]scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
            f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={_format_fps(fps)},"
            f"format=yuv420p,setpts=PTS-STARTPTS[v{index}]"
        )
        video_labels.append(f"[v{index}]")
        if has_audio:
            source = audio_source[index]
            chains.append(
                f"[{source}:a]aresample={CONCAT_AUDIO_RATE},"
                f"aformat=sample_fmts=fltp:channel_layouts={CONCAT_AUDIO_CHANNELS},"
                f"asetpts=PTS-STARTPTS[a{index}]"
            )
            audio_labels.append(f"[a{index}]")

    count = len(medias)
    transition = (options.get("concatTransition") or "none").lower()
    fade = float(options.get("concatTransitionDuration") or 1.0)

    if transition == "fade" and count > 1:
        durations = [float(m.get("duration") or 0) for m in medias]
        if any(d <= 0 for d in durations):
            raise ValueError("Para usar fundidos, todos los clips deben declarar duración.")
        fade = max(0.1, min(fade, min(durations) - 0.05))

        current_video = "v0"
        acc = durations[0]
        for index in range(1, count):
            offset = max(0.0, acc - fade)
            label = f"xv{index}"
            chains.append(
                f"[{current_video}][v{index}]xfade=transition=fade:"
                f"duration={fade:.3f}:offset={offset:.3f}[{label}]"
            )
            current_video = label
            acc = acc + durations[index] - fade

        if has_audio:
            current_audio = "a0"
            for index in range(1, count):
                label = f"xa{index}"
                chains.append(
                    f"[{current_audio}][a{index}]acrossfade=d={fade:.3f}:c1=tri:c2=tri[{label}]"
                )
                current_audio = label
            maps = ["-map", f"[{current_video}]", "-map", f"[{current_audio}]"]
        else:
            maps = ["-map", f"[{current_video}]", "-an"]
    elif has_audio:
        streams = "".join(f"{video_labels[i]}{audio_labels[i]}" for i in range(count))
        chains.append(f"{streams}concat=n={count}:v=1:a=1[v][a]")
        maps = ["-map", "[v]", "-map", "[a]"]
    else:
        streams = "".join(video_labels)
        chains.append(f"{streams}concat=n={count}:v=1:a=0[v]")
        maps = ["-map", "[v]", "-an"]

    args += ["-filter_complex", ";".join(chains)] + maps

    codec = options.get("videoCodec") or "libx264"
    if codec in ("copy", "none"):
        codec = "libx264"
    args += ["-c:v", codec]
    if options.get("qualityMode") == "bitrate" and options.get("videoBitrate"):
        args += ["-b:v", options["videoBitrate"]]
    else:
        args += _quality_args(codec, options)
    args += _preset_args(codec, options.get("preset"))
    info = encoder_info(codec)
    if info.get("extra_args"):
        args += info["extra_args"]

    if has_audio:
        audio_codec = options.get("audioCodec") or "aac"
        if audio_codec in ("none", "copy"):
            audio_codec = "aac"
        args += ["-c:a", audio_codec]
        bitrate = options.get("audioBitrate") or AUDIO_ENCODERS.get(audio_codec, {}).get("default_bitrate")
        if bitrate:
            args += ["-b:a", bitrate]
        args += ["-ac", str(2)]

    return _finish(args, output_path, container, {"twoPass": False}, passlog_base)


def _stream_signature(media):
    video = media.get("video") or {}
    audio = (media.get("audios") or [None])[0]
    return {
        "videoCodec": video.get("codec"),
        "width": video.get("width"),
        "height": video.get("height"),
        "pixFmt": video.get("pixFmt"),
        "audioCodec": (audio or {}).get("codec"),
        "sampleRate": (audio or {}).get("sampleRate"),
        "channels": (audio or {}).get("channels"),
    }


def validate_concat(*, inputs, options, medias, output_path):
    issues = []
    container = container_info(options.get("container", "mp4"))
    mode = options.get("concatMode", "copy")

    if len(medias) < 2:
        issues.append({"level": "error", "message": "Para unir hacen falta al menos dos clips."})
        return issues

    for media in medias:
        if not media.get("video"):
            issues.append({
                "level": "error",
                "message": f"«{media.get('name')}» no tiene pista de vídeo y no se puede unir como clip.",
            })

    lowered = {os.path.normcase(os.path.abspath(p)) for p in inputs}
    if output_path and os.path.normcase(os.path.abspath(output_path)) in lowered:
        issues.append({"level": "error", "message": "La salida no puede sobrescribir uno de los clips de entrada."})

    if mode == "copy":
        if (options.get("concatTransition") or "none") != "none":
            issues.append({
                "level": "error",
                "message": "Los fundidos requieren el modo «Recomponer».",
            })
        base = _stream_signature(medias[0])
        for media in medias[1:]:
            signature = _stream_signature(media)
            differences = [key for key in base if base[key] != signature[key]]
            if differences:
                issues.append({
                    "level": "error",
                    "message": f"«{media.get('name')}» no coincide con el primer clip "
                               f"({', '.join(differences)}). Use «Recomponer» para mezclar formatos.",
                })
        input_codec = (medias[0].get("video") or {}).get("codec")
        if options.get("container") == "mp4" and input_codec not in ("h264", "hevc", "av1", "mpeg4"):
            issues.append({
                "level": "warn",
                "message": f"El códec {input_codec} puede no ser compatible con MP4 al copiar; "
                           "si falla, use MKV o el modo Recomponer.",
            })
    else:
        if any(media.get("duration") is None for media in medias):
            issues.append({
                "level": "warn",
                "message": "Algún clip no declara duración; el audio de relleno podría quedar descuadrado.",
            })
        if options.get("videoCodec") == "copy":
            issues.append({
                "level": "warn",
                "message": "El modo Recomponer recodifica: se usará H.264 en lugar de copiar.",
            })
        if (options.get("concatTransition") or "none") == "fade":
            fade = float(options.get("concatTransitionDuration") or 1.0)
            if any((media.get("duration") or 0) <= fade for media in medias):
                issues.append({
                    "level": "warn",
                    "message": f"Algún clip dura menos que el fundido ({fade:g} s); se acortará el fundido.",
                })

    if any(not media.get("audios") for media in medias):
        issues.append({
            "level": "warn",
            "message": "Algún clip no tiene audio: se añadirá silencio en ese tramo."
            if mode != "copy" else "Algún clip no tiene audio y el modo copia no puede añadirlo.",
        })

    total = sum((media.get("duration") or 0) for media in medias)
    if total > 0:
        issues.append({"level": "info", "message": f"Duración total resultante: {total:.1f} s"})

    return issues


CAPTURE_SOURCES = {
    "screen": "Pantalla completa",
    "window": "Una ventana",
    "camera": "Cámara / webcam",
}


def build_capture_commands(*, options, output_path):
    """Captura de escritorio, ventana o webcam con gdigrab/dshow."""
    container = container_info(options.get("container", "mp4"))
    source = options.get("captureSource") or "screen"
    fps = int(options.get("captureFps") or 30)
    duration = float(options.get("captureDuration") or 0)

    args = ["-hide_banner", "-nostats", "-progress", "pipe:1", "-loglevel", "warning", "-y"]

    if source == "window":
        title = (options.get("captureTitle") or "").strip()
        args += ["-f", "gdigrab", "-framerate", str(fps), "-i", f"title={title}"]
    elif source == "camera":
        device = (options.get("captureDevice") or "").strip()
        args += ["-f", "dshow", "-framerate", str(fps), "-i", f"video={device}"]
    else:
        args += ["-f", "gdigrab", "-framerate", str(fps), "-i", "desktop"]

    if duration > 0:
        args += ["-t", f"{duration:.1f}"]

    args += [
        "-c:v", "libx264", "-preset", "veryfast",
        "-crf", str(int(options.get("quality") or 23)),
        "-pix_fmt", "yuv420p",
    ]
    if container.get("faststart"):
        args += ["-movflags", "+faststart"]
    args.append(output_path)

    return {"commands": [args], "preview": preview_of(args)}


def validate_capture(*, options, output_path=None):
    issues = []
    source = options.get("captureSource") or "screen"
    if source == "window" and not (options.get("captureTitle") or "").strip():
        issues.append({"level": "error", "message": "Escribe el título de la ventana que quieres grabar."})
    if source == "camera" and not (options.get("captureDevice") or "").strip():
        issues.append({"level": "error", "message": "Escribe el nombre del dispositivo de cámara (por ejemplo «HD WebCam»)."})
    try:
        duration = float(options.get("captureDuration") or 0)
    except (TypeError, ValueError):
        duration = -1
    if duration < 0:
        issues.append({"level": "error", "message": "La duración de la grabación no es válida."})
    if not (5 <= int(options.get("captureFps") or 30) <= 60):
        issues.append({"level": "error", "message": "Los fps de captura deben estar entre 5 y 60."})
    return issues


# ----------------------------------------------------------------------
# Subtítulos (extraer, incrustar y quemar)
# ----------------------------------------------------------------------

SUBTITLE_MODES = {
    "extract": "Extraer a un archivo",
    "mux": "Incrustar en el vídeo",
    "burn": "Quemar en la imagen",
}

SUBTITLE_FORMATS = {
    "srt": "SubRip (.srt)",
    "ass": "ASS (.ass)",
    "vtt": "WebVTT (.vtt)",
    "sup": "PGS/DVD (.sup)",
}

SUBTITLE_LANGUAGES = {
    "spa": "Español",
    "eng": "Inglés",
    "fra": "Francés",
    "deu": "Alemán",
    "ita": "Italiano",
    "por": "Portugués",
    "rus": "Ruso",
    "jpn": "Japonés",
    "zho": "Chino",
    "ara": "Árabe",
}

BURN_FONTS = ["Arial", "Segoe UI", "Verdana", "Tahoma", "Georgia", "Trebuchet MS", "Impact"]

BURN_COLORS = {
    "blanco": "&H00FFFFFF",
    "amarillo": "&H0000FFFF",
    "cian": "&H00FFFF00",
    "verde": "&H0000FF00",
}

BURN_ALIGNMENTS = {"abajo": 2, "centro": 5, "arriba": 8}

IMAGE_SUBTITLE_CODECS = {"hdmv_pgs_subtitle", "dvd_subtitle", "dvb_subtitle", "xsub"}

_SUB_CODEC_BY_FORMAT = {"srt": "srt", "ass": "ass", "vtt": "webvtt", "sup": "copy"}

_MUX_SUB_CODEC = {"mp4": "mov_text", "mov": "mov_text", "mkv": "copy", "webm": "webvtt"}

_CONTAINER_SAFE_AUDIO = {"aac", "mp3", "ac3", "eac3", "alac", "pcm_s16le", "pcm_s24le"}


def _escape_subtitle_path(path: str) -> str:
    """Ruta para el filtro subtitles: absoluta, barras normales y ':' escapado."""
    return str(path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def burn_style_string(style) -> str:
    style = style or {}
    font = style.get("font") or "Arial"
    size = int(style.get("size") or 24)
    color = BURN_COLORS.get(style.get("color") or "blanco", BURN_COLORS["blanco"])
    position = BURN_ALIGNMENTS.get(style.get("position") or "abajo", 2)
    outline = 2 if style.get("outline", True) else 0
    bold = -1 if style.get("bold") else 0
    margin = 32 if position == 2 else (24 if position == 8 else 0)
    return (
        f"FontName={font},FontSize={size},PrimaryColour={color},Outline={outline},"
        f"Shadow=0,MarginV={margin},Alignment={position},Bold={bold}"
    )


def subtitle_filter(path: str, style) -> str:
    return f"subtitles=filename='{_escape_subtitle_path(path)}':force_style='{burn_style_string(style)}'"


def build_subtitle_commands(*, media, options, output_path, extraction_path=None):
    """Comandos de subtítulos. La extracción previa (al quemar una pista) va como primer comando."""
    mode = options.get("subsMode", "extract")
    container = container_info(options.get("container", "mp4"))
    stream_index = int(options.get("subtitleStream") or 0)
    subs = media.get("subtitles") or []
    global_args = ["-hide_banner", "-nostats", "-progress", "pipe:1", "-loglevel", "warning", "-y"]

    if mode == "extract":
        fmt = (options.get("subtitleFormat") or "srt").lower()
        codec = _SUB_CODEC_BY_FORMAT.get(fmt, "srt")
        args = global_args + [
            "-i", media["path"],
            "-map", f"0:s:{stream_index}",
            "-c:s", codec,
            output_path,
        ]
        return {"commands": [args], "preview": preview_of(args), "durations": [None]}

    if mode == "mux":
        subtitle_file = options.get("subtitleFile")
        new_index = len(subs)
        sub_codec = _MUX_SUB_CODEC.get(options.get("container"), "copy")
        args = global_args + [
            "-i", media["path"],
            "-i", subtitle_file,
            "-map", "0",
            "-map", "1:0",
            "-c", "copy",
            "-c:s", sub_codec,
        ]
        language = options.get("subtitleLanguage")
        title = options.get("subtitleTitle")
        if language:
            args += [f"-metadata:s:s:{new_index}", f"language={language}"]
        if title:
            args += [f"-metadata:s:s:{new_index}", f"title={title}"]
        if options.get("subtitleDefault"):
            args += [f"-disposition:s:{new_index}", "default"]
        args.append(output_path)
        return {"commands": [args], "preview": preview_of(args), "durations": [None]}

    # ---- Quemar ----
    commands = []
    durations = []
    subtitle_path = options.get("subtitleFile")

    if not subtitle_path and extraction_path:
        source_codec = (subs[stream_index].get("codec") if stream_index < len(subs) else "") or "subrip"
        extract_format = "ass" if source_codec == "ass" else "srt"
        extract_args = global_args + [
            "-i", media["path"],
            "-map", f"0:s:{stream_index}",
            "-c:s", _SUB_CODEC_BY_FORMAT[extract_format],
            extraction_path,
        ]
        commands.append(extract_args)
        durations.append(1)
        subtitle_path = extraction_path

    video_codec = options.get("videoCodec") or "libx264"
    if video_codec in ("copy", "none"):
        video_codec = "libx264"

    audio_codec = "copy"
    source_audio = ((media.get("audios") or [{}])[0]).get("codec")
    if options.get("container") in ("mp4", "mov") and source_audio not in _CONTAINER_SAFE_AUDIO:
        audio_codec = "aac"

    burn_args = global_args + [
        "-i", media["path"],
        "-vf", subtitle_filter(subtitle_path, options.get("burnStyle")),
        "-c:v", video_codec,
    ]
    burn_args += _quality_args(video_codec, options)
    burn_args += _preset_args(video_codec, options.get("preset"))
    info = encoder_info(video_codec)
    if info.get("pix_fmt"):
        burn_args += ["-pix_fmt", info["pix_fmt"]]
    burn_args += ["-c:a", audio_codec, "-sn"]
    commands.append(burn_args + [output_path])
    durations.append(media.get("duration"))

    return {"commands": commands, "preview": "\n\n".join(preview_of(c) for c in commands), "durations": durations}


def validate_subtitles(*, media, options, output_path, input_path):
    issues = []
    mode = options.get("subsMode", "extract")
    container = container_info(options.get("container", "mp4"))
    subs = (media or {}).get("subtitles") or []
    stream_index = int(options.get("subtitleStream") or 0)
    subtitle_file = options.get("subtitleFile")

    if not media:
        return [{"level": "error", "message": "No se pudo leer el archivo de entrada."}]

    if output_path and input_path and output_path.lower() == input_path.lower():
        issues.append({"level": "error", "message": "La salida no puede sobrescribir el archivo de entrada."})

    if mode == "extract":
        if not subs:
            issues.append({"level": "error", "message": "El archivo no contiene pistas de subtítulos."})
            return issues
        if stream_index >= len(subs):
            issues.append({"level": "error", "message": "La pista de subtítulos seleccionada no existe."})
            return issues
        codec = subs[stream_index].get("codec")
        fmt = (options.get("subtitleFormat") or "srt").lower()
        if codec in IMAGE_SUBTITLE_CODECS and fmt != "sup":
            issues.append({
                "level": "error",
                "message": "Los subtítulos de imagen (PGS/DVD) no se pueden convertir a texto. "
                           "Extraiga en formato .sup.",
            })
        if codec not in IMAGE_SUBTITLE_CODECS and fmt == "sup":
            issues.append({
                "level": "error",
                "message": "El formato .sup solo sirve para subtítulos de imagen. Elija .srt, .ass o .vtt.",
            })
        return issues

    if mode == "mux":
        if not subtitle_file:
            issues.append({"level": "error", "message": "Seleccione un archivo de subtítulos para incrustar."})
        elif not os.path.isfile(subtitle_file):
            issues.append({"level": "error", "message": f"No se encuentra el archivo «{subtitle_file}»."})
        if container.get("subtitles") is None:
            issues.append({"level": "error", "message": f"{container['label']} no admite subtítulos."})
        if options.get("container") in ("mp4", "mov"):
            if any(s.get("codec") in IMAGE_SUBTITLE_CODECS for s in subs):
                issues.append({
                    "level": "error",
                    "message": "El vídeo tiene subtítulos de imagen, que MP4/MOV no admiten. Use MKV.",
                })
            if subtitle_file and subtitle_file.lower().endswith((".ass", ".ssa")):
                issues.append({
                    "level": "warn",
                    "message": "Al pasar ASS a MP4 se pierden estilos y posiciones; se convertirá a texto plano.",
                })
        return issues

    # Quemar
    if not media.get("video"):
        issues.append({"level": "error", "message": "El archivo no contiene pista de vídeo."})
    if not subtitle_file and not subs:
        issues.append({"level": "error", "message": "Seleccione un archivo o una pista de subtítulos incrustada."})
    if subtitle_file and not os.path.isfile(subtitle_file):
        issues.append({"level": "error", "message": f"No se encuentra el archivo «{subtitle_file}»."})
    if not subtitle_file and stream_index >= len(subs):
        issues.append({"level": "error", "message": "La pista de subtítulos seleccionada no existe."})
    if container.get("kind") != "video":
        issues.append({"level": "error", "message": "Para quemar subtítulos hace falta un contenedor de vídeo."})
    return issues
