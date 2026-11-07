"""Pruebas de la unión de clips (comandos, filtros y validación)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.command import (  # noqa: E402
    build_concat_commands,
    concat_target_size,
    validate_concat,
)
from core.options import default_options  # noqa: E402

MEDIA_A = {
    "name": "a.mp4",
    "duration": 3.0,
    "video": {"width": 1280, "height": 720, "codec": "h264", "pixFmt": "yuv420p", "fps": 30},
    "audios": [{"codec": "aac", "sampleRate": 48000, "channels": 2}],
    "subtitles": [],
}

MEDIA_B = {
    "name": "b.mp4",
    "duration": 2.0,
    "video": {"width": 640, "height": 360, "codec": "h264", "pixFmt": "yuv420p", "fps": 25},
    "audios": [{"codec": "aac", "sampleRate": 48000, "channels": 2}],
    "subtitles": [],
}

MEDIA_SILENT = {
    "name": "mudo.mp4",
    "duration": 2.0,
    "video": {"width": 1280, "height": 720, "codec": "h264", "pixFmt": "yuv420p", "fps": 30},
    "audios": [],
    "subtitles": [],
}


def build(mode, medias, inputs=None):
    return build_concat_commands(
        inputs=inputs or ["C:/a.mp4", "C:/b.mp4"],
        output_path="C:/out.mp4",
        options=default_options(task="concat", concatMode=mode),
        medias=medias,
        list_path="C:/lista.txt",
    )


class ConcatCommandTests(unittest.TestCase):
    def test_copy_uses_concat_demuxer(self):
        commands = build("copy", [MEDIA_A, MEDIA_B])["commands"]
        self.assertEqual(len(commands), 1)
        args = commands[0]
        self.assertEqual(args[args.index("-f") + 1], "concat")
        self.assertEqual(args[args.index("-safe") + 1], "0")
        self.assertEqual(args[args.index("-i") + 1], "C:/lista.txt")
        self.assertEqual(args[args.index("-c") + 1], "copy")
        self.assertEqual(args[-1], "C:/out.mp4")

    def test_reencode_normalizes_and_concatenates(self):
        args = build("reencode", [MEDIA_A, MEDIA_B])["commands"][0]
        graph = args[args.index("-filter_complex") + 1]

        self.assertIn("concat=n=2:v=1:a=1[v][a]", graph)
        self.assertIn("[0:v]scale=1280:720", graph)
        self.assertIn("force_original_aspect_ratio=decrease", graph)
        self.assertIn("pad=1280:720", graph)
        self.assertIn("fps=30", graph)
        self.assertIn("aresample=48000", graph)
        self.assertEqual(args[args.index("-map") + 1], "[v]")
        self.assertEqual(args[args.index("-c:v") + 1], "libx264")

    def test_missing_audio_gets_silence(self):
        args = build("reencode", [MEDIA_A, MEDIA_SILENT])["commands"][0]
        self.assertIn("anullsrc=channel_layout=stereo:sample_rate=48000", args)
        graph = args[args.index("-filter_complex") + 1]
        # El segundo clip toma el audio del input extra (índice 2).
        self.assertIn("[2:a]aresample=48000", graph)

    def test_all_silent_concatenates_video_only(self):
        args = build("reencode", [MEDIA_SILENT, MEDIA_SILENT])["commands"][0]
        graph = args[args.index("-filter_complex") + 1]
        self.assertIn("concat=n=2:v=1:a=0[v]", graph)
        self.assertIn("-an", args)
        self.assertNotIn("anullsrc", args)

    def test_target_size_uses_first_clip(self):
        self.assertEqual(concat_target_size([MEDIA_A, MEDIA_B], {"maxWidth": 1920, "maxHeight": 1080}), (1280, 720))

    def test_target_size_respects_limit(self):
        self.assertEqual(concat_target_size([MEDIA_A], {"maxWidth": 640, "maxHeight": 360}), (640, 360))


class ConcatValidationTests(unittest.TestCase):
    def test_mismatched_clips_rejected_in_copy_mode(self):
        issues = validate_concat(
            inputs=["C:/a.mp4", "C:/b.mp4"],
            options=default_options(task="concat", concatMode="copy"),
            medias=[MEDIA_A, MEDIA_B],
            output_path="C:/out.mp4",
        )
        self.assertTrue(any(i["level"] == "error" and "Recomponer" in i["message"] for i in issues))

    def test_matching_clips_pass_copy_mode(self):
        issues = validate_concat(
            inputs=["C:/a.mp4", "C:/b.mp4"],
            options=default_options(task="concat", concatMode="copy"),
            medias=[MEDIA_A, {"**": "", **MEDIA_A, "name": "b.mp4"}],
            output_path="C:/out.mp4",
        )
        self.assertFalse([i for i in issues if i["level"] == "error"])

    def test_requires_two_clips(self):
        issues = validate_concat(
            inputs=["C:/a.mp4"],
            options=default_options(task="concat", concatMode="copy"),
            medias=[MEDIA_A],
            output_path="C:/out.mp4",
        )
        self.assertTrue(any("al menos dos" in i["message"] for i in issues))

    def test_output_cannot_overwrite_input(self):
        issues = validate_concat(
            inputs=["C:/a.mp4", "C:/b.mp4"],
            options=default_options(task="concat", concatMode="copy"),
            medias=[MEDIA_A, MEDIA_B],
            output_path="C:/a.mp4",
        )
        self.assertTrue(any("sobrescribir" in i["message"] for i in issues))


if __name__ == "__main__":
    unittest.main()
