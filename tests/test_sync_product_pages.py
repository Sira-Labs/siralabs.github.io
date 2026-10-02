"""Unit tests for scripts/sync_product_pages.py (run: python3 -m unittest discover tests)."""

import importlib.util
import sys
import unittest
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "sync_product_pages.py"
_spec = importlib.util.spec_from_file_location("sync_product_pages", _SCRIPT)
sync = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = sync  # dataclasses resolve annotations via sys.modules
_spec.loader.exec_module(sync)

PROJECT = sync.Project(repo="Demo", slug="demo")

PAGE = """<!doctype html>
<html><head>
<meta property="og:image" content="https://sira-labs.github.io/Demo/assets/social-preview.png">
</head><body>
<footer><nav><a href="https://github.com/Sira-Labs/Demo">GitHub</a></nav></footer>
</body></html>"""


class AdjustPageTest(unittest.TestCase):
    def test_adds_canonical_and_og_url(self):
        html = sync.adjust_page(PAGE, PROJECT, has_social_preview=False)
        self.assertIn('<link rel="canonical" href="https://siralabs.org/demo/">', html)
        self.assertIn(
            '<meta property="og:url" content="https://siralabs.org/demo/">', html
        )

    def test_rewrites_old_github_io_address(self):
        html = sync.adjust_page(PAGE, PROJECT, has_social_preview=False)
        self.assertNotIn("sira-labs.github.io/Demo/", html)
        self.assertIn("https://siralabs.org/demo/assets/social-preview.png", html)

    def test_is_idempotent(self):
        once = sync.adjust_page(PAGE, PROJECT, has_social_preview=False)
        twice = sync.adjust_page(once, PROJECT, has_social_preview=False)
        self.assertEqual(once, twice)
        self.assertEqual(twice.count('rel="canonical"'), 1)

    def test_adds_backlink_only_when_missing(self):
        html = sync.adjust_page(PAGE, PROJECT, has_social_preview=False)
        self.assertEqual(html.count("sira-labs-backlink"), 1)

        linked = PAGE.replace(
            "<nav>", '<nav><a href="https://siralabs.org/">Sira Labs</a>'
        )
        html = sync.adjust_page(linked, PROJECT, has_social_preview=False)
        self.assertNotIn("sira-labs-backlink", html)

    def test_links_existing_sira_mention_instead_of_adding_one(self):
        mention = PAGE.replace(
            "</nav>",
            '</nav><small>A <span class="sira">Sīra Labs</span> project</small>',
        )
        html = sync.adjust_page(mention, PROJECT, has_social_preview=False)
        self.assertIn('<a class="sira" href="/">Sīra Labs</a>', html)
        self.assertNotIn("sira-labs-backlink", html)

    def test_og_image_added_only_when_page_has_none(self):
        bare = PAGE.replace(PAGE.splitlines()[2] + "\n", "")
        html = sync.adjust_page(bare, PROJECT, has_social_preview=True)
        self.assertIn('content="https://siralabs.org/demo/social-preview.png"', html)

        html = sync.adjust_page(PAGE, PROJECT, has_social_preview=True)
        self.assertEqual(html.count('property="og:image"'), 1)

    def test_rejects_page_without_head(self):
        with self.assertRaises(sync.SyncError):
            sync.adjust_page(
                "<html><body></body></html>", PROJECT, has_social_preview=False
            )


if __name__ == "__main__":
    unittest.main()
