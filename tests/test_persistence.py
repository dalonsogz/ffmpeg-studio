"""Pruebas de la cola persistente (guardado y restauración)."""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as studio  # noqa: E402
from core.options import default_options  # noqa: E402

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(APP_ROOT, "..", ".probe", "media", "base.mp4")
READY = os.path.isfile(SAMPLE) and bool(studio.find_ffmpeg(APP_ROOT, {}))


@unittest.skipUnless(READY, "Faltan binarios de FFmpeg o vídeo de muestra")
class QueuePersistenceTests(unittest.TestCase):
    def setUp(self):
        tmp_root = os.path.join(APP_ROOT, ".tmp")
        os.makedirs(tmp_root, exist_ok=True)
        self.tmp = tempfile.mkdtemp(prefix="queue-", dir=tmp_root)
        self.settings = os.path.join(self.tmp, "settings.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def make_api(self, restore=False):
        return studio.Api(settings_file=self.settings,
                          enable_hardware_detection=False,
                          restore_queue=restore)

    def test_pending_job_survives_restart(self):
        api = self.make_api()
        built = api._build_job([SAMPLE], default_options(maxWidth=640, maxHeight=360), self.tmp)
        self.assertTrue(built["ok"], built.get("issues"))
        job = built["job"]
        job["status"] = "pending"

        with api.queue.lock:
            api.queue.jobs = [job]
        api.queue._notify_change()
        self.assertTrue(os.path.isfile(api.queue_file))

        restored = self.make_api(restore=True)
        snapshot = restored.queue.snapshot()
        self.assertEqual(len(snapshot["jobs"]), 1)
        self.assertEqual(snapshot["jobs"][0]["status"], "pending")
        self.assertEqual(snapshot["jobs"][0]["output"], job["output"])
        self.assertEqual(restored.restored_pending, 1)

    def test_history_is_restored(self):
        api = self.make_api()
        built = api._build_job([SAMPLE], default_options(maxWidth=640, maxHeight=360), self.tmp)
        job = built["job"]
        job["status"] = "done"
        job["percent"] = 100
        job["finishedAt"] = 1234567890
        job["commands"] = []
        with api.queue.lock:
            api.queue.jobs = [job]
        api.queue._notify_change()

        restored = self.make_api(restore=True)
        snapshot = restored.queue.snapshot()
        self.assertEqual(len(snapshot["jobs"]), 1)
        self.assertEqual(snapshot["jobs"][0]["status"], "done")
        self.assertEqual(restored.restored_pending, 0)

    def test_missing_input_is_dropped(self):
        api = self.make_api()
        with open(api.queue_file, "w", encoding="utf-8") as handle:
            handle.write('{"pending": [{"inputs": ["C:/no/existe.mp4"], "options": {}, "output": "C:/x.mp4"}], "history": []}')
        restored = self.make_api(restore=True)
        self.assertEqual(restored.queue.snapshot()["jobs"], [])


if __name__ == "__main__":
    unittest.main()
