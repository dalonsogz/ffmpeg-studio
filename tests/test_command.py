"""Pruebas del constructor de comandos y del validador."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.command import build_job_commands, compute_scale, validate_job  # noqa: E402
from core.options import default_options  # noqa: E402

MEDIA_1080 = {
    "duration": 10,
    "video": {"width": 1920, "height": 1080, "codec": "h264"},
    "audios": [{"index": 1, "codec": "aac"}],
    "subtitles": [],
}

MEDIA_4K = {
    "duration": 10,
    "video": {"width": 3840, "height": 2160, "codec": "hevc"},
    "audios": [{"index": 1, "codec": "aac"}],
    "subtitles": [],
}


def build(overrides=None, media=MEDIA_1080):
    options = default_options(**(overrides or {}))
    return build_job_commands(
        input_path="C:/in.mp4",
        output_path="C:/out.mp4",
        options=options,
        media=media,
        passlog_base="C:/tmp/pass",
    )


class ScaleTests(unittest.TestCase):
    def test_no_upscale(self):
        self.assertEqual(compute_scale(MEDIA_4K, 1920, 1080), "scale=1920:1080:flags=lanczos")
        self.assertIsNone(compute_scale(MEDIA_1080, 1920, 1080))
        self.assertEqual(compute_scale(MEDIA_1080, 1280, 720), "scale=1280:720:flags=lanczos")
        self.assertIsNone(compute_scale({"video": {"width": 1920, "height": 1080}}, 0, 0))


class CommandTests(unittest.TestCase):
    def test_basic_conversion(self):
        commands = build({"container": "mp4", "videoCodec": "libx264", "quality": 21})["commands"]
        self.assertEqual(len(commands), 1)
        args = commands[0]
        self.assertEqual(args[args.index("-i") + 1], "C:/in.mp4")
        self.assertEqual(args[args.index("-c:v") + 1], "libx264")
        self.assertEqual(args[args.index("-crf") + 1], "21")
        self.assertEqual(args[args.index("-preset") + 1], "medium")
        self.assertEqual(args[args.index("-pix_fmt") + 1], "yuv420p")
        self.assertEqual(args[args.index("-c:a") + 1], "aac")
        self.assertIn("+faststart", args)
        self.assertEqual(args[-1], "C:/out.mp4")

    def test_two_pass_symmetry(self):
        commands = build({"qualityMode": "bitrate", "videoBitrate": "2M", "twoPass": True})["commands"]
        self.assertEqual(len(commands), 2)
        first, second = commands
        self.assertEqual(first[first.index("-pass") + 1], "1")
        self.assertEqual(first[first.index("-f") + 1], "null")
        self.assertNotIn("+faststart", first)
        self.assertEqual(first[-1], "NUL")
        self.assertEqual(second[second.index("-pass") + 1], "2")
        self.assertIn("+faststart", second)
        self.assertEqual(second[-1], "C:/out.mp4")
        for command in commands:
            self.assertIn("-passlogfile", command)
            self.assertIn("-c:a", command)

    def test_trim_arguments(self):
        args = build({"trim": {"enabled": True, "start": 5, "end": 8, "mode": "exact"}})["commands"][0]
        self.assertLess(args.index("-ss"), args.index("-i"))
        self.assertEqual(args[args.index("-t") + 1], "3.000")

    def test_gif_palette(self):
        args = build({"task": "gif", "container": "gif", "videoCodec": "gif",
                      "gifWidth": 480, "gifFps": 12})["commands"][0]
        chain = args[args.index("-vf") + 1]
        self.assertIn("palettegen", chain)
        self.assertIn("paletteuse", chain)
        self.assertIn("fps=12", chain)
        self.assertIn("-an", args)

    def test_thumbnail(self):
        args = build({"task": "image", "container": "jpg", "videoCodec": "mjpeg",
                      "imageTime": 2, "maxWidth": 320})["commands"][0]
        self.assertEqual(args[args.index("-frames:v") + 1], "1")
        self.assertEqual(args[args.index("-update") + 1], "1")
        self.assertEqual(args[args.index("-ss") + 1], "2.000")
        self.assertLess(args.index("-ss"), args.index("-i"))

    def test_audio_extraction(self):
        args = build({"task": "audio", "container": "mp3", "videoCodec": "none",
                      "audioCodec": "libmp3lame", "audioBitrate": "192k"})["commands"][0]
        self.assertIn("-vn", args)
        self.assertEqual(args[args.index("-c:a") + 1], "libmp3lame")
        self.assertEqual(args[args.index("-b:a") + 1], "192k")

    def test_remux_maps_all_streams(self):
        args = build({"videoCodec": "copy", "audioCodec": "copy", "container": "mkv"})["commands"][0]
        self.assertEqual(args[args.index("-map") + 1], "0")
        self.assertEqual(args[args.index("-c") + 1], "copy")


class ValidationTests(unittest.TestCase):
    def test_cannot_scale_without_reencoding(self):
        options = default_options(videoCodec="copy", audioCodec="copy", maxWidth=1280, maxHeight=720)
        issues = validate_job(options=options, media=MEDIA_4K,
                              output_path="C:/out.mkv", input_path="C:/in.mkv")
        self.assertTrue(any(i["level"] == "error" and "resolución" in i["message"] for i in issues))

    def test_invalid_trim_and_same_output(self):
        options = default_options(trim={"enabled": True, "start": 5, "end": 2, "mode": "exact"})
        issues = validate_job(options=options, media=MEDIA_1080,
                              output_path="C:/in.mp4", input_path="C:/in.mp4")
        self.assertTrue(any("sobrescribir" in i["message"] for i in issues))
        self.assertTrue(any("posterior al inicio" in i["message"] for i in issues))

    def test_audio_task_without_audio(self):
        options = default_options(task="audio", container="mp3", videoCodec="none")
        silent = {**MEDIA_1080, "audios": []}
        issues = validate_job(options=options, media=silent,
                              output_path="C:/out.mp3", input_path="C:/in.mp4")
        self.assertTrue(any(i["level"] == "error" and "audio" in i["message"] for i in issues))

    def test_incompatible_codec(self):
        options = default_options(container="webm", videoCodec="libx264")
        issues = validate_job(options=options, media=MEDIA_1080,
                              output_path="C:/out.webm", input_path="C:/in.mp4")
        self.assertTrue(any("no admite" in i["message"] for i in issues))


if __name__ == "__main__":
    unittest.main()
