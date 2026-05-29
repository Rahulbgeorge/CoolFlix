from django.test import SimpleTestCase
from .infrastructure.cleaner import FileNameCleaner

class FileNameCleanerTests(SimpleTestCase):
    def test_fallout_series(self):
        filename = "Fallout.S01.COMPLETE.2160p.AMZN.WEB-DL.DV.P5.ENG.LATINO.HINDI.TAMIL.TELUGU.DDP5.1.Atmos.H265.MP4-BEN.THE.MEN"
        filepath = f"/source/path/{filename}"
        output = FileNameCleaner.clean(filepath)
        
        self.assertEqual(output.cleaned_name, "Fallout")
        self.assertIsNone(output.year)
        self.assertEqual(output.season, "S01")
        self.assertTrue(output.is_series)
        self.assertEqual(output.resolution, "2160p")
        self.assertEqual(output.codec, "h265")
        self.assertEqual(output.quality, "WEB-DL")
        self.assertIn("English", output.languages)
        self.assertIn("Latino", output.languages)
        self.assertIn("Hindi", output.languages)
        self.assertIn("Tamil", output.languages)
        self.assertIn("Telugu", output.languages)

    def test_padayappa_movie(self):
        filename = "Padayappa HD Subtitles.mp4"
        filepath = f"/source/path/{filename}"
        output = FileNameCleaner.clean(filepath)
        
        self.assertEqual(output.cleaned_name, "Padayappa")
        self.assertIsNone(output.year)
        self.assertEqual(output.resolution, "720p")  # HD resolves to 720p
        self.assertTrue(output.subtitles)

    def test_scream_movie(self):
        filename = "Scream 7 (2026) English HQ HDRip - 1080p - x264 - (DD+5.1 - 384Kbps - AAC) - 2GB - ESub.mkv"
        filepath = f"/source/path/{filename}"
        output = FileNameCleaner.clean(filepath)
        
        self.assertEqual(output.cleaned_name, "Scream 7")
        self.assertEqual(output.year, 2026)
        self.assertEqual(output.resolution, "1080p")
        self.assertEqual(output.codec, "x264")
        self.assertEqual(output.quality, "HDRip")  # HDRip matches
        self.assertEqual(output.size, "2GB")
        self.assertTrue(output.subtitles)
        self.assertIn("English", output.languages)

    def test_the_housemaid_movie(self):
        filename = "The Housemaid (2025) English HQ HDRip - 1080p - x264 - (DD+5.1 - 640Kbps & AAC 2.0) - 2.8GB - ESub.mkv"
        filepath = f"/source/path/{filename}"
        output = FileNameCleaner.clean(filepath)
        
        self.assertEqual(output.cleaned_name, "The Housemaid")
        self.assertEqual(output.year, 2025)
        self.assertEqual(output.resolution, "1080p")
        self.assertEqual(output.codec, "x264")
        self.assertEqual(output.quality, "HDRip")
        self.assertEqual(output.size, "2.8GB")
        self.assertTrue(output.subtitles)
        self.assertIn("English", output.languages)

    def test_vikram_movie(self):
        filename = "Vikram  (2022) 1080p HDRip [Dual Audio] [Hindi + Tamil] x264 ESubs 3.2GB - QRips.mkv"
        filepath = f"/source/path/{filename}"
        output = FileNameCleaner.clean(filepath)
        
        self.assertEqual(output.cleaned_name, "Vikram")
        self.assertEqual(output.year, 2022)
        self.assertEqual(output.resolution, "1080p")
        self.assertEqual(output.codec, "x264")
        self.assertEqual(output.quality, "HDRip")
        self.assertEqual(output.size, "3.2GB")
        self.assertTrue(output.subtitles)
        self.assertEqual(set(output.languages), {"Hindi", "Tamil"})
