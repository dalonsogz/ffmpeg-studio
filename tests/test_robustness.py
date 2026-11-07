"""Pruebas de robustez: espacio en disco, escritura atómica y reintento GPU→CPU."""

import glob
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.command import software_fallback_codec  # noqa: E402
from core.errors import looks_like_hardware_failure  # noqa: E402
from core.options import default_options  # noqa: E402
from core.queue import JobQueue  # noqa: E402
from core.storage import (  # noqa: E402
    estimate_output_bytes,
    has_space,
    parse_bitrate,
    space_error_message,
)

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(APP_ROOT, "..", ".probe", "media", "base.mp4")

MEDIA = {"duration": 60.0, "size": 100 * 1024 * 1024, "video": {"width": 1920, "height": 1080}, "audios": [{}]}


class StorageTests(unittest.TestCase):
    def test_parse_bitrate(self):
        self.assertEqual(parse_bitrate("2M"), 2_000_000)
        self.assertEqual(parse_bitrate("160k"), 160_000)
        self.assertEqual(parse_bitrate(""), 0.0)

    def test_copy_is_close_to_source_size(self):
        estimate = estimate_output_bytes(
            default_options(videoCodec="copy", audioCodec="copy"), [MEDIA],
        )
        self.assertGreater(estimate, MEDIA["size"])
        self.assertLess(estimate, MEDIA["size"] * 1.2 + 100 * 1024 * 1024)

    def test_bitrate_mode_scales_with_duration(self):
        options = default_options(qualityMode="bitrate", videoBitrate="2M", audioBitrate="128k")
        ten_minutes = estimate_output_bytes(options, [{**MEDIA, "duration": 600.0}])
        twenty_minutes = estimate_output_bytes(options, [{**MEDIA, "duration": 1200.0}])
        self.assertGreater(twenty_minutes, ten_minutes * 1.8)

    def test_small_tasks_have_minimum(self):
        self.assertGreaterEqual(estimate_output_bytes(default_options(task="image"), [MEDIA]), 20 * 1024 * 1024)

    def test_space_check_uses_free_bytes(self):
        with mock.patch("core.storage.free_bytes", return_value=1):
            self.assertFalse(has_space(__file__, 10))
            self.assertIn("Espacio insuficiente", space_error_message(__file__, 10))

    def test_space_ok_when_free(self):
        self.assertTrue(has_space(__file__, 1))


class FallbackTests(unittest.TestCase):
    def test_codec_mapping(self):
        self.assertEqual(software_fallback_codec("h264_nvenc"), "libx264")
        self.assertEqual(software_fallback_codec("hevc_qsv"), "libx265")
        self.assertEqual(software_fallback_codec("av1_amf"), "libsvtav1")
        self.assertIsNone(software_fallback_codec("libx264"))
        self.assertIsNone(software_fallback_codec("copy"))

    def test_hardware_failure_detection(self):
        self.assertTrue(looks_like_hardware_failure(["[h264_nvenc @ 0x1] OpenEncodeSessionEx failed"]))
        self.assertTrue(looks_like_hardware_failure([], {"title": "La aceleración por hardware no está disponible."}))
        self.assertFalse(looks_like_hardware_failure(["Invalid data found when processing input"]))


class FakeRunner:
    """Falla la primera vez (GPU) y acierta la segunda (CPU)."""

    def __init__(self, hardware_failure=True):
        self.calls = 0
        self.hardware_failure = hardware_failure

    def run_job(self, *, job_id, commands, duration, durations=None, on_progress=None, on_log=None):
        self.calls += 1
        if self.calls == 1 and self.hardware_failure:
            return {
                "ok": False, "cancelled": False, "code": 1, "durationMs": 1,
                "logLines": ["[h264_nvenc @ 0000] OpenEncodeSessionEx failed: out of memory"],
                "error": {"title": "Fallo de hardware", "detail": "nvenc"},
            }
        return {"ok": True, "cancelled": False, "code": 0, "durationMs": 1, "logLines": [], "error": None}


def fake_job(job_id, output, fallback=True):
    return {
        "id": job_id,
        "input": "in.mp4",
        "inputs": ["in.mp4"],
        "inputName": "in.mp4",
        "clipCount": 1,
        "output": output,
        "tempOutput": None,
        "estimatedBytes": 0,
        "fallback": {"commands": [["-cpu"]], "codec": "libx264"} if fallback else None,
        "commands": [["-gpu"]],
        "duration": 1,
        "task": "video",
        "container": "mp4",
        "label": "Vídeo · MP4",
        "status": "pending",
        "percent": 0,
        "logTail": [],
        "pass": 1,
        "passCount": 1,
    }


class QueueBehaviourTests(unittest.TestCase):
    def wait_done(self, queue, timeout=5):
        deadline = time.time() + timeout
        while time.time() < deadline:
            status = queue.snapshot()["jobs"][0]["status"]
            if status in ("done", "error", "cancelled"):
                return status
            time.sleep(0.02)
        return "timeout"

    def test_retries_on_cpu_after_gpu_failure(self):
        runner = FakeRunner()
        queue = JobQueue(runner)
        queue.add([fake_job("j1", os.path.join(tempfile.gettempdir(), "noop.mp4"))])
        self.assertEqual(self.wait_done(queue), "done")
        self.assertEqual(runner.calls, 2)
        snapshot = queue.snapshot()["jobs"][0]
        self.assertTrue(snapshot["retrying"])
        self.assertIn("GPU", snapshot["logTail"][0])

    def test_no_retry_without_fallback(self):
        runner = FakeRunner()
        queue = JobQueue(runner)
        queue.add([fake_job("j2", os.path.join(tempfile.gettempdir(), "noop.mp4"), fallback=False)])
        self.assertEqual(self.wait_done(queue), "error")
        self.assertEqual(runner.calls, 1)

    def test_blocks_when_no_space(self):
        runner = FakeRunner(hardware_failure=False)
        queue = JobQueue(runner)
        job = fake_job("j3", os.path.join(tempfile.gettempdir(), "noop.mp4"))
        job["estimatedBytes"] = 10 ** 18
        queue.add([job])
        self.assertEqual(self.wait_done(queue), "error")
        self.assertEqual(runner.calls, 0)
        self.assertIn("Espacio insuficiente", queue.snapshot()["jobs"][0]["error"]["title"])


@unittest.skipUnless(os.path.isfile(SAMPLE), "Falta el vídeo de muestra")
class AtomicOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import Api

        tmp_root = os.path.join(APP_ROOT, ".tmp")
        os.makedirs(tmp_root, exist_ok=True)
        cls.tmp = tempfile.mkdtemp(prefix="atomic-", dir=tmp_root)
        cls.api = Api(settings_file=os.path.join(cls.tmp, "settings.json"), enable_hardware_detection=False)
        if not cls.api.ffmpeg:
            raise unittest.SkipTest("FFmpeg no encontrado")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def wait_job(self, job_id, timeout=120):
        deadline = time.time() + timeout
        while time.time() < deadline:
            current = next((j for j in self.api.queue_state()["jobs"] if j["id"] == job_id), None)
            if current and current["status"] in ("done", "error", "cancelled"):
                return current
            time.sleep(0.1)
        return None

    def test_job_writes_atomically(self):
        options = default_options(maxWidth=640, maxHeight=360, quality=28)
        result = self.api.add_to_queue([SAMPLE], options, self.tmp)
        self.assertEqual(result["added"], 1, result.get("rejected"))
        job = result["snapshot"]["jobs"][-1]

        final = self.wait_job(job["id"])
        self.assertIsNotNone(final)
        self.assertEqual(final["status"], "done", final.get("error"))
        self.assertTrue(os.path.isfile(final["output"]))
        leftovers = glob.glob(os.path.join(self.tmp, ".ffgui-*"))
        self.assertEqual(leftovers, [], f"quedaron temporales: {leftovers}")

    def test_job_exposes_fallback_for_hardware_codec(self):
        options = default_options(videoCodec="h264_nvenc", maxWidth=640, maxHeight=360)
        built = self.api._build_job([SAMPLE], options, self.tmp)
        self.assertTrue(built["ok"])
        fallback = built["job"]["fallback"]
        self.assertIsNotNone(fallback)
        self.assertEqual(fallback["codec"], "libx264")
        # La salida real es la definitiva; el comando apunta al temporal.
        self.assertNotIn(".ffgui-", os.path.basename(built["job"]["output"]))
        command = " ".join(built["job"]["commands"][0])
        self.assertIn(".ffgui-", command)

    def test_preview_shows_final_path(self):
        options = default_options(maxWidth=640, maxHeight=360)
        preview = self.api.preview([SAMPLE], options)
        self.assertTrue(preview["ok"])
        self.assertNotIn(".ffgui-", preview["preview"])


if __name__ == "__main__":
    unittest.main()
