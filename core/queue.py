"""Cola secuencial de trabajos con estado compartido entre hilos."""

from __future__ import annotations

import os
import threading
import time

from .errors import looks_like_hardware_failure
from .storage import has_space, space_error_message


class JobQueue:
    def __init__(self, runner, on_change=None):
        self.runner = runner
        self.jobs = []
        self.lock = threading.RLock()
        self.running = False
        self.paused = False
        self.current_id = None
        self.thread = None
        self.on_change = on_change

    # ------------------------------------------------------------------
    def persisted_state(self):
        """Estado apto para guardar: pendientes re-ejecutables e historial reciente."""
        with self.lock:
            pending = []
            history = []
            for job in self.jobs:
                status = job["status"]
                if status in ("pending", "running"):
                    pending.append({
                        "inputs": job.get("inputs") or [],
                        "options": job.get("options") or {},
                        "output": job["output"],
                    })
                elif status in ("done", "error", "cancelled"):
                    history.append({
                        "id": job["id"],
                        "inputName": job["inputName"],
                        "output": job["output"],
                        "status": status,
                        "label": job.get("label"),
                        "finishedAt": job.get("finishedAt"),
                        "error": job.get("error"),
                    })
            return {"pending": pending, "history": history[-20:]}

    def _notify_change(self):
        if not self.on_change:
            return
        try:
            self.on_change(self.persisted_state())
        except Exception:  # noqa: BLE001
            pass

    def add(self, jobs):
        with self.lock:
            self.jobs.extend(jobs)
        self._notify_change()
        self.start()

    def start(self):
        with self.lock:
            if self.thread and self.thread.is_alive():
                self.paused = False
                return
            self.paused = False
            self.running = True
            self.thread = threading.Thread(target=self._pump, daemon=True)
            self.thread.start()

    def pause(self):
        with self.lock:
            self.paused = True

    def cancel(self, job_id):
        with self.lock:
            job = next((j for j in self.jobs if j["id"] == job_id), None)
        if not job:
            return False
        if job["status"] == "pending":
            with self.lock:
                job["status"] = "cancelled"
                job["finishedAt"] = time.time() * 1000
            self._notify_change()
            return True
        if job["status"] == "running":
            return self.runner.cancel(job_id)
        return False

    def remove(self, job_id):
        with self.lock:
            job = next((j for j in self.jobs if j["id"] == job_id), None)
            if not job or job["status"] == "running":
                return False
            self.jobs.remove(job)
        self._notify_change()
        return True

    def clear_finished(self):
        with self.lock:
            self.jobs = [j for j in self.jobs if j["status"] in ("running", "pending")]
        self._notify_change()

    # ------------------------------------------------------------------
    def _pump(self):
        while True:
            with self.lock:
                if self.paused:
                    self.running = False
                    return
                job = next((j for j in self.jobs if j["status"] == "pending"), None)
                if not job:
                    self.running = False
                    self.current_id = None
                    return
                job["status"] = "running"
                job["startedAt"] = time.time() * 1000
                job["percent"] = 0
                self.current_id = job["id"]
            self._run(job)

    def _run(self, job):
        self._notify_change()
        if not self._ensure_space(job):
            self._notify_change()
            return

        result = self._execute(job, job["commands"], job.get("durations"))

        if self._should_retry_on_cpu(job, result):
            with self.lock:
                job["retryNote"] = "La codificación por GPU falló; reintentando con la CPU…"
                job["retrying"] = True
            self._remove_output_temp(job)
            self._cleanup_passlog(job)
            self._on_progress(job["id"], {
                "percent": 0, "speed": None, "etaSeconds": None,
                "sizeBytes": None, "pass": 1, "passCount": job.get("passCount") or 1,
            })
            result = self._execute(job, job["fallback"]["commands"], job.get("durations"))

        with self.lock:
            job["finishedAt"] = time.time() * 1000
            job["logTail"] = self._compose_log(job, result.get("logLines", [])[-40:])
            if result["ok"]:
                if self._finalize_output(job):
                    job["status"] = "done"
                    job["percent"] = 100
                    job["speed"] = None
                    job["etaSeconds"] = None
                else:
                    job["status"] = "error"
                    job["error"] = {
                        "title": "No se pudo finalizar el archivo de salida.",
                        "detail": "El archivo temporal no se pudo renombrar; ¿está bloqueado por otro programa?",
                    }
            elif result.get("cancelled"):
                job["status"] = "cancelled"
            else:
                job["status"] = "error"
                job["error"] = result.get("error") or {
                    "title": "Error desconocido de FFmpeg.", "detail": "",
                }

        if job["status"] != "done":
            self._remove_output_temp(job)
        self._cleanup_passlog(job)
        self._notify_change()

    def _execute(self, job, commands, durations):
        return self.runner.run_job(
            job_id=job["id"],
            commands=commands,
            duration=job.get("duration"),
            durations=durations,
            on_progress=lambda payload: self._on_progress(job["id"], payload),
            on_log=lambda lines: self._on_log(job["id"], lines),
        )

    @staticmethod
    def _compose_log(job, lines):
        note = job.get("retryNote")
        return ([note] + list(lines)) if note else list(lines)

    def _ensure_space(self, job):
        needed = job.get("estimatedBytes") or 0
        if not needed or has_space(job["output"], needed):
            return True
        with self.lock:
            job["status"] = "error"
            job["finishedAt"] = time.time() * 1000
            job["error"] = {"title": space_error_message(job["output"], needed), "detail": ""}
        return False

    @staticmethod
    def _should_retry_on_cpu(job, result):
        if result.get("ok") or result.get("cancelled"):
            return False
        if not job.get("fallback"):
            return False
        return looks_like_hardware_failure(result.get("logLines"), result.get("error"))

    @staticmethod
    def _remove_output_temp(job):
        temp = job.get("tempOutput")
        if temp:
            try:
                os.unlink(temp)
            except OSError:
                pass

    @staticmethod
    def _unique_path(path):
        directory, filename = os.path.split(path)
        stem, extension = os.path.splitext(filename)
        counter = 2
        while True:
            candidate = os.path.join(directory, f"{stem} ({counter}){extension}")
            if not os.path.exists(candidate):
                return candidate
            counter += 1

    def _finalize_output(self, job):
        temp = job.get("tempOutput")
        if not temp:
            return True
        if not os.path.exists(temp):
            return False
        final = job["output"]
        try:
            if os.path.exists(final):
                final = self._unique_path(final)
                job["output"] = final
            os.replace(temp, final)
            return True
        except OSError:
            return False

    def _on_progress(self, job_id, payload):
        with self.lock:
            job = next((j for j in self.jobs if j["id"] == job_id), None)
            if not job:
                return
            if payload.get("percent") is not None:
                job["percent"] = payload["percent"]
            job["speed"] = payload.get("speed")
            job["etaSeconds"] = payload.get("etaSeconds")
            job["sizeBytes"] = payload.get("sizeBytes")
            job["pass"] = payload.get("pass")
            job["passCount"] = payload.get("passCount")

    def _on_log(self, job_id, lines):
        with self.lock:
            job = next((j for j in self.jobs if j["id"] == job_id), None)
            if job:
                job["logTail"] = self._compose_log(job, lines)

    @staticmethod
    def _cleanup_passlog(job):
        base = job.get("passlogBase")
        if base:
            directory = os.path.dirname(base) or "."
            prefix = os.path.basename(base)
            try:
                for name in os.listdir(directory):
                    if name.startswith(prefix):
                        os.unlink(os.path.join(directory, name))
            except OSError:
                pass

        list_path = job.get("listPath")
        if list_path:
            try:
                os.unlink(list_path)
            except OSError:
                pass

        for temp_path in job.get("tempFiles") or []:
            try:
                os.unlink(temp_path)
            except OSError:
                pass

    # ------------------------------------------------------------------
    def snapshot(self):
        with self.lock:
            return {
                "running": self.running,
                "paused": self.paused,
                "currentId": self.current_id,
                "jobs": [self._public(job) for job in self.jobs],
            }

    @staticmethod
    def _public(job):
        return {
            "id": job["id"],
            "input": job["input"],
            "inputs": job.get("inputs", [job["input"]]),
            "clipCount": job.get("clipCount", 1),
            "output": job["output"],
            "inputName": job["inputName"],
            "task": job["task"],
            "container": job["container"],
            "label": job["label"],
            "status": job["status"],
            "percent": round(float(job.get("percent") or 0), 1),
            "speed": job.get("speed"),
            "etaSeconds": job.get("etaSeconds"),
            "sizeBytes": job.get("sizeBytes"),
            "pass": job.get("pass"),
            "passCount": job.get("passCount"),
            "error": job.get("error"),
            "retrying": bool(job.get("retrying")),
            "logTail": job.get("logTail", []),
            "startedAt": job.get("startedAt"),
            "finishedAt": job.get("finishedAt"),
        }
