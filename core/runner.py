"""Ejecución de FFmpeg con progreso y cancelación limpia."""

from __future__ import annotations

import os
import subprocess
import threading
import time

from .errors import explain_failure

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


class JobRunner:
    def __init__(self, ffmpeg_path: str):
        self.ffmpeg_path = ffmpeg_path
        self._active = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    def cancel(self, job_id: str) -> bool:
        with self._lock:
            entry = self._active.get(job_id)
        if not entry:
            return False
        entry["cancelled"] = True
        try:
            entry["proc"].stdin.write("q")
            entry["proc"].stdin.flush()
        except Exception:
            pass

        def _kill_later():
            time.sleep(5)
            proc = entry["proc"]
            if proc.poll() is None:
                try:
                    proc.kill()
                except Exception:
                    pass

        threading.Thread(target=_kill_later, daemon=True).start()
        return True

    def is_running(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._active

    # ------------------------------------------------------------------
    def run_job(self, *, job_id, commands, duration, durations=None, on_progress=None, on_log=None) -> dict:
        pass_count = len(commands)
        weights = list(durations) if durations and len(durations) == pass_count else [duration] * pass_count
        total_weight = sum(float(w) for w in weights if w) or 0.0

        before = 0.0
        for index, command in enumerate(commands):
            weight = float(weights[index] or 0)
            if total_weight:
                progress_base = (before / total_weight) * 100
                progress_span = (weight / total_weight) * 100
            else:
                progress_base = (index / pass_count) * 100
                progress_span = 100 / pass_count
            result = self._run_one(
                job_id, command, weight, index, pass_count,
                on_progress, on_log, progress_base, progress_span,
            )
            if not result["ok"]:
                result["passIndex"] = index
                result["passCount"] = pass_count
                return result
            before += weight
        return {"ok": True, "cancelled": False, "code": 0, "logLines": [], "durationMs": 0}

    # ------------------------------------------------------------------
    def _run_one(self, job_id, args, duration, pass_index, pass_count,
                 on_progress, on_log, progress_base=0.0, progress_span=100.0) -> dict:
        started = time.time()
        proc = subprocess.Popen(
            [self.ffmpeg_path] + list(args),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=CREATE_NO_WINDOW,
        )
        entry = {"proc": proc, "cancelled": False}
        with self._lock:
            self._active[job_id] = entry

        log_lines = []
        last_log_at = 0.0

        def read_stderr():
            nonlocal last_log_at
            try:
                for raw in proc.stderr:
                    line = raw.rstrip("\r\n")
                    if not line:
                        continue
                    log_lines.append(line)
                    if len(log_lines) > 300:
                        del log_lines[:-300]
                    now = time.time()
                    if on_log and now - last_log_at > 0.25:
                        last_log_at = now
                        on_log(list(log_lines[-40:]))
            except Exception:
                pass

        stderr_thread = threading.Thread(target=read_stderr, daemon=True)
        stderr_thread.start()

        current = {}
        try:
            for raw in proc.stdout:
                line = raw.rstrip("\r\n")
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip()
                if key != "progress":
                    current[key] = self._parse_value(key, value)
                    continue
                self._emit_progress(current, duration, progress_base, progress_span,
                                    pass_index, pass_count, on_progress)
                current = {}
        except Exception:
            pass

        code = proc.wait()
        stderr_thread.join(timeout=3)

        for stream in (proc.stdout, proc.stderr, proc.stdin):
            try:
                if stream:
                    stream.close()
            except Exception:
                pass

        with self._lock:
            self._active.pop(job_id, None)

        cancelled = bool(entry.get("cancelled"))
        ok = (not cancelled) and code == 0
        if on_log:
            on_log(list(log_lines[-40:]))

        return {
            "ok": ok,
            "cancelled": cancelled,
            "code": code,
            "logLines": log_lines,
            "durationMs": int((time.time() - started) * 1000),
            "error": None if ok else (None if cancelled else explain_failure(code, log_lines)),
        }

    @staticmethod
    def _parse_value(key, value):
        try:
            if key in ("out_time_us", "out_time_ms"):
                return float(value) / 1_000_000
            if key == "speed":
                return float(str(value).replace("x", ""))
            if key in ("total_size", "frame", "fps"):
                return float(value)
        except ValueError:
            return None
        return None

    @staticmethod
    def _emit_progress(fields, duration, progress_base, progress_span, pass_index, pass_count, on_progress):
        if not on_progress:
            return
        out_time = fields.get("out_time_us")
        if out_time is None:
            out_time = fields.get("out_time_ms")
        speed = fields.get("speed")
        percent = None
        eta = None
        if duration and out_time is not None:
            ratio = max(0.0, min(1.0, out_time / duration))
            percent = progress_base + ratio * progress_span
            remaining = max(0.0, duration - out_time)
            if speed and speed > 0:
                eta = remaining / speed
        on_progress({
            "percent": percent,
            "outTime": out_time,
            "speed": speed,
            "fps": fields.get("fps"),
            "sizeBytes": fields.get("total_size"),
            "etaSeconds": eta,
            "pass": pass_index + 1,
            "passCount": pass_count,
        })
