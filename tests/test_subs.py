"""Pruebas de subtítulos: comandos, estilos, validación e integración con FFmpeg."""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.command import (  # noqa: E402
    build_subtitle_commands,
    burn_style_string,
    subtitle_filter,
    validate_subtitles,
)
from core.ffmpeg import find_ffmpeg, ffprobe_beside  # noqa: E402
from core.options import default_options  # noqa: E402
from core.probe import probe_file  # noqa: E402
from core.runner import JobRunner  # noqa: E402

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(APP_ROOT, "..", ".probe", "media", "base.mp4")
SUBS = os.path.join(APP_ROOT, "..", ".probe", "media", "subs.srt")
FFMPEG = find_ffmpeg(APP_ROOT, {})
FFPROBE = ffprobe_beside(FFMPEG) if FFMPEG else None

MEDIA = {
    "path": "C:/videos/pelicula.mkv",
    "name": "pelicula.mkv",
    "duration": 42.0,
    "video": {"width": 1920, "height": 1080, "codec": "h264"},
    "audios": [{"codec": "aac"}],
    "subtitles": [
        {"codec": "subrip", "language": "spa", "title": "Español"},
        {"codec": "hdmv_pgs_subtitle", "language": "eng", "title": None},
    ],
}


def build(overrides, extraction_path=None):
    options = default_options(task="subs", **overrides)
    return build_subtitle_commands(
        media=MEDIA, options=options, output_path="C:/out.srt", extraction_path=extraction_path,
    )


class StyleTests(unittest.TestCase):
    def test_style_mapping(self):
        style = {"font": "Verdana", "size": 30, "color": "amarillo",
                 "position": "arriba", "bold": True, "outline": True}
        text = burn_style_string(style)
        self.assertIn("FontName=Verdana", text)
        self.assertIn("FontSize=30", text)
        self.assertIn("PrimaryColour=&H0000FFFF", text)
        self.assertIn("Alignment=8", text)
        self.assertIn("Bold=-1", text)

    def test_filter_escapes_windows_path(self):
        result = subtitle_filter("D:/videos/subs con espacios.srt", {})
        self.assertTrue(result.startswith("subtitles=filename='D\\:/videos/"))
        self.assertIn("force_style='", result)


class CommandTests(unittest.TestCase):
    def test_extract_track_to_srt(self):
        args = build({"subsMode": "extract", "subtitleStream": 1, "subtitleFormat": "srt"})["commands"][0]
        self.assertEqual(args[args.index("-map") + 1], "0:s:1")
        self.assertEqual(args[args.index("-c:s") + 1], "srt")
        self.assertEqual(args[-1], "C:/out.srt")

    def test_extract_image_track_keeps_codec(self):
        args = build({"subsMode": "extract", "subtitleStream": 1, "subtitleFormat": "sup"})["commands"][0]
        self.assertEqual(args[args.index("-c:s") + 1], "copy")

    def test_mux_sets_track_metadata_and_disposition(self):
        args = build({
            "subsMode": "mux", "container": "mkv", "subtitleFile": "C:/subs.srt",
            "subtitleLanguage": "spa", "subtitleTitle": "Forzados", "subtitleDefault": True,
        })["commands"][0]
        self.assertEqual(args[args.index("-map") + 1], "0")
        self.assertIn("1:0", args)
        self.assertEqual(args[args.index("-c") + 1], "copy")
        self.assertEqual(args[args.index("-c:s") + 1], "copy")
        # Dos subtítulos previos: la nueva pista es la 2.
        self.assertIn("language=spa", args)
        self.assertIn("title=Forzados", args)
        self.assertIn("default", args)

    def test_mux_mp4_converts_to_mov_text(self):
        args = build({"subsMode": "mux", "container": "mp4", "subtitleFile": "C:/subs.srt"})["commands"][0]
        self.assertEqual(args[args.index("-c:s") + 1], "mov_text")

    def test_burn_from_file(self):
        built = build({
            "subsMode": "burn", "subtitleFile": "C:/subs.srt",
            "burnStyle": {"font": "Arial", "size": 24, "color": "blanco", "position": "abajo"},
        })
        self.assertEqual(len(built["commands"]), 1)
        args = built["commands"][0]
        self.assertIn("subtitles=filename=", args[args.index("-vf") + 1])
        self.assertEqual(args[args.index("-c:v") + 1], "libx264")
        self.assertIn("-sn", args)

    def test_burn_from_embedded_extracts_first(self):
        built = build({"subsMode": "burn", "subtitleStream": 0}, extraction_path="C:/tmp/extraido.srt")
        self.assertEqual(len(built["commands"]), 2)
        first = built["commands"][0]
        self.assertEqual(first[first.index("-map") + 1], "0:s:0")
        self.assertEqual(first[-1], "C:/tmp/extraido.srt")
        self.assertEqual(built["durations"][0], 1)
        self.assertEqual(built["durations"][1], 42.0)


class ValidationTests(unittest.TestCase):
    def test_extract_without_tracks(self):
        media = {**MEDIA, "subtitles": []}
        issues = validate_subtitles(
            media=media, options=default_options(task="subs", subsMode="extract"),
            output_path="C:/out.srt", input_path="C:/in.mkv",
        )
        self.assertTrue(any("no contiene pistas" in i["message"] for i in issues))

    def test_image_track_cannot_export_text(self):
        issues = validate_subtitles(
            media=MEDIA,
            options=default_options(task="subs", subsMode="extract", subtitleStream=1, subtitleFormat="srt"),
            output_path="C:/out.srt", input_path="C:/in.mkv",
        )
        self.assertTrue(any("PGS" in i["message"] for i in issues))

    def test_sup_requires_image_track(self):
        issues = validate_subtitles(
            media=MEDIA,
            options=default_options(task="subs", subsMode="extract", subtitleStream=0, subtitleFormat="sup"),
            output_path="C:/out.sup", input_path="C:/in.mkv",
        )
        self.assertTrue(any(".sup" in i["message"] for i in issues))

    def test_mux_requires_existing_file(self):
        issues = validate_subtitles(
            media=MEDIA,
            options=default_options(task="subs", subsMode="mux", container="mkv", subtitleFile="C:/noexiste.srt"),
            output_path="C:/out.mkv", input_path="C:/in.mkv",
        )
        self.assertTrue(any("No se encuentra" in i["message"] for i in issues))

    def test_mp4_rejects_image_subtitles_when_muxing(self):
        pgs_media = {**MEDIA, "subtitles": [{"codec": "hdmv_pgs_subtitle"}]}
        issues = validate_subtitles(
            media=pgs_media,
            options=default_options(task="subs", subsMode="mux", container="mp4", subtitleFile="C:/subs.srt"),
            output_path="C:/out.mp4", input_path="C:/in.mkv",
        )
        self.assertTrue(any("subtítulos de imagen" in i["message"] for i in issues))

    def test_burn_needs_source(self):
        media = {**MEDIA, "subtitles": []}
        issues = validate_subtitles(
            media=media, options=default_options(task="subs", subsMode="burn"),
            output_path="C:/out.mp4", input_path="C:/in.mp4",
        )
        self.assertTrue(any("archivo o una pista" in i["message"] for i in issues))


@unittest.skipUnless(FFMPEG and FFPROBE and os.path.isfile(SAMPLE) and os.path.isfile(SUBS),
                     "Faltan binarios o archivos de muestra")
class SubtitleIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp_root = os.path.join(APP_ROOT, ".tmp")
        os.makedirs(tmp_root, exist_ok=True)
        cls.work = tempfile.mkdtemp(prefix="subs-", dir=tmp_root)
        cls.runner = JobRunner(FFMPEG)
        cls.base = probe_file(FFPROBE, SAMPLE)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, ignore_errors=True)

    def test_mux_then_extract_roundtrip(self):
        muxed = os.path.join(self.work, "con_subs.mkv")
        mux = build_subtitle_commands(
            media=self.base,
            options=default_options(task="subs", subsMode="mux", container="mkv",
                                    subtitleFile=SUBS, subtitleLanguage="spa"),
            output_path=muxed,
        )
        self.assertTrue(self.runner.run_job(job_id="mux", commands=mux["commands"], duration=None)["ok"])

        media = probe_file(FFPROBE, muxed)
        self.assertEqual(len(media["subtitles"]), 1)
        self.assertEqual(media["subtitles"][0]["language"], "spa")

        extracted = os.path.join(self.work, "extraido.srt")
        extract = build_subtitle_commands(
            media=media,
            options=default_options(task="subs", subsMode="extract", subtitleFormat="srt", subtitleStream=0),
            output_path=extracted,
        )
        self.assertTrue(self.runner.run_job(job_id="extract", commands=extract["commands"], duration=None)["ok"])
        with open(extracted, encoding="utf-8") as handle:
            text = handle.read()

        with open(SUBS, encoding="utf-8-sig", errors="replace") as handle:
            expected_lines = [
                line.strip() for line in handle.read().splitlines()
                if line.strip() and "-->" not in line and not line.strip().isdigit()
            ]
        self.assertTrue(expected_lines, "El SRT de muestra no tiene texto")
        self.assertIn(expected_lines[0], text)

    def test_burn_produces_clean_video(self):
        output = os.path.join(self.work, "quemado.mp4")
        built = build_subtitle_commands(
            media=self.base,
            options=default_options(task="subs", subsMode="burn", container="mp4",
                                    subtitleFile=SUBS, videoCodec="libx264", quality=28),
            output_path=output,
        )
        self.assertTrue(self.runner.run_job(job_id="burn", commands=built["commands"],
                                            duration=self.base["duration"])["ok"])
        media = probe_file(FFPROBE, output)
        self.assertEqual(media["subtitles"], [])
        self.assertLess(abs(media["duration"] - self.base["duration"]), 0.3)


if __name__ == "__main__":
    unittest.main()
