"""Pruebas de velocidad, fps, encuadre y hoja de contactos."""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.command import (  # noqa: E402
    build_concat_commands,
    build_job_commands,
    build_sheet_commands,
    build_video_filters,
    framing_filters,
    sheet_grid,
    speed_filters,
    validate_job,
    validate_sheet,
)
from core.ffmpeg import find_ffmpeg, ffprobe_beside  # noqa: E402
from core.options import default_options  # noqa: E402
from core.probe import probe_file  # noqa: E402
from core.runner import JobRunner  # noqa: E402

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(APP_ROOT, "..", ".probe", "media", "base.mp4")
FFMPEG = find_ffmpeg(APP_ROOT, {})
FFPROBE = ffprobe_beside(FFMPEG) if FFMPEG else None

MEDIA = {
    "path": "C:/videos/entrada.mp4",
    "duration": 10.0,
    "video": {"width": 1920, "height": 1080, "codec": "h264", "pixFmt": "yuv420p", "fps": 30},
    "audios": [{"codec": "aac"}],
    "subtitles": [],
}


def build(overrides):
    options = default_options(**overrides)
    return build_job_commands(
        input_path="C:/videos/entrada.mp4",
        output_path="C:/videos/salida.mp4",
        options=options,
        media=MEDIA,
        passlog_base="C:/videos/pass",
    )


class SpeedTests(unittest.TestCase):
    def test_normal_speed_adds_nothing(self):
        self.assertEqual(speed_filters({"speed": 1.0}), ([], []))

    def test_double_speed(self):
        video, audio = speed_filters({"speed": 2.0})
        self.assertEqual(video, ["setpts=PTS/2"])
        self.assertEqual(audio, ["atempo=2"])

    def test_half_speed(self):
        video, audio = speed_filters({"speed": 0.5})
        self.assertEqual(video, ["setpts=PTS/0.5"])
        self.assertEqual(audio, ["atempo=0.5"])

    def test_quarter_speed_chains_atempo(self):
        _, audio = speed_filters({"speed": 0.25})
        self.assertEqual(audio, ["atempo=0.5", "atempo=0.5"])

    def test_four_times_chains_atempo(self):
        _, audio = speed_filters({"speed": 4.0})
        self.assertEqual(audio, ["atempo=2", "atempo=2"])

    def test_command_includes_speed_filters(self):
        args = build({"speed": 2.0})["commands"][0]
        vf = args[args.index("-vf") + 1]
        af = args[args.index("-af") + 1]
        self.assertIn("setpts=PTS/2", vf)
        self.assertIn("atempo=2", af)

    def test_fps_adds_output_rate(self):
        args = build({"fps": 25})["commands"][0]
        self.assertEqual(args[args.index("-r") + 1], "25")

    def test_audio_task_supports_speed(self):
        args = build({"task": "audio", "container": "mp3", "videoCodec": "none",
                      "audioCodec": "libmp3lame", "speed": 1.5})["commands"][0]
        self.assertIn("atempo=1.5", args[args.index("-af") + 1])


class FramingTests(unittest.TestCase):
    def test_crop_rotate_flip_order(self):
        filters = framing_filters({
            "crop": {"left": 10, "top": 20, "right": 30, "bottom": 40},
            "rotate": 90,
            "flip": "both",
        })
        self.assertEqual(filters, [
            "crop=iw-10-30:ih-20-40:10:20",
            "transpose=1",
            "hflip",
            "vflip",
        ])

    def test_rotation_swaps_dimensions_for_scale(self):
        filters = build_video_filters(MEDIA, default_options(rotate=90, maxWidth=540, maxHeight=960))
        self.assertIn("transpose=1", filters)
        # Tras rotar, el vídeo es 1080x1920; el límite 540x960 debe respetar esa proporción.
        self.assertIn("scale=540:960:flags=lanczos", filters)

    def test_180_uses_two_flips(self):
        self.assertEqual(framing_filters({"rotate": 180}), ["hflip", "vflip"])


class ValidationTests(unittest.TestCase):
    def test_copy_cannot_change_speed(self):
        issues = validate_job(
            options=default_options(videoCodec="copy", audioCodec="copy", speed=2.0),
            media=MEDIA, output_path="C:/out.mp4", input_path="C:/in.mp4",
        )
        self.assertTrue(any("velocidad" in i["message"] for i in issues))

    def test_copy_cannot_change_fps(self):
        issues = validate_job(
            options=default_options(videoCodec="copy", audioCodec="copy", fps=24),
            media=MEDIA, output_path="C:/out.mp4", input_path="C:/in.mp4",
        )
        self.assertTrue(any("fotogramas" in i["message"] for i in issues))

    def test_copy_cannot_crop(self):
        issues = validate_job(
            options=default_options(videoCodec="copy", audioCodec="copy",
                                    crop={"left": 10, "top": 0, "right": 0, "bottom": 0}),
            media=MEDIA, output_path="C:/out.mp4", input_path="C:/in.mp4",
        )
        self.assertTrue(any("encuadre" in i["message"] for i in issues))

    def test_speed_with_copied_audio_is_rejected(self):
        issues = validate_job(
            options=default_options(videoCodec="libx264", audioCodec="copy", speed=2.0),
            media=MEDIA, output_path="C:/out.mp4", input_path="C:/in.mp4",
        )
        self.assertTrue(any("audio" in i["message"].lower() for i in issues))


class SheetTests(unittest.TestCase):
    def test_grid_presets(self):
        self.assertEqual(sheet_grid(9), (3, 3))
        self.assertEqual(sheet_grid(4), (2, 2))
        self.assertEqual(sheet_grid(12), (4, 3))

    def test_command_builds_tile(self):
        built = build_sheet_commands(media=MEDIA, options=default_options(task="sheet"), output_path="C:/hoja.jpg")
        args = built["commands"][0]
        chain = args[args.index("-vf") + 1]
        self.assertIn("tile=3x3", chain)
        self.assertIn("fps=1/", chain)
        self.assertEqual(args[args.index("-frames:v") + 1], "1")
        self.assertEqual(args[args.index("-update") + 1], "1")

    def test_sheet_requires_video(self):
        media = {**MEDIA, "video": None}
        issues = validate_sheet(media=media, options=default_options(task="sheet"),
                                output_path="C:/h.jpg", input_path="C:/a.mp4")
        self.assertTrue(any("vídeo" in i["message"] for i in issues))


class LoudnessTests(unittest.TestCase):
    def test_video_filter(self):
        args = build({"normalizeLoudness": True, "loudnessTarget": -14})["commands"][0]
        self.assertIn("loudnorm=I=-14", args[args.index("-af") + 1])

    def test_audio_task_filter(self):
        args = build({
            "task": "audio", "container": "mp3", "videoCodec": "none",
            "audioCodec": "libmp3lame", "normalizeLoudness": True, "loudnessTarget": -23,
        })["commands"][0]
        self.assertIn("loudnorm=I=-23", args[args.index("-af") + 1])

    def test_requires_audio_reencode(self):
        issues = validate_job(
            options=default_options(normalizeLoudness=True, audioCodec="copy"),
            media=MEDIA, output_path="C:/out.mp4", input_path="C:/in.mp4",
        )
        self.assertTrue(any("Normalizar" in i["message"] for i in issues))


@unittest.skipUnless(FFMPEG and FFPROBE and os.path.isfile(SAMPLE), "Faltan binarios o muestra")
class EffectsIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp_root = os.path.join(APP_ROOT, ".tmp")
        os.makedirs(tmp_root, exist_ok=True)
        cls.work = tempfile.mkdtemp(prefix="fx-", dir=tmp_root)
        cls.runner = JobRunner(FFMPEG)
        cls.base = probe_file(FFPROBE, SAMPLE)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, ignore_errors=True)

    def _run(self, options, name):
        out = os.path.join(self.work, name)
        built = build_job_commands(
            input_path=SAMPLE, output_path=out, options=options,
            media=self.base, passlog_base=os.path.join(self.work, "pass"),
        )
        result = self.runner.run_job(job_id=name, commands=built["commands"],
                                     duration=self.base["duration"])
        self.assertTrue(result["ok"], result.get("error"))
        return out

    def test_double_speed_halves_duration(self):
        out = self._run(default_options(speed=2.0, quality=28), "rapido.mp4")
        media = probe_file(FFPROBE, out)
        self.assertLess(abs(media["duration"] - self.base["duration"] / 2), 0.35)

    def test_contact_sheet_dimensions(self):
        out = os.path.join(self.work, "hoja.jpg")
        built = build_sheet_commands(
            media=self.base,
            options=default_options(task="sheet", sheetCount=9, sheetWidth=320),
            output_path=out,
        )
        result = self.runner.run_job(job_id="hoja", commands=built["commands"], duration=None)
        self.assertTrue(result["ok"], result.get("error"))
        media = probe_file(FFPROBE, out)
        self.assertEqual(media["video"]["width"], 3 * 320)


if __name__ == "__main__":
    unittest.main()
