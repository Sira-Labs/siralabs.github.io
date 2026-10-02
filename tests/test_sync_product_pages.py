"""Unit tests for scripts/sync_product_pages.py (run: python3 -m unittest discover tests)."""

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "sync_product_pages.py"
_spec = importlib.util.spec_from_file_location("sync_product_pages", _SCRIPT)
sync = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = sync  # dataclasses resolve annotations via sys.modules
_spec.loader.exec_module(sync)

PROJECT = sync.Project(repo="Demo", slug="demo")
PREVIEW = sync.PREVIEW_PATH

PAGE = """<!doctype html>
<html><head>
<meta property="og:image" content="https://sira-labs.github.io/Demo/assets/social-preview.png">
</head><body>
<footer><nav><a href="https://github.com/Sira-Labs/Demo">GitHub</a></nav></footer>
</body></html>"""

# The same page without its own og:image.
BARE_PAGE = PAGE.replace(PAGE.splitlines()[2] + "\n", "")


class AdjustPageTest(unittest.TestCase):
    """adjust_page() rewrites a product page for its address on siralabs.org."""

    def test_adds_canonical_and_og_url(self):
        """The page gets a canonical URL and og:url on siralabs.org."""
        html = sync.adjust_page(PAGE, PROJECT, preview_path=None)
        self.assertIn('<link rel="canonical" href="https://siralabs.org/demo/">', html)
        self.assertIn(
            '<meta property="og:url" content="https://siralabs.org/demo/">', html
        )

    def test_rewrites_old_github_io_address(self):
        """Links to sira-labs.github.io/<Repo>/ point to the new address."""
        html = sync.adjust_page(PAGE, PROJECT, preview_path=None)
        self.assertNotIn("sira-labs.github.io/Demo/", html)
        self.assertIn("https://siralabs.org/demo/assets/social-preview.png", html)

    def test_is_idempotent(self):
        """Adjusting an adjusted page changes nothing."""
        once = sync.adjust_page(PAGE, PROJECT, preview_path=PREVIEW)
        twice = sync.adjust_page(once, PROJECT, preview_path=PREVIEW)
        self.assertEqual(once, twice)
        self.assertEqual(twice.count('rel="canonical"'), 1)

    def test_adds_backlink_only_when_missing(self):
        """A back-link is added only to pages that do not link home."""
        html = sync.adjust_page(PAGE, PROJECT, preview_path=None)
        self.assertEqual(html.count("sira-labs-backlink"), 1)

        linked = PAGE.replace(
            "<nav>", '<nav><a href="https://siralabs.org/">Sira Labs</a>'
        )
        html = sync.adjust_page(linked, PROJECT, preview_path=None)
        self.assertNotIn("sira-labs-backlink", html)

    def test_links_existing_sira_mention_instead_of_adding_one(self):
        """An unlinked "Sira Labs" mention becomes the back-link."""
        mention = PAGE.replace(
            "</nav>",
            '</nav><small>A <span class="sira">Sīra Labs</span> project</small>',
        )
        html = sync.adjust_page(mention, PROJECT, preview_path=None)
        self.assertIn('<a class="sira" href="/">Sīra Labs</a>', html)
        self.assertNotIn("sira-labs-backlink", html)

    def test_og_image_added_only_when_page_has_none(self):
        """og:image comes from the preview path unless the page has its own."""
        html = sync.adjust_page(BARE_PAGE, PROJECT, preview_path=PREVIEW)
        self.assertIn(f'content="https://siralabs.org/demo/{PREVIEW}"', html)

        html = sync.adjust_page(BARE_PAGE, PROJECT, preview_path=None)
        self.assertNotIn('property="og:image"', html)

        html = sync.adjust_page(PAGE, PROJECT, preview_path=PREVIEW)
        self.assertEqual(html.count('property="og:image"'), 1)

    def test_rejects_page_without_head(self):
        """A page without </head> is refused."""
        with self.assertRaises(sync.SyncError):
            sync.adjust_page("<html><body></body></html>", PROJECT, preview_path=None)


class SyncProjectTest(unittest.TestCase):
    """sync_project() publishes a page folder safely."""

    def setUp(self):
        """Create a fake repository clone and an empty site root."""
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.repo = root / "Demo"
        self.site = root / "site-root"
        (self.repo / "site").mkdir(parents=True)
        self.site.mkdir()

    def tearDown(self):
        """Remove the temporary folders."""
        self._tmp.cleanup()

    def _write_page(self, html):
        """Write the fake repository's site/index.html."""
        (self.repo / "site" / "index.html").write_text(html, encoding="utf-8")

    def _write_preview(self, relative):
        """Write a stand-in PNG at ``relative`` inside the fake repository."""
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\x89PNG")

    def test_invalid_page_keeps_published_copy(self):
        """A page that fails validation leaves the published folder untouched."""
        published = self.site / "demo"
        published.mkdir()
        (published / "index.html").write_text("published", encoding="utf-8")
        self._write_page("<html><body>no head</body></html>")

        with self.assertRaises(sync.SyncError):
            sync.sync_project(PROJECT, self.repo, self.site)
        self.assertEqual(
            (published / "index.html").read_text(encoding="utf-8"), "published"
        )
        self.assertEqual([p.name for p in self.site.iterdir()], ["demo"])

    def test_replaces_published_copy(self):
        """A valid page replaces the published folder, stale files included."""
        published = self.site / "demo"
        published.mkdir()
        (published / "stale.txt").write_text("old", encoding="utf-8")
        self._write_page(BARE_PAGE)

        sync.sync_project(PROJECT, self.repo, self.site)
        self.assertFalse((published / "stale.txt").exists())
        self.assertIn("canonical", (published / "index.html").read_text("utf-8"))
        self.assertEqual([p.name for p in self.site.iterdir()], ["demo"])

    def test_docs_preview_is_copied_where_og_image_points(self):
        """A docs/assets preview lands at the path the og:image names."""
        self._write_page(PAGE)
        self._write_preview("docs/assets/social-preview.png")

        sync.sync_project(PROJECT, self.repo, self.site)
        self.assertTrue((self.site / "demo" / PREVIEW).is_file())
        html = (self.site / "demo" / "index.html").read_text("utf-8")
        self.assertIn(f"https://siralabs.org/demo/{PREVIEW}", html)

    def test_site_preview_used_for_missing_og_image(self):
        """A preview already in site/assets gives a page without og:image one."""
        self._write_page(BARE_PAGE)
        self._write_preview(f"site/{PREVIEW}")

        sync.sync_project(PROJECT, self.repo, self.site)
        html = (self.site / "demo" / "index.html").read_text("utf-8")
        self.assertIn(f'content="https://siralabs.org/demo/{PREVIEW}"', html)


if __name__ == "__main__":
    unittest.main()
