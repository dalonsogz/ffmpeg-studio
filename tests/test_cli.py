"""Pruebas del modo CLI (conversión sin interfaz) y de la estimación expuesta."""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as studio  # noqa: E402
from core.ffmpeg import find_ffmpeg, ffprobe_beside  # noqa: E402
from core.options import default_options  # noqa: E402
from core.probe import probe_file  # noqa: E402

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(APP_ROOT, "..", ".probe", "media", "base.mp4")
FFMPEG = find_ffmpeg(APP_ROOT, {})
FFPROBE = ffprobe_beside(FFMPEG) if FFMPEG else None
READY = bool(FFMPEG and FFPROBE and os.path.isfile(SAMPLE))


@unittest.skipUnless(READY, "Faltan binarios de FFmpeg o vídeo de muestra")
class CliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp_root = os.path.join(APP_ROOT, ".tmp")
        os.makedirs(tmp_root, exist_ok=True)
        cls.tmp = tempfile.mkdtemp(prefix="cli-", dir=tmp_root)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_cli_converts_file(self):
        target = os.path.join(self.tmp, "salida.mp4")
        code = studio.run_cli(["--cli", SAMPLE, target, "--crf", "28", "--width", "640"])
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isfile(target))
        media = probe_file(FFPROBE, target)
        self.assertEqual(media["video"]["width"], 640)

    def test_cli_rejects_unknown_preset(self):
        target = os.path.join(self.tmp, "x.mp4")
        code = studio.run_cli(["--cli", SAMPLE, target, "--preset", "no-existe"])
        self.assertEqual(code, 2)
        self.assertFalse(os.path.exists(target))

    def test_cli_rejects_missing_input(self):
        code = studio.run_cli(["--cli", os.path.join(self.tmp, "nada.mp4"), os.path.join(self.tmp, "x.mp4")])
        self.assertEqual(code, 2)

    def test_cli_leaves_no_temp_files(self):
        target = os.path.join(self.tmp, "limpio.mp4")
        code = studio.run_cli(["--cli", SAMPLE, target])
        self.assertEqual(code, 0)
        leftovers = [name for name in os.listdir(self.tmp) if name.startswith(".ffgui-")]
        self.assertEqual(leftovers, [])

    def test_preview_exposes_estimate(self):
        api = studio.Api(settings_file=os.path.join(self.tmp, "settings.json"),
                         enable_hardware_detection=False)
        result = api.preview([SAMPLE], default_options(maxWidth=640, maxHeight=360))
        self.assertTrue(result["ok"], result.get("issues"))
        self.assertIsInstance(result["estimatedBytes"], int)
        self.assertGreater(result["estimatedBytes"], 0)


if __name__ == "__main__":
    unittest.main()
