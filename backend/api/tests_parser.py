import os
from django.test import SimpleTestCase
from .infrastructure.magnet_parser import MagnetParser

class MagnetParserTests(SimpleTestCase):
    def test_parse_veerabhadrudu_page(self):
        # Path to the saved page content
        saved_page_path = '/Users/rahulbg/.gemini/antigravity-ide/brain/ead2a710-4dcc-4666-8a32-38ecbc09e1de/.system_generated/steps/151/content.md'
        
        # Read the file
        if not os.path.exists(saved_page_path):
            self.skipTest("Saved HTML content file is missing.")
            
        with open(saved_page_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        # Find index where HTML starts (line starts with '<!DOCTYPE html>' or similar)
        html_start_idx = 0
        for i, line in enumerate(lines):
            if '<!DOCTYPE html>' in line or '<html' in line:
                html_start_idx = i
                break
                
        html_content = "".join(lines[html_start_idx:])
        
        # Parse content
        output = MagnetParser.parse_page(url="https://test.movierulz.com", html_content=html_content)
        
        # Verify page title
        self.assertEqual(output.page_title, "Veerabhadrudu (2026) DVDScr Telugu Full Movie")
        
        # Verify list of magnet links
        self.assertTrue(len(output.magnets) > 0)
        
        # Let's inspect the first magnet link
        first_magnet = output.magnets[0]
        self.assertTrue(first_magnet.magnet_link.startswith("magnet:?xt=urn:btih:1a907709efe79c39cd778ca2c07f544b0028456d"))
        self.assertEqual(first_magnet.size, "5.4GB")
        self.assertEqual(first_magnet.resolution, "1080p")
        self.assertEqual(first_magnet.quality, "DVDScr")
        self.assertEqual(first_magnet.codec, "x264")
        self.assertIn("Telugu", first_magnet.languages)
        self.assertEqual(first_magnet.title, "Veerabhadrudu (2026) [1080P] [DVDScr] [5.4GB] (Telugu)")
        
        # Inspect second magnet link (2.8GB)
        second_magnet = output.magnets[1]
        self.assertEqual(second_magnet.size, "2.8GB")
        self.assertEqual(second_magnet.resolution, "1080p")
        self.assertEqual(second_magnet.title, "Veerabhadrudu (2026) [1080P] [DVDScr] [2.8GB] (Telugu)")
        
        # Inspect third magnet link (1.5GB 720p)
        third_magnet = output.magnets[2]
        self.assertEqual(third_magnet.size, "1.5GB")
        self.assertEqual(third_magnet.resolution, "720p")
        self.assertEqual(third_magnet.title, "Veerabhadrudu (2026) [720P] [DVDScr] [1.5GB] (Telugu)")
