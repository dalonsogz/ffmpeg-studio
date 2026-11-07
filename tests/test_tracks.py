"""Pruebas de selección de pistas y fundidos al unir."""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.command import (  # noqa: E402
    build_concat_commands,
    build_job_commands,
    validate_concat,
    validate_job,
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
    "path": "C:/videos/entrada.mkv",
    "duration": 10.0,
    "video": {"width": 1920, "height": 1080, "codec": "h264", "pixFmt": "yuv420p", "fps": 30},
    "audios": [
        {"codec": "aac", "language": "spa", "channels": 2},
        {"codec": "ac3", "language": "eng", "channels": 6},
    ],
    "subtitles": [
        {"codec": "subrip", "language": "spa"},
        {"codec": "hdmv_pgs_subtitle", "language": "eng"},
    ],
}


def build(overrides, media=MEDIA, container="mp4"):
    settings = {"task": "video", "container": container}
    settings.update(overrides)
    options = default_options(**settings)
    return build_job_commands(
        input_path="C:/videos/entrada.mkv",
        output_path="C:/videos/salida." + container,
        options=options,
        media=media,
        passlog_base="C:/videos/pass",
    )["commands"][0]


class TrackSelectionTests(unittest.TestCase):
    def test_auto_does_not_map(self):
        args = build({})
        self.assertNotIn("-map", args)
        self.assertIn("-sn", args)

    def test_all_audio_tracks(self):
        args = build({"audioTrack": -2})
        self.assertEqual(args[args.index("-map") + 1], "0:v:0")
        self.assertIn("0:a", args)

    def test_specific_audio_track(self):
        args = build({"audioTrack": 1})
        self.assertIn("0:a:1", args)

    def test_subtitle_track_maps_and_converts(self):
        args = build({"subtitleTrack": 0, "container": "mp4"})
        self.assertIn("0:s:0", args)
        self.assertEqual(args[args.index("-c:s") + 1], "mov_text")

    def test_subtitle_copy_in_mkv(self):
        args = build({"subtitleTrack": 0, "container": "mkv"})
        self.assertEqual(args[args.index("-c:s") + 1], "copy")

    def test_remux_keeps_everything_by_default(self):
        args = build({"videoCodec": "copy", "audioCodec": "copy", "container": "mkv"})
        self.assertEqual(args[args.index("-map") + 1], "0")
        self.assertEqual(args[args.index("-c") + 1], "copy")

    def test_remux_with_track_selection(self):
        args = build({"videoCodec": "copy", "audioCodec": "copy",
                      "container": "mkv", "audioTrack": 0})
        self.assertIn("0:a:0", args)
        self.assertIn("copy", args)

    def test_invalid_audio_track(self):
        issues = validate_job(
            options=default_options(audioTrack=5),
            media=MEDIA, output_path="C:/out.mp4", input_path="C:/in.mkv",
        )
        self.assertTrue(any("pista de audio" in i["message"] for i in issues))

    def test_invalid_subtitle_track(self):
        issues = validate_job(
            options=default_options(subtitleTrack=7),
            media=MEDIA, output_path="C:/out.mp4", input_path="C:/in.mkv",
        )
        self.assertTrue(any("pista de subtítulos" in i["message"] for i in issues))

    def test_image_subtitles_rejected_in_mp4(self):
        issues = validate_job(
            options=default_options(subtitleTrack=1, container="mp4"),
            media=MEDIA, output_path="C:/out.mp4", input_path="C:/in.mkv",
        )
        self.assertTrue(any("imagen" in i["message"] for i in issues))


class TransitionTests(unittest.TestCase):
    def _concat(self, options, medias=None):
        medias = medias or [
            {**MEDIA, "duration": 4.0},
            {**MEDIA, "duration": 3.0},
        ]
        return build_concat_commands(
            inputs=["C:/a.mp4", "C:/b.mp4"],
            output_path="C:/out.mp4",
            options=default_options(task="concat", concatMode="reencode", **options),
            medias=medias,
        )["commands"][0]

    def test_fade_uses_xfade_and_acrossfade(self):
        args = self._concat({"concatTransition": "fade", "concatTransitionDuration": 1.0})
        graph = args[args.index("-filter_complex") + 1]
        self.assertIn("xfade=transition=fade", graph)
        self.assertIn("duration=1.000", graph)
        # 4 s del primer clip menos 1 s de fundido.
        self.assertIn("offset=3.000", graph)
        self.assertIn("acrossfade=d=1.000", graph)

    def test_no_fade_keeps_concat_filter(self):
        args = self._concat({"concatTransition": "none"})
        graph = args[args.index("-filter_complex") + 1]
        self.assertIn("concat=n=2:v=1:a=1", graph)
        self.assertNotIn("xfade", graph)

    def test_copy_mode_rejects_transition(self):
        issues = validate_concat(
            inputs=["C:/a.mp4", "C:/b.mp4"],
            options=default_options(task="concat", concatMode="copy", concatTransition="fade"),
            medias=[{**MEDIA, "duration": 4.0}, {**MEDIA, "duration": 3.0}],
            output_path="C:/out.mp4",
        )
        self.assertTrue(any("Recomponer" in i["message"] for i in issues))


@unittest.skipUnless(FFMPEG and FFPROBE and os.path.isfile(SAMPLE), "Faltan binarios o muestra")
class TransitionIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp_root = os.path.join(APP_ROOT, ".tmp")
        os.makedirs(tmp_root, exist_ok=True)
        cls.work = tempfile.mkdtemp(prefix="xfade-", dir=tmp_root)
        cls.runner = JobRunner(FFMPEG)
        cls.base = probe_file(FFPROBE, SAMPLE)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, ignore_errors=True)

    def test_crossfade_shortens_total_duration(self):
        output = os.path.join(self.work, "fundido.mp4")
        built = build_concat_commands(
            inputs=[SAMPLE, SAMPLE],
            output_path=output,
            options=default_options(task="concat", concatMode="reencode",
                                    concatTransition="fade", concatTransitionDuration=1.0),
            medias=[self.base, self.base],
        )
        result = self.runner.run_job(job_id="fade", commands=built["commands"],
                                     duration=self.base["duration"] * 2)
        self.assertTrue(result["ok"], result.get("error"))
        media = probe_file(FFPROBE, output)
        esperado = self.base["duration"] * 2 - 1.0
        self.assertLess(abs(media["duration"] - esperado), 0.6)


if __name__ == "__main__":
    unittest.main()
