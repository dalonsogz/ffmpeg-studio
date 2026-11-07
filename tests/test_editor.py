"""Pruebas del editor de subtítulos (lectura, edición y guardado)."""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.subtitles import (  # noqa: E402
    format_time,
    load_subtitles,
    normalize_cues,
    parse_cues,
    parse_time,
    save_subtitles,
    write_srt,
    write_vtt,
)

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SAMPLE_SRT = """1
00:00:01,000 --> 00:00:03,500
Hola, mundo.

2
00:00:04,000 --> 00:00:06,250
Segunda línea
con salto.
"""


class ParseTests(unittest.TestCase):
    def test_times(self):
        self.assertEqual(parse_time("00:00:01,500"), 1500)
        self.assertEqual(parse_time("01:02:03.250"), 3723250)
        self.assertEqual(parse_time("02:03,250"), 123250)
        self.assertIsNone(parse_time("no es una hora"))

    def test_format_time(self):
        self.assertEqual(format_time(3723250), "01:02:03,250")
        self.assertEqual(format_time(1500, "."), "00:00:01.500")

    def test_parse_srt(self):
        cues = parse_cues(SAMPLE_SRT)
        self.assertEqual(len(cues), 2)
        self.assertEqual(cues[0]["start"], 1000)
        self.assertEqual(cues[0]["end"], 3500)
        self.assertEqual(cues[0]["text"], "Hola, mundo.")
        self.assertEqual(cues[1]["text"], "Segunda línea\ncon salto.")

    def test_parse_without_indexes(self):
        text = "00:00:01,000 --> 00:00:02,000\nSin número\n"
        cues = parse_cues(text)
        self.assertEqual(len(cues), 1)

    def test_vtt(self):
        text = "WEBVTT\n\n00:00:01.000 --> 00:00:02.500\nHola\n"
        cues = parse_cues(text)
        self.assertEqual(cues[0]["start"], 1000)
        self.assertEqual(cues[0]["end"], 2500)

    def test_write_roundtrip(self):
        cues = parse_cues(SAMPLE_SRT)
        again = parse_cues(write_srt(cues))
        self.assertEqual(again, cues)

    def test_write_vtt(self):
        cues = parse_cues(SAMPLE_SRT)
        text = write_vtt(cues)
        self.assertTrue(text.startswith("WEBVTT"))
        self.assertIn("00:00:01.000 --> 00:00:03.500", text)

    def test_invalid_end_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_cues([{"start": 5000, "end": 1000, "text": "mal"}])

    def test_negative_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_cues([{"start": -1, "end": 1000, "text": "mal"}])


class FileTests(unittest.TestCase):
    def setUp(self):
        tmp_root = os.path.join(APP_ROOT, ".tmp")
        os.makedirs(tmp_root, exist_ok=True)
        self.tmp = tempfile.mkdtemp(prefix="subs-", dir=tmp_root)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_save_and_load_srt(self):
        path = os.path.join(self.tmp, "salida.srt")
        cues = [{"start": 1000, "end": 2500, "text": "Hola"}]
        result = save_subtitles(path, cues)
        self.assertTrue(result["ok"])
        self.assertEqual(result["count"], 1)
        loaded = load_subtitles(path)
        self.assertTrue(loaded["ok"])
        self.assertEqual(loaded["cues"][0]["text"], "Hola")

    def test_save_vtt(self):
        path = os.path.join(self.tmp, "salida.vtt")
        save_subtitles(path, [{"start": 0, "end": 1000, "text": "Hola"}])
        with open(path, encoding="utf-8") as handle:
            self.assertTrue(handle.read().startswith("WEBVTT"))

    def test_bom_and_crlf(self):
        path = os.path.join(self.tmp, "bom.srt")
        with open(path, "w", encoding="utf-8-sig", newline="\r\n") as handle:
            handle.write(SAMPLE_SRT)
        loaded = load_subtitles(path)
        self.assertEqual(len(loaded["cues"]), 2)

    def test_ass_is_rejected_with_help(self):
        path = os.path.join(self.tmp, "estilos.ass")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("[Script Info]\n")
        loaded = load_subtitles(path)
        self.assertFalse(loaded["ok"])
        self.assertIn("SRT", loaded["error"])


class EditorApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app as studio

        tmp_root = os.path.join(APP_ROOT, ".tmp")
        os.makedirs(tmp_root, exist_ok=True)
        cls.tmp = tempfile.mkdtemp(prefix="subs-api-", dir=tmp_root)
        cls.api = studio.Api(settings_file=os.path.join(cls.tmp, "settings.json"),
                             enable_hardware_detection=False)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_load_and_save_cycle(self):
        path = os.path.join(self.tmp, "editado.srt")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(SAMPLE_SRT)

        loaded = self.api.subtitle_load(path)
        self.assertTrue(loaded["ok"], loaded.get("error"))
        self.assertEqual(len(loaded["cues"]), 2)

        loaded["cues"].append({"start": 7000, "end": 8000, "text": "Añadido"})
        saved = self.api.subtitle_save(path, loaded["cues"])
        self.assertTrue(saved["ok"], saved.get("error"))
        self.assertEqual(saved["count"], 3)

        again = self.api.subtitle_load(path)
        self.assertEqual(again["cues"][-1]["text"], "Añadido")

    def test_invalid_cue_reports_error(self):
        path = os.path.join(self.tmp, "malo.srt")
        result = self.api.subtitle_save(path, [{"start": 900, "end": 100, "text": "x"}])
        self.assertFalse(result["ok"])
        self.assertIn("posterior", result["error"])

    def test_missing_file(self):
        result = self.api.subtitle_load(os.path.join(self.tmp, "nada.srt"))
        self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()
