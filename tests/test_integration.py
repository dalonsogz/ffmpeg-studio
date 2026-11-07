"""Pruebas de integración: ejecutan FFmpeg de verdad sobre un vídeo de muestra."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.command import (  # noqa: E402
    build_concat_commands,
    build_job_commands,
    write_concat_list,
)
from core.ffmpeg import find_ffmpeg, ffprobe_beside  # noqa: E402
from core.options import default_options  # noqa: E402
from core.probe import probe_file  # noqa: E402
from core.runner import JobRunner  # noqa: E402

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(APP_ROOT, "..", ".probe", "media", "base.mp4")
FFMPEG = find_ffmpeg(APP_ROOT, {})
FFPROBE = ffprobe_beside(FFMPEG) if FFMPEG else None
READY = bool(FFMPEG and FFPROBE and os.path.isfile(SAMPLE))
SKIP = "No hay binarios de FFmpeg o vídeo de muestra disponibles"


@unittest.skipUnless(READY, SKIP)
class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp_root = os.path.join(APP_ROOT, ".tmp")
        os.makedirs(tmp_root, exist_ok=True)
        cls.work = tempfile.mkdtemp(prefix="test-", dir=tmp_root)
        cls.media = probe_file(FFPROBE, SAMPLE)
        cls.runner = JobRunner(FFMPEG)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, ignore_errors=True)

    def run_options(self, options, name):
        output = os.path.join(self.work, name)
        built = build_job_commands(
            input_path=SAMPLE, output_path=output, options=options,
            media=self.media, passlog_base=os.path.join(self.work, "pass"),
        )
        result = self.runner.run_job(
            job_id=name, commands=built["commands"], duration=self.media["duration"],
        )
        self.assertTrue(result["ok"], result.get("error"))
        return output

    def test_probe_sample(self):
        self.assertGreater(self.media["duration"], 2.5)
        self.assertEqual(self.media["video"]["width"], 1280)
        self.assertTrue(self.media["audios"])

    def test_exact_trim_duration(self):
        output = self.run_options(default_options(
            videoCodec="libx264", quality=24, trim={"enabled": True, "start": 0.5, "end": 1.5, "mode": "exact"},
        ), "trim.mp4")
        out = probe_file(FFPROBE, output)
        self.assertLess(abs(out["duration"] - 1.0), 0.2)

    def test_gif_generation(self):
        output = self.run_options(default_options(
            task="gif", container="gif", videoCodec="gif", gifWidth=320, gifFps=10,
        ), "anim.gif")
        self.assertGreater(os.path.getsize(output), 5000)

    def test_thumbnail_width(self):
        output = self.run_options(default_options(
            task="image", container="jpg", videoCodec="mjpeg", imageTime=1, maxWidth=320,
        ), "thumb.jpg")
        out = probe_file(FFPROBE, output)
        self.assertEqual(out["video"]["width"], 320)

    def test_two_pass_with_same_streams(self):
        output = self.run_options(default_options(
            qualityMode="bitrate", videoBitrate="1M", twoPass=True,
            maxWidth=640, maxHeight=360, audioBitrate="96k",
        ), "twopass.mp4")
        out = probe_file(FFPROBE, output)
        self.assertEqual(out["video"]["width"], 640)

    # ---- unión de clips ----

    def make_clip(self, name, size, seconds):
        path = os.path.join(self.work, name)
        subprocess.run([
            FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=25",
            "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=48000",
            "-t", str(seconds),
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30",
            "-c:a", "aac", "-b:a", "96k", path,
        ], check=True, creationflags=0x08000000)
        return path

    def test_concat_copy_is_exact_and_fast(self):
        list_path = os.path.join(self.work, "lista.txt")
        write_concat_list([SAMPLE, SAMPLE], list_path)
        output = os.path.join(self.work, "unido-copy.mp4")
        built = build_concat_commands(
            inputs=[SAMPLE, SAMPLE], output_path=output,
            options=default_options(task="concat", concatMode="copy"),
            medias=[self.media, self.media], list_path=list_path,
        )
        result = self.runner.run_job(
            job_id="concat-copy", commands=built["commands"], duration=self.media["duration"] * 2,
        )
        self.assertTrue(result["ok"], result.get("error"))
        out = probe_file(FFPROBE, output)
        self.assertLess(abs(out["duration"] - self.media["duration"] * 2), 0.6)

    def test_concat_reencode_mixed_resolutions(self):
        small = self.make_clip("clip-360.mp4", "640x360", 2)
        medias = [self.media, probe_file(FFPROBE, small)]
        output = os.path.join(self.work, "unido-reencode.mp4")
        built = build_concat_commands(
            inputs=[SAMPLE, small], output_path=output,
            options=default_options(task="concat", concatMode="reencode"),
            medias=medias,
        )
        result = self.runner.run_job(
            job_id="concat-reencode", commands=built["commands"],
            duration=sum(m["duration"] for m in medias),
        )
        self.assertTrue(result["ok"], result.get("error"))
        out = probe_file(FFPROBE, output)
        self.assertEqual((out["video"]["width"], out["video"]["height"]), (1280, 720))
        self.assertLess(abs(out["duration"] - sum(m["duration"] for m in medias)), 1.0)


if __name__ == "__main__":
    unittest.main()
