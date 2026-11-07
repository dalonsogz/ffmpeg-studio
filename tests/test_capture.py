"""Pruebas de la captura de pantalla, ventana y webcam."""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.command import (  # noqa: E402
    build_capture_commands,
    validate_capture,
)
from core.ffmpeg import find_ffmpeg, ffprobe_beside  # noqa: E402
from core.options import default_options  # noqa: E402
from core.probe import probe_file  # noqa: E402
from core.runner import JobRunner  # noqa: E402

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FFMPEG = find_ffmpeg(APP_ROOT, {})
FFPROBE = ffprobe_beside(FFMPEG) if FFMPEG else None


def build(**overrides):
    options = default_options(task="capture", **overrides)
    return build_capture_commands(options=options, output_path="C:/out.mp4")["commands"][0]


class CaptureCommandTests(unittest.TestCase):
    def test_screen_capture(self):
        args = build(captureSource="screen", captureDuration=10, captureFps=30)
        self.assertEqual(args[args.index("-f") + 1], "gdigrab")
        self.assertEqual(args[args.index("-i") + 1], "desktop")
        self.assertEqual(args[args.index("-t") + 1], "10.0")
        self.assertEqual(args[args.index("-framerate") + 1], "30")

    def test_window_capture_uses_title(self):
        args = build(captureSource="window", captureTitle="Documento", captureDuration=5)
        self.assertEqual(args[args.index("-i") + 1], "title=Documento")

    def test_camera_capture_uses_dshow(self):
        args = build(captureSource="camera", captureDevice="HD WebCam", captureDuration=5)
        self.assertEqual(args[args.index("-f") + 1], "dshow")
        self.assertEqual(args[args.index("-i") + 1], "video=HD WebCam")

    def test_open_ended_capture_has_no_duration(self):
        args = build(captureDuration=0)
        self.assertNotIn("-t", args)


class CaptureValidationTests(unittest.TestCase):
    def test_window_needs_title(self):
        issues = validate_capture(options=default_options(task="capture", captureSource="window", captureTitle=""))
        self.assertTrue(any("título" in i["message"] for i in issues))

    def test_camera_needs_device(self):
        issues = validate_capture(options=default_options(task="capture", captureSource="camera", captureDevice=" "))
        self.assertTrue(any("cámara" in i["message"] for i in issues))

    def test_bad_fps(self):
        issues = validate_capture(options=default_options(task="capture", captureFps=120))
        self.assertTrue(any("fps" in i["message"] for i in issues))


@unittest.skipUnless(FFMPEG and FFPROBE, "FFmpeg no disponible")
class CaptureIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp_root = os.path.join(APP_ROOT, ".tmp")
        os.makedirs(tmp_root, exist_ok=True)
        cls.work = tempfile.mkdtemp(prefix="capture-", dir=tmp_root)
        cls.runner = JobRunner(FFMPEG)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, ignore_errors=True)

    def test_screen_capture_records_two_seconds(self):
        output = os.path.join(self.work, "captura.mp4")
        options = default_options(task="capture", captureDuration=2, captureFps=10)
        built = build_capture_commands(options=options, output_path=output)
        result = self.runner.run_job(job_id="captura", commands=built["commands"], duration=2)
        if not result["ok"]:
            self.skipTest(f"Captura no disponible en este entorno: {result.get('error')}")
        media = probe_file(FFPROBE, output)
        self.assertGreater(media["video"]["width"], 0)
        self.assertLess(abs(media["duration"] - 2), 0.8)


class CaptureApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app as studio

        tmp_root = os.path.join(APP_ROOT, ".tmp")
        os.makedirs(tmp_root, exist_ok=True)
        cls.tmp = tempfile.mkdtemp(prefix="capture-api-", dir=tmp_root)
        cls.api = studio.Api(settings_file=os.path.join(cls.tmp, "settings.json"),
                             enable_hardware_detection=False)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_preview_builds_capture_command(self):
        result = self.api.preview([], default_options(task="capture", captureDuration=10))
        self.assertTrue(result["ok"], result.get("issues"))
        self.assertIn("gdigrab", result["preview"])
        self.assertIn("desktop", result["preview"])

    def test_job_has_no_input_files(self):
        built = self.api._build_capture_job(default_options(task="capture", captureDuration=10), self.tmp)
        self.assertTrue(built["ok"], built.get("issues"))
        job = built["job"]
        self.assertEqual(job["inputs"], [])
        self.assertEqual(job["task"], "capture")
        self.assertEqual(job["duration"], 10.0)
        self.assertTrue(job["output"].endswith(".mp4"))


if __name__ == "__main__":
    unittest.main()
