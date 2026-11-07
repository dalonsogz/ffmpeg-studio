"""Pruebas del puente de la aplicación (sin abrir ventana)."""

import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import Api  # noqa: E402
from core.command import compute_scale  # noqa: E402
from core.options import default_options  # noqa: E402
from core.probe import probe_file  # noqa: E402

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(APP_ROOT, "..", ".probe", "media", "base.mp4")
SUBS = os.path.join(APP_ROOT, "..", ".probe", "media", "subs.srt")
READY = os.path.isfile(SAMPLE)
SKIP = "No hay vídeo de muestra disponible"


@unittest.skipUnless(READY, SKIP)
class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp_root = os.path.join(APP_ROOT, ".tmp")
        os.makedirs(tmp_root, exist_ok=True)
        cls.tmp = tempfile.mkdtemp(prefix="api-", dir=tmp_root)
        cls.api = Api(settings_file=os.path.join(cls.tmp, "settings.json"),
                      enable_hardware_detection=False)
        if not cls.api.ffmpeg:
            raise unittest.SkipTest("FFmpeg no encontrado")
        cls.media = probe_file(cls.api.ffprobe, SAMPLE)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_bootstrap_payload(self):
        payload = self.api.bootstrap()
        self.assertTrue(payload["ok"])
        self.assertIn("mp4", payload["containers"])
        self.assertIn("libx264", payload["videoEncoders"])
        self.assertTrue(payload["presets"])

    def test_preview_command(self):
        expected_scale = compute_scale(self.media, 320, 180)
        result = self.api.preview(SAMPLE, default_options(maxWidth=320, maxHeight=180))
        self.assertTrue(result["ok"], result.get("issues"))
        self.assertIn("-c:v libx264", result["preview"])
        self.assertIsNotNone(expected_scale)
        self.assertIn(expected_scale, result["preview"])
        self.assertFalse([i for i in result["issues"] if i["level"] == "error"])

    def test_preview_reports_blocking_error(self):
        result = self.api.preview(SAMPLE, default_options(container="webm", videoCodec="libx264"))
        self.assertFalse(result["ok"])
        self.assertTrue(any(i["level"] == "error" for i in result["issues"]))

    def test_queue_end_to_end(self):
        options = default_options(maxWidth=640, maxHeight=360, quality=26)
        result = self.api.add_to_queue([SAMPLE], options, self.tmp)
        self.assertEqual(result["added"], 1, result.get("rejected"))
        job = result["snapshot"]["jobs"][-1]
        job_id = job["id"]

        deadline = time.time() + 90
        status = job["status"]
        while time.time() < deadline:
            snapshot = self.api.queue_state()
            current = next((j for j in snapshot["jobs"] if j["id"] == job_id), None)
            if current is None:
                break
            status = current["status"]
            if status in ("done", "error", "cancelled"):
                break
            time.sleep(0.25)

        self.assertEqual(status, "done", (current or {}).get("error"))
        self.assertTrue(os.path.isfile(job["output"]))
        media = probe_file(self.api.ffprobe, job["output"])
        self.assertEqual(media["video"]["width"], 640)

    def test_incompatible_job_is_rejected(self):
        result = self.api.add_to_queue([SAMPLE], default_options(container="webm", videoCodec="libx264"), self.tmp)
        self.assertEqual(result["added"], 0)
        self.assertTrue(result["rejected"])

    def test_concat_end_to_end(self):
        options = default_options(task="concat", concatMode="copy")
        result = self.api.add_to_queue([SAMPLE, SAMPLE], options, self.tmp)
        self.assertEqual(result["added"], 1, result.get("rejected"))

        job = result["snapshot"]["jobs"][-1]
        self.assertEqual(job["clipCount"], 2)

        deadline = time.time() + 90
        status = job["status"]
        while time.time() < deadline:
            status = self.api.queue_state()["jobs"][-1]["status"]
            if status in ("done", "error", "cancelled"):
                break
            time.sleep(0.25)

        self.assertEqual(status, "done", self.api.queue_state()["jobs"][-1].get("error"))
        media = probe_file(self.api.ffprobe, job["output"])
        self.assertLess(abs(media["duration"] - 6.0), 0.8)

    def test_concat_preview_reports_single_clip(self):
        result = self.api.preview([SAMPLE], default_options(task="concat", concatMode="copy"))
        self.assertFalse(result["ok"])
        self.assertTrue(any("al menos dos" in i["message"] for i in result["issues"]))

    @unittest.skipUnless(os.path.isfile(SUBS), "Falta el archivo de subtítulos de muestra")
    def test_subtitles_mux_end_to_end(self):
        options = default_options(task="subs", subsMode="mux", container="mkv",
                                  subtitleFile=SUBS, subtitleLanguage="spa")
        preview = self.api.preview([SAMPLE], options)
        self.assertTrue(preview["ok"], preview.get("issues"))
        self.assertIn("-c:s", preview["preview"])

        result = self.api.add_to_queue([SAMPLE], options, self.tmp)
        self.assertEqual(result["added"], 1, result.get("rejected"))
        job = result["snapshot"]["jobs"][-1]

        deadline = time.time() + 60
        status = job["status"]
        while time.time() < deadline:
            current = next((j for j in self.api.queue_state()["jobs"] if j["id"] == job["id"]), None)
            status = current["status"] if current else status
            if status in ("done", "error", "cancelled"):
                break
            time.sleep(0.2)

        self.assertEqual(status, "done", (current or {}).get("error"))
        media = probe_file(self.api.ffprobe, job["output"])
        self.assertEqual(len(media["subtitles"]), 1)


if __name__ == "__main__":
    unittest.main()
