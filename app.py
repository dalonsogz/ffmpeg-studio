"""FFmpeg Studio — front-end de escritorio para FFmpeg.

Arranque:  python app.py [archivos...]
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import uuid

import webview

from core.command import (
    AUDIO_ENCODERS,
    BURN_ALIGNMENTS,
    BURN_COLORS,
    BURN_FONTS,
    CAPTURE_SOURCES,
    CONCAT_MODES,
    CONTAINERS,
    SUBTITLE_FORMATS,
    SUBTITLE_LANGUAGES,
    SUBTITLE_MODES,
    VIDEO_ENCODERS,
    build_capture_commands,
    build_concat_commands,
    build_job_commands,
    build_sheet_commands,
    build_subtitle_commands,
    container_info,
    software_fallback_codec,
    validate_capture,
    validate_concat,
    validate_job,
    validate_sheet,
    validate_subtitles,
    write_concat_list,
)
from core.storage import estimate_output_bytes, has_space, space_error_message
from core.subtitles import load_subtitles, save_subtitles
from core.ffmpeg import detect_hardware, ffmpeg_version, ffprobe_beside, find_ffmpeg
from core.options import default_options
from core.presets import load_presets
from core.probe import probe_file
from core.queue import JobQueue
from core.runner import JobRunner
from core.settings import load_settings, save_settings, settings_path

FROZEN = bool(getattr(sys, "frozen", False))
if FROZEN:
    # En un ejecutable, los recursos viven en _MEIPASS y el .exe en su carpeta.
    RESOURCE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    RESOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
    APP_DIR = RESOURCE_DIR

WEB_DIR = os.path.join(RESOURCE_DIR, "web")
PRESETS_FILE = os.path.join(RESOURCE_DIR, "presets.json")

# La ventana se guarda en una variable de módulo (no como atributo del objeto
# expuesto a JavaScript) para que el puente no intente serializarla.
_WINDOW = None


def _window():
    return _WINDOW

MEDIA_TYPES = (
    "Multimedia (*.mp4;*.mkv;*.mov;*.avi;*.webm;*.m4v;*.wmv;*.flv;*.ts;*.mts;*.mpg;*.mpeg;*.3gp;*.ogv;"
    "*.mp3;*.wav;*.flac;*.m4a;*.aac;*.ogg;*.opus;*.wma;*.jpg;*.jpeg;*.png;*.webp;*.gif;*.bmp;*.tif;*.tiff)",
    "Todos los archivos (*.*)",
)


class Api:
    """Métodos expuestos a JavaScript a través de window.pywebview.api."""

    def __init__(self, settings_file=None, enable_hardware_detection=True, restore_queue=False):
        self.settings = load_settings(settings_file)
        self.settings_file = settings_file or settings_path()
        self.queue_file = os.path.join(os.path.dirname(self.settings_file), "queue.json")
        self.restored_pending = 0
        self.presets = load_presets(PRESETS_FILE)

        self.ffmpeg = find_ffmpeg(APP_DIR, self.settings, search_roots=[RESOURCE_DIR])
        saved_probe = self.settings.get("ffprobePath")
        self.ffprobe = saved_probe if saved_probe and os.path.isfile(saved_probe) else ffprobe_beside(self.ffmpeg)
        self.version = None

        self.hardware = None
        self._hw_lock = threading.Lock()
        self._hw_thread = None

        self.runner = JobRunner(self.ffmpeg or "ffmpeg")
        self.queue = JobQueue(self.runner, on_change=self._save_queue)
        if restore_queue:
            self._restore_queue()

        self.initial = [path for path in sys.argv[1:] if os.path.isfile(path)]

        if self.ffmpeg:
            self.version = ffmpeg_version(self.ffmpeg)
        if enable_hardware_detection:
            self._start_hardware_detection()

    # ------------------------------------------------------------------
    # Hardware
    # ------------------------------------------------------------------
    def _hardware_key(self):
        if not self.ffmpeg:
            return None
        try:
            stat = os.stat(self.ffmpeg)
            return f"{self.ffmpeg}|{stat.st_size}|{int(stat.st_mtime)}"
        except OSError:
            return self.ffmpeg

    def _start_hardware_detection(self, force=False):
        if not self.ffmpeg:
            return
        thread = threading.Thread(target=self._detect_hardware, args=(force,), daemon=True)
        self._hw_thread = thread
        thread.start()

    def _detect_hardware(self, force):
        key = self._hardware_key()
        cached = self.settings.get("hardwareCache") or {}
        if not force and cached.get("key") == key and cached.get("data"):
            with self._hw_lock:
                self.hardware = cached["data"]
            return
        data = detect_hardware(self.ffmpeg)
        with self._hw_lock:
            self.hardware = data
        self.settings["hardwareCache"] = {"key": key, "data": data}
        save_settings(self.settings, self.settings_file)

    def hardware_state(self):
        with self._hw_lock:
            return self.hardware

    def redetect_hardware(self):
        if not self.ffmpeg:
            return None
        data = detect_hardware(self.ffmpeg)
        with self._hw_lock:
            self.hardware = data
        self.settings["hardwareCache"] = {"key": self._hardware_key(), "data": data}
        save_settings(self.settings, self.settings_file)
        return data

    # ------------------------------------------------------------------
    # Persistencia de la cola
    # ------------------------------------------------------------------
    def _save_queue(self, state):
        try:
            os.makedirs(os.path.dirname(self.queue_file), exist_ok=True)
            temporary = f"{self.queue_file}.tmp"
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump(state, handle, ensure_ascii=False, indent=1)
            os.replace(temporary, self.queue_file)
        except OSError:
            pass

    def _restore_queue(self):
        """Recupera pendientes (reconstruidos) e historial de la sesión anterior."""
        if not os.path.isfile(self.queue_file):
            return
        try:
            with open(self.queue_file, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return

        jobs = []
        for spec in data.get("pending") or []:
            output = spec.get("output")
            if not output:
                continue
            options = {**default_options(), **(spec.get("options") or {})}
            try:
                if options.get("task") == "capture":
                    built = self._build_capture_job(
                        options, os.path.dirname(output), prepare=True, output_override=output,
                    )
                else:
                    inputs = [path for path in (spec.get("inputs") or []) if os.path.isfile(path)]
                    if not inputs:
                        continue
                    built = self._build_job(
                        inputs, options, os.path.dirname(output),
                        prepare=True, output_override=output,
                    )
            except Exception:  # noqa: BLE001
                continue
            if not built.get("ok"):
                continue
            job = built["job"]
            job["status"] = "pending"
            jobs.append(job)
            self.restored_pending += 1

        for entry in data.get("history") or []:
            output = entry.get("output")
            if not output:
                continue
            jobs.append({
                "id": entry.get("id") or str(uuid.uuid4()),
                "input": "",
                "inputs": [],
                "inputName": entry.get("inputName") or os.path.basename(output),
                "clipCount": 1,
                "output": output,
                "task": "history",
                "container": "",
                "label": entry.get("label") or "Trabajo anterior",
                "commands": [],
                "duration": None,
                "status": entry.get("status") or "done",
                "percent": 100 if entry.get("status") == "done" else 0,
                "error": entry.get("error"),
                "finishedAt": entry.get("finishedAt"),
                "logTail": [],
                "pass": 1,
                "passCount": 0,
            })

        if jobs:
            with self.queue.lock:
                self.queue.jobs.extend(jobs)
            self.queue._notify_change()

    # ------------------------------------------------------------------
    # Arranque / ajustes
    # ------------------------------------------------------------------
    def bootstrap(self):
        return {
            "ok": bool(self.ffmpeg and self.ffprobe),
            "ffmpeg": {"path": self.ffmpeg, "version": self.version, "found": bool(self.ffmpeg)},
            "ffprobe": {"path": self.ffprobe},
            "hardware": self.hardware_state(),
            "presets": self.presets,
            "settings": {
                "outputDir": self.settings.get("outputDir"),
                "openOutputWhenDone": bool(self.settings.get("openOutputWhenDone")),
            },
            "containers": CONTAINERS,
            "videoEncoders": VIDEO_ENCODERS,
            "audioEncoders": AUDIO_ENCODERS,
            "concatModes": CONCAT_MODES,
            "captureSources": CAPTURE_SOURCES,
            "subtitleModes": SUBTITLE_MODES,
            "subtitleFormats": SUBTITLE_FORMATS,
            "subtitleLanguages": SUBTITLE_LANGUAGES,
            "burnFonts": BURN_FONTS,
            "burnColors": list(BURN_COLORS.keys()),
            "burnPositions": list(BURN_ALIGNMENTS.keys()),
            "defaults": default_options(),
            "restored": self.restored_pending,
            "platform": "win32" if os.name == "nt" else sys.platform,
        }

    def initial_files(self):
        return self.initial

    def save_settings(self, patch):
        self.settings.update(patch or {})
        save_settings(self.settings, self.settings_file)
        return {
            "ok": True,
            "outputDir": self.settings.get("outputDir"),
            "openOutputWhenDone": bool(self.settings.get("openOutputWhenDone")),
        }

    # ------------------------------------------------------------------
    # Diálogos
    # ------------------------------------------------------------------
    def pick_files(self):
        result = _window().create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=True, file_types=MEDIA_TYPES,
        )
        return list(result) if result else []

    def pick_output_dir(self):
        result = _window().create_file_dialog(webview.FOLDER_DIALOG)
        if not result:
            return None
        return result[0] if isinstance(result, (list, tuple)) else result

    def pick_subtitle_file(self):
        result = _window().create_file_dialog(
            webview.OPEN_DIALOG,
            file_types=("Subtítulos (*.srt;*.ass;*.ssa;*.vtt;*.sup)", "Todos los archivos (*.*)"),
        )
        if not result:
            return None
        return result[0] if isinstance(result, (list, tuple)) else result

    # ------------------------------------------------------------------
    # Editor de subtítulos
    # ------------------------------------------------------------------
    def subtitle_load(self, path):
        if not path or not os.path.isfile(path):
            return {"ok": False, "error": "El archivo de subtítulos no existe."}
        try:
            return load_subtitles(path)
        except Exception as error:  # noqa: BLE001
            return {"ok": False, "error": str(error)}

    def subtitle_save(self, path, cues):
        if not path:
            return {"ok": False, "error": "Falta la ruta de destino."}
        try:
            return save_subtitles(path, cues)
        except ValueError as error:
            return {"ok": False, "error": str(error)}
        except OSError as error:
            return {"ok": False, "error": f"No se pudo guardar: {error.strerror or error}"}

    def pick_save_path(self, suggested=None):
        window = _window()
        if not window:
            return None
        result = window.create_file_dialog(
            webview.SAVE_DIALOG,
            save_filename=suggested or "subtitulos.srt",
            file_types=("Subtítulos (*.srt;*.vtt)", "Todos los archivos (*.*)"),
        )
        if isinstance(result, (list, tuple)):
            result = result[0] if result else None
        return result

    def pick_ffmpeg(self):
        result = _window().create_file_dialog(
            webview.OPEN_DIALOG, file_types=("Ejecutable (*.exe)", "Todos los archivos (*.*)"),
        )
        if not result:
            return {"ok": False}
        chosen = result[0] if isinstance(result, (list, tuple)) else result
        probe = ffprobe_beside(chosen)
        if not probe:
            return {"ok": False, "message": "Junto a ese ffmpeg.exe debe existir ffprobe.exe."}

        self.ffmpeg = os.path.normpath(chosen)
        self.ffprobe = probe
        self.version = ffmpeg_version(self.ffmpeg)
        self.settings["ffmpegPath"] = self.ffmpeg
        self.settings["ffprobePath"] = probe
        self.settings.pop("hardwareCache", None)
        save_settings(self.settings, self.settings_file)
        self.runner.ffmpeg_path = self.ffmpeg
        self._start_hardware_detection(force=True)
        payload = self.bootstrap()
        payload.update({"ok": True})
        return payload

    # ------------------------------------------------------------------
    # Medios
    # ------------------------------------------------------------------
    def probe(self, paths):
        results = []
        for path in paths or []:
            try:
                results.append({"ok": True, "media": probe_file(self.ffprobe, path)})
            except Exception as error:  # noqa: BLE001
                results.append({"ok": False, "path": path, "error": str(error)})
        return results

    def preview(self, inputs, options):
        if options.get("task") == "capture":
            try:
                built = self._build_capture_job(options, self.settings.get("outputDir"), prepare=False)
            except Exception as error:  # noqa: BLE001
                return {"ok": False, "preview": "", "issues": [{"level": "error", "message": str(error)}]}
            if not built["ok"]:
                return {"ok": False, "preview": "", "issues": built["issues"], "output": None}
            job = built["job"]
            return {
                "ok": True,
                "preview": job["preview"],
                "issues": built["issues"],
                "output": job["output"],
                "duration": job["duration"],
                "estimatedBytes": job.get("estimatedBytes"),
            }

        if isinstance(inputs, str):
            paths = [inputs] if inputs else []
        else:
            paths = list(inputs or [])
        if not paths:
            return {"ok": False, "preview": "", "issues": [], "output": None}
        try:
            built = self._build_job(paths, options, self.settings.get("outputDir"), prepare=False)
        except Exception as error:  # noqa: BLE001
            return {"ok": False, "preview": "", "issues": [{"level": "error", "message": str(error)}]}
        if not built["ok"]:
            return {"ok": False, "preview": "", "issues": built["issues"], "output": None}
        return {
            "ok": True,
            "preview": built["job"]["preview"],
            "issues": built["issues"],
            "output": built["job"]["output"],
            "duration": built["job"]["duration"],
            "estimatedBytes": built["job"].get("estimatedBytes"),
        }

    # ------------------------------------------------------------------
    # Cola
    # ------------------------------------------------------------------
    def add_to_queue(self, files, options, output_dir=None):
        files = list(files or [])
        if not files:
            return {"added": 0, "rejected": [], "snapshot": self.queue.snapshot()}

        # Unir clips es un único trabajo con varias entradas; el resto, uno por archivo.
        groups = [files] if options.get("task") == "concat" else [[path] for path in files]

        added = 0
        rejected = []
        jobs = []
        for group in groups:
            try:
                built = self._build_job(group, options, output_dir or self.settings.get("outputDir"))
            except Exception as error:  # noqa: BLE001
                rejected.append({"file": group[0], "messages": [str(error)]})
                continue
            if not built["ok"]:
                rejected.append({
                    "file": group[0],
                    "messages": [i["message"] for i in built["issues"] if i["level"] == "error"],
                })
                continue
            try:
                os.makedirs(os.path.dirname(built["job"]["output"]), exist_ok=True)
            except OSError as error:
                rejected.append({"file": group[0], "messages": [f"No se pudo crear la carpeta: {error}"]})
                continue
            jobs.append(built["job"])
            added += 1

        if jobs:
            self.queue.add(jobs)
        return {"added": added, "rejected": rejected, "snapshot": self.queue.snapshot()}

    def add_capture(self, options, output_dir=None):
        """Encola una grabación (no necesita archivo de entrada)."""
        try:
            built = self._build_capture_job(
                options, output_dir or self.settings.get("outputDir"), prepare=True,
            )
        except Exception as error:  # noqa: BLE001
            return {"added": 0, "rejected": [{"file": "captura", "messages": [str(error)]}],
                    "snapshot": self.queue.snapshot()}
        if not built["ok"]:
            return {
                "added": 0,
                "rejected": [{"file": "captura",
                              "messages": [i["message"] for i in built["issues"] if i["level"] == "error"]}],
                "snapshot": self.queue.snapshot(),
            }
        self.queue.add([built["job"]])
        return {"added": 1, "rejected": [], "snapshot": self.queue.snapshot()}

    def start_queue(self):
        self.queue.start()
        return self.queue.snapshot()

    def pause_queue(self):
        self.queue.pause()
        return self.queue.snapshot()

    def clear_queue(self):
        self.queue.clear_finished()
        return self.queue.snapshot()

    def cancel_job(self, job_id):
        self.queue.cancel(job_id)
        return self.queue.snapshot()

    def remove_job(self, job_id):
        self.queue.remove(job_id)
        return self.queue.snapshot()

    def queue_state(self):
        return self.queue.snapshot()

    # ------------------------------------------------------------------
    # Shell
    # ------------------------------------------------------------------
    def reveal(self, target):
        if target and os.path.exists(target):
            if os.name == "nt":
                subprocess.Popen(["explorer", "/select,", os.path.normpath(target)])
            else:
                subprocess.Popen(["xdg-open", os.path.dirname(os.path.normpath(target))])
        return True

    def open_path(self, target):
        if target and os.path.exists(target):
            try:
                os.startfile(target)  # type: ignore[attr-defined]
            except OSError:
                return False
            return True
        return False

    # ------------------------------------------------------------------
    # Construcción de trabajos
    # ------------------------------------------------------------------
    def _build_job(self, paths, options, output_dir, prepare=True, output_override=None):
        if isinstance(paths, str):
            paths = [paths]
        if options.get("task") == "concat":
            return self._build_concat_job(paths, options, output_dir, prepare)
        if options.get("task") == "subs":
            return self._build_subtitle_job(paths[0], options, output_dir, prepare)
        if options.get("task") == "sheet":
            return self._build_sheet_job(paths[0], options, output_dir, prepare)
        return self._build_single_job(paths[0], options, output_dir, prepare, output_override)

    @staticmethod
    def _temp_output_path(output_path, job_id):
        """Archivo temporal en la misma carpeta (y volumen) que la salida final."""
        directory, filename = os.path.split(output_path)
        _, extension = os.path.splitext(filename)
        return os.path.join(directory, f".ffgui-{job_id}{extension}")

    @staticmethod
    def _space_issues(output_path, needed_bytes):
        if needed_bytes and not has_space(output_path, needed_bytes):
            return [{"level": "error", "message": space_error_message(output_path, needed_bytes)}]
        return []

    @staticmethod
    def _video_fallback(options, build_commands):
        """Variante en CPU del mismo trabajo, para reintentar si la GPU falla."""
        soft = software_fallback_codec(options.get("videoCodec") or "")
        if not soft:
            return None
        fallback_options = dict(options)
        fallback_options["videoCodec"] = soft
        built = build_commands(fallback_options)
        if not built:
            return None
        return {"commands": built["commands"], "codec": soft}

    def _build_single_job(self, input_path, options, output_dir, prepare=True, output_override=None):
        media = probe_file(self.ffprobe, input_path)
        output = output_override or self._build_output_path(input_path, options, output_dir)
        estimate = estimate_output_bytes(options, [media])

        issues = validate_job(options=options, media=media, output_path=output, input_path=input_path)
        issues += self._space_issues(output, estimate)
        if any(issue["level"] == "error" for issue in issues):
            return {"ok": False, "issues": issues, "media": media}

        job_id = str(uuid.uuid4())
        temp_output = self._temp_output_path(output, job_id) if prepare else None
        command_output = temp_output or output
        passlog = os.path.join(os.path.dirname(output), f".ffgui-pass-{job_id}")

        built = build_job_commands(
            input_path=input_path,
            output_path=command_output,
            options=options,
            media=media,
            passlog_base=passlog,
        )

        fallback = None
        if prepare and options.get("task", "video") == "video":
            fallback = self._video_fallback(
                options,
                lambda fallback_options: build_job_commands(
                    input_path=input_path,
                    output_path=command_output,
                    options=fallback_options,
                    media=media,
                    passlog_base=passlog,
                ),
            )

        return {
            "ok": True,
            "issues": issues,
            "media": media,
            "job": {
                "id": job_id,
                "input": input_path,
                "inputs": [input_path],
                "inputName": os.path.basename(input_path),
                "clipCount": 1,
                "output": output,
                "tempOutput": temp_output,
                "options": options,
                "estimatedBytes": estimate,
                "fallback": fallback,
                "task": options.get("task", "video"),
                "container": options.get("container", "mp4"),
                "label": self._task_label(options),
                "commands": built["commands"],
                "preview": built["preview"],
                "duration": self._effective_duration(media, options),
                "passlogBase": passlog,
                "status": "pending",
                "percent": 0,
                "logTail": [],
                "pass": 1,
                "passCount": len(built["commands"]),
            },
        }

    def _build_concat_job(self, paths, options, output_dir, prepare):
        medias = [probe_file(self.ffprobe, path) for path in paths]
        output = self._build_output_path(paths[0], options, output_dir)
        estimate = estimate_output_bytes(options, medias)

        issues = validate_concat(inputs=paths, options=options, medias=medias, output_path=output)
        issues += self._space_issues(output, estimate)
        if any(issue["level"] == "error" for issue in issues):
            return {"ok": False, "issues": issues, "media": medias[0] if medias else None}

        job_id = str(uuid.uuid4())
        temp_output = self._temp_output_path(output, job_id) if prepare else None
        command_output = temp_output or output
        passlog = os.path.join(os.path.dirname(output), f".ffgui-pass-{job_id}")
        list_path = os.path.join(os.path.dirname(output), f".ffgui-concat-{job_id}.txt")
        mode = options.get("concatMode", "copy")
        if mode == "copy" and prepare:
            write_concat_list(paths, list_path)

        built = build_concat_commands(
            inputs=paths,
            output_path=command_output,
            options=options,
            medias=medias,
            list_path=list_path,
            passlog_base=passlog,
        )

        fallback = None
        if prepare and mode == "reencode":
            fallback = self._video_fallback(
                options,
                lambda fallback_options: build_concat_commands(
                    inputs=paths,
                    output_path=command_output,
                    options=fallback_options,
                    medias=medias,
                    list_path=list_path,
                    passlog_base=passlog,
                ),
            )

        duration = sum((media.get("duration") or 0) for media in medias) or None

        return {
            "ok": True,
            "issues": issues,
            "media": medias[0],
            "job": {
                "id": job_id,
                "input": paths[0],
                "inputs": paths,
                "inputName": f"{os.path.basename(paths[0])} +{len(paths) - 1}",
                "clipCount": len(paths),
                "output": output,
                "tempOutput": temp_output,
                "options": options,
                "estimatedBytes": estimate,
                "fallback": fallback,
                "task": "concat",
                "container": options.get("container", "mp4"),
                "label": f"Unión · {len(paths)} clips",
                "commands": built["commands"],
                "preview": built["preview"],
                "duration": duration,
                "passlogBase": passlog,
                "listPath": list_path if mode == "copy" else None,
                "status": "pending",
                "percent": 0,
                "logTail": [],
                "pass": 1,
                "passCount": len(built["commands"]),
            },
        }

    def _build_capture_job(self, options, output_dir, prepare=True, output_override=None):
        output = output_override or self._capture_output_path(output_dir, options)
        estimate = estimate_output_bytes(options, [])
        issues = validate_capture(options=options)
        issues += self._space_issues(output, estimate)
        if any(issue["level"] == "error" for issue in issues):
            return {"ok": False, "issues": issues, "media": None}

        job_id = str(uuid.uuid4())
        temp_output = self._temp_output_path(output, job_id) if prepare else None
        built = build_capture_commands(options=options, output_path=temp_output or output)

        try:
            duration = float(options.get("captureDuration") or 0)
        except (TypeError, ValueError):
            duration = 0
        source = options.get("captureSource") or "screen"
        source_label = CAPTURE_SOURCES.get(source, source)

        return {
            "ok": True,
            "issues": issues,
            "media": None,
            "job": {
                "id": job_id,
                "input": "",
                "inputs": [],
                "inputName": f"Grabación · {source_label}",
                "clipCount": 1,
                "output": output,
                "tempOutput": temp_output,
                "options": options,
                "estimatedBytes": estimate,
                "fallback": None,
                "task": "capture",
                "container": options.get("container", "mp4"),
                "label": f"Grabación · {source_label}",
                "commands": built["commands"],
                "preview": built["preview"],
                "duration": duration or None,
                "status": "pending",
                "percent": 0,
                "logTail": [],
                "pass": 1,
                "passCount": 1,
            },
        }

    @staticmethod
    def _is_writable(directory):
        try:
            os.makedirs(directory, exist_ok=True)
            probe = os.path.join(directory, f".ffgui-write-{uuid.uuid4().hex[:8]}")
            with open(probe, "w", encoding="utf-8") as handle:
                handle.write("x")
            os.unlink(probe)
            return True
        except OSError:
            return False

    @classmethod
    def _capture_output_path(cls, output_dir, options):
        videos = os.path.join(os.path.expanduser("~"), "Videos")
        candidates = [output_dir, videos, os.path.expanduser("~"), tempfile.gettempdir()]
        target_dir = tempfile.gettempdir()
        for directory in candidates:
            if directory and cls._is_writable(directory):
                target_dir = directory
                break

        extension = container_info(options.get("container", "mp4"))["ext"]
        base = f"Grabacion_{time.strftime('%Y%m%d_%H%M%S')}"
        candidate = os.path.join(target_dir, f"{base}.{extension}")
        counter = 2
        while os.path.exists(candidate):
            candidate = os.path.join(target_dir, f"{base} ({counter}).{extension}")
            counter += 1
        return candidate

    def _build_subtitle_job(self, input_path, options, output_dir, prepare=True):
        media = probe_file(self.ffprobe, input_path)
        output = self._build_subtitle_output_path(input_path, options, output_dir)
        estimate = estimate_output_bytes(options, [media])

        issues = validate_subtitles(media=media, options=options, output_path=output, input_path=input_path)
        issues += self._space_issues(output, estimate)
        if any(issue["level"] == "error" for issue in issues):
            return {"ok": False, "issues": issues, "media": media}

        job_id = str(uuid.uuid4())
        temp_output = self._temp_output_path(output, job_id) if prepare else None
        command_output = temp_output or output
        temp_files = []
        extraction_path = None
        if options.get("subsMode") == "burn" and not options.get("subtitleFile"):
            subs = media.get("subtitles") or []
            stream_index = int(options.get("subtitleStream") or 0)
            codec = subs[stream_index].get("codec") if stream_index < len(subs) else "subrip"
            extension = "ass" if codec == "ass" else "srt"
            extraction_path = os.path.join(os.path.dirname(output), f".ffgui-sub-{job_id}.{extension}")
            temp_files.append(extraction_path)

        built = build_subtitle_commands(
            media=media, options=options, output_path=command_output, extraction_path=extraction_path,
        )
        mode = options.get("subsMode", "extract")

        fallback = None
        if prepare and mode == "burn":
            fallback = self._video_fallback(
                options,
                lambda fallback_options: build_subtitle_commands(
                    media=media, options=fallback_options,
                    output_path=command_output, extraction_path=extraction_path,
                ),
            )

        return {
            "ok": True,
            "issues": issues,
            "media": media,
            "job": {
                "id": job_id,
                "input": input_path,
                "inputs": [input_path],
                "inputName": os.path.basename(input_path),
                "clipCount": 1,
                "output": output,
                "tempOutput": temp_output,
                "options": options,
                "estimatedBytes": estimate,
                "fallback": fallback,
                "task": "subs",
                "container": options.get("container", "mp4"),
                "label": self._task_label(options),
                "commands": built["commands"],
                "preview": built["preview"],
                "duration": media.get("duration") if mode == "burn" else None,
                "durations": built.get("durations"),
                "tempFiles": temp_files,
                "status": "pending",
                "percent": 0,
                "logTail": [],
                "pass": 1,
                "passCount": len(built["commands"]),
            },
        }

    def _build_sheet_job(self, input_path, options, output_dir, prepare=True):
        media = probe_file(self.ffprobe, input_path)
        output = self._build_output_path(input_path, options, output_dir)
        estimate = estimate_output_bytes(options, [media])

        issues = validate_sheet(media=media, options=options, output_path=output, input_path=input_path)
        issues += self._space_issues(output, estimate)
        if any(issue["level"] == "error" for issue in issues):
            return {"ok": False, "issues": issues, "media": media}

        job_id = str(uuid.uuid4())
        temp_output = self._temp_output_path(output, job_id) if prepare else None
        built = build_sheet_commands(media=media, options=options, output_path=temp_output or output)

        return {
            "ok": True,
            "issues": issues,
            "media": media,
            "job": {
                "id": job_id,
                "input": input_path,
                "inputs": [input_path],
                "inputName": os.path.basename(input_path),
                "clipCount": 1,
                "output": output,
                "tempOutput": temp_output,
                "options": options,
                "estimatedBytes": estimate,
                "fallback": None,
                "task": "sheet",
                "container": options.get("container", "jpg"),
                "label": "Hoja de contactos",
                "commands": built["commands"],
                "preview": built["preview"],
                "duration": None,
                "durations": built.get("durations"),
                "status": "pending",
                "percent": 0,
                "logTail": [],
                "pass": 1,
                "passCount": len(built["commands"]),
            },
        }

    @staticmethod
    def _build_subtitle_output_path(input_path, options, output_dir):
        directory, filename = os.path.split(input_path)
        stem, _ = os.path.splitext(filename)
        target_dir = output_dir or directory
        mode = options.get("subsMode", "extract")

        if mode == "extract":
            extension = (options.get("subtitleFormat") or "srt").lower()
            suffix = "_subs"
        else:
            container = container_info(options.get("container", "mp4"))
            extension = container["ext"]
            suffix = "_con_subs" if mode == "mux" else "_subtitulado"

        name = f"{stem}{suffix}"
        candidate = os.path.join(target_dir, f"{name}.{extension}")
        counter = 2
        while os.path.exists(candidate):
            candidate = os.path.join(target_dir, f"{name} ({counter}).{extension}")
            counter += 1
        return candidate

    @staticmethod
    def _task_label(options, clip_count=1):
        container = container_info(options.get("container", "mp4"))["label"]
        task = options.get("task", "video")
        if task == "audio":
            return f"Audio · {container}"
        if task == "gif":
            return "GIF animado"
        if task == "image":
            return f"Miniatura · {container}"
        if task == "concat":
            return f"Unión · {clip_count} clips"
        if task == "subs":
            return f"Subtítulos · {SUBTITLE_MODES.get(options.get('subsMode'), '')}"
        if task == "sheet":
            return "Hoja de contactos"
        return f"Vídeo · {container}"

    @staticmethod
    def _effective_duration(media, options):
        trim = options.get("trim") or {}
        duration = None
        if trim.get("enabled"):
            start = trim.get("start")
            end = trim.get("end")
            if start is not None and end is not None and float(end) > float(start):
                duration = float(end) - float(start)
        if duration is None:
            duration = media.get("duration")
        try:
            speed = float(options.get("speed") or 1.0)
        except (TypeError, ValueError):
            speed = 1.0
        if duration and speed > 0 and abs(speed - 1.0) > 1e-9:
            duration = duration / speed
        return duration

    @staticmethod
    def _build_output_path(input_path, options, output_dir):
        directory, filename = os.path.split(input_path)
        stem, current_ext = os.path.splitext(filename)
        current_ext = current_ext.lstrip(".").lower()
        container = container_info(options.get("container", "mp4"))
        target_dir = output_dir or directory

        task = options.get("task", "video")
        suffix = "_convertido"
        if task == "audio":
            suffix = "_audio" if current_ext == container["ext"] else ""
        elif task == "gif":
            suffix = ""
        elif task == "image":
            suffix = "_miniatura"
        elif task == "concat":
            suffix = "_unido"
        elif task == "sheet":
            suffix = "_hoja"

        name = f"{stem}{suffix}"
        candidate = os.path.join(target_dir, f"{name}.{container['ext']}")
        counter = 2
        while os.path.exists(candidate):
            candidate = os.path.join(target_dir, f"{name} ({counter}).{container['ext']}")
            counter += 1
        return candidate


def window_geometry(design_width=1400, design_height=900):
    """Ajusta la ventana al área de trabajo real (teniendo en cuenta el escalado DPI)."""
    if os.name != "nt":
        return {"width": design_width, "height": design_height}
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        user32.SetProcessDPIAware()
        rect = wintypes.RECT()
        user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)  # SPI_GETWORKAREA
        dpi = user32.GetDpiForSystem() if hasattr(user32, "GetDpiForSystem") else 96
        scale = (dpi or 96) / 96.0
        available_w = (rect.right - rect.left) / scale
        available_h = (rect.bottom - rect.top) / scale

        width = int(min(design_width, max(1100, available_w * 0.94)))
        height = int(min(design_height, max(700, available_h * 0.94)))
        return {
            "width": width,
            "height": height,
            "x": int(max(0, (available_w - width) / 2)),
            "y": int(max(0, (available_h - height) / 2)),
        }
    except Exception:  # noqa: BLE001
        return {"width": design_width, "height": design_height}


_MUTEX = None


def _single_instance_ok():
    """Evita dos ventanas y dos colas: si ya hay una instancia, la trae al frente."""
    global _MUTEX
    if os.name != "nt":
        return True

    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32 = ctypes.WinDLL("user32", use_last_error=True)

    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]

    _MUTEX = kernel32.CreateMutexW(None, False, "Local\\FFmpegStudio_SingleInstance")
    if ctypes.get_last_error() != 183:  # ERROR_ALREADY_EXISTS
        return True

    user32.FindWindowW.restype = wintypes.HWND
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    hwnd = user32.FindWindowW(None, "FFmpeg Studio")
    if hwnd:
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
    elif len(sys.argv) > 1:
        user32.MessageBoxW(None, "FFmpeg Studio ya está abierto.", "FFmpeg Studio", 0x40)
    return False


def _cli_streams(log_path=None):
    """En la versión sin consola, la salida va a --log (o se descarta)."""
    if sys.stdout is not None and sys.stderr is not None:
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(errors="replace")
            except Exception:  # noqa: BLE001
                pass
        return None

    try:
        handle = open(log_path, "w", encoding="utf-8") if log_path else open(os.devnull, "w", encoding="utf-8")
    except OSError:
        handle = open(os.devnull, "w", encoding="utf-8")
    sys.stdout = handle
    sys.stderr = handle
    return handle


def run_cli(argv) -> int:
    """Conversión sin interfaz: útil para automatizar y para probar el paquete."""
    import argparse

    from core.errors import looks_like_hardware_failure

    parser = argparse.ArgumentParser(prog="FFmpegStudio.exe", description="Conversión sin interfaz gráfica")
    parser.add_argument("--cli", nargs=2, metavar=("ENTRADA", "SALIDA"), required=True,
                        help="archivo de entrada y archivo de salida")
    parser.add_argument("--preset", help="id de un perfil de presets.json")
    parser.add_argument("--crf", type=int, help="calidad: menor = mejor (por defecto 21)")
    parser.add_argument("--width", type=int, help="ancho máximo en píxeles")
    parser.add_argument("--container", help="contenedor de salida (mp4, mkv, webm…)")
    parser.add_argument("--log", help="archivo donde escribir el progreso y los errores")
    args = parser.parse_args(argv)

    log_handle = _cli_streams(args.log)
    try:
        return _run_cli_job(args, looks_like_hardware_failure)
    finally:
        if log_handle:
            log_handle.flush()
            log_handle.close()


def _run_cli_job(args, looks_like_hardware_failure) -> int:

    source, target = args.cli
    if not os.path.isfile(source):
        print(f"ERROR: no existe {source}", file=sys.stderr)
        return 2

    api = Api(enable_hardware_detection=False)
    if not api.ffmpeg or not api.ffprobe:
        print("ERROR: no se encontró FFmpeg (colócalo junto al ejecutable o en el PATH).", file=sys.stderr)
        return 2

    options = default_options()
    if args.preset:
        preset = next((item for item in api.presets if item["id"] == args.preset), None)
        if not preset:
            print(f"ERROR: preset desconocido {args.preset}", file=sys.stderr)
            return 2
        if preset["task"] in ("concat", "subs"):
            print("ERROR: ese preset necesita la interfaz gráfica.", file=sys.stderr)
            return 2
        for key, value in preset["options"].items():
            if value is not None:
                options[key] = value
    if args.crf is not None:
        options["quality"] = args.crf
        options["qualityMode"] = "crf"
    if args.width:
        options["maxWidth"] = args.width
        options["maxHeight"] = None
    if args.container:
        options["container"] = args.container

    try:
        built = api._build_job(
            [source], options, os.path.dirname(target) or ".",
            prepare=True, output_override=target,
        )
    except Exception as error:  # noqa: BLE001
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    if not built["ok"]:
        for issue in built["issues"]:
            if issue["level"] == "error":
                print(f"ERROR: {issue['message']}", file=sys.stderr)
        return 2

    job = built["job"]
    runner = JobRunner(api.ffmpeg)
    state = {"last": -10}

    def on_progress(payload):
        percent = payload.get("percent")
        if percent is None:
            return
        step = int(percent // 10) * 10
        if step > state["last"]:
            state["last"] = step
            print(f"progreso: {step}%", flush=True)

    result = runner.run_job(
        job_id=job["id"], commands=job["commands"], duration=job.get("duration"),
        durations=job.get("durations"), on_progress=on_progress,
    )

    if (not result["ok"] and not result.get("cancelled")
            and job.get("fallback") and looks_like_hardware_failure(result.get("logLines"), result.get("error"))):
        print("aviso: fallo de GPU, reintentando en CPU…", file=sys.stderr)
        result = runner.run_job(
            job_id=job["id"], commands=job["fallback"]["commands"],
            duration=job.get("duration"), durations=job.get("durations"), on_progress=on_progress,
        )

    temp = job.get("tempOutput")
    if result["ok"]:
        try:
            os.replace(temp, job["output"])
        except OSError as error:
            print(f"ERROR: no se pudo finalizar la salida: {error}", file=sys.stderr)
            return 1
        print(f"OK: {job['output']}")
        return 0

    if temp:
        try:
            os.unlink(temp)
        except OSError:
            pass
    error = result.get("error") or {}
    print(f"ERROR: {error.get('title', 'FFmpeg falló')}", file=sys.stderr)
    if error.get("detail"):
        print(f"  {error['detail']}", file=sys.stderr)
    return 1


def main():
    global _WINDOW
    if "--cli" in sys.argv:
        sys.exit(run_cli(sys.argv[1:]))
    if not _single_instance_ok():
        return
    api = Api(restore_queue=True)
    geometry = window_geometry()
    window = webview.create_window(
        "FFmpeg Studio",
        url=os.path.join(WEB_DIR, "index.html"),
        js_api=api,
        width=geometry["width"],
        height=geometry["height"],
        x=geometry.get("x"),
        y=geometry.get("y"),
        min_size=(1180, 720),
        background_color="#0d1016",
        text_select=True,
    )
    _WINDOW = window
    debug = os.environ.get("FFGUI_DEBUG") == "1"
    webview.start(debug=debug)


if __name__ == "__main__":
    main()
