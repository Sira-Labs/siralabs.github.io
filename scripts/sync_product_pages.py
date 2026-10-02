#!/usr/bin/env python3
"""Copy the product pages of the Sira Labs projects onto siralabs.org.

Each project keeps its product page in its own repository under ``site/`` (one static HTML
file, optionally with an ``assets/`` folder). This script copies that folder to
``<slug>/`` here, so the page is served at ``https://siralabs.org/<slug>/``, and adjusts the
copy for its new address:

- adds ``<link rel="canonical">`` and ``og:url`` for the siralabs.org address,
- rewrites links to the old ``sira-labs.github.io/<Repo>/`` address,
- adds an ``og:image`` when the page has none, using ``site/assets/social-preview.png`` or,
  failing that, ``docs/assets/social-preview.png`` copied to the same place,
- adds a link back to the organisation page when the page has none.

The project repositories stay the source of truth: edit the page there, then run this script
and commit the result. Usage::

    python3 scripts/sync_product_pages.py                    # shallow-clone each repository
    python3 scripts/sync_product_pages.py --source ../repos  # use existing clones in a folder
"""

from __future__ import annotations

import argparse
import logging
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

LOG = logging.getLogger("sync_product_pages")

SITE_ORIGIN = "https://siralabs.org"
GITHUB_ORG = "Sira-Labs"

# Where a social preview lives inside a published page folder. Pages that already reference
# assets/social-preview.png (rewritten to the new address) keep working with this path.
PREVIEW_PATH = "assets/social-preview.png"


@dataclass(frozen=True)
class Project:
    """A project whose ``site/`` folder is published under ``/<slug>/``."""

    repo: str
    slug: str

    @property
    def url(self) -> str:
        """The page's address on siralabs.org."""
        return f"{SITE_ORIGIN}/{self.slug}/"

    @property
    def old_url(self) -> str:
        """The address the repository publishes the page at itself."""
        return f"https://sira-labs.github.io/{self.repo}/"


PROJECTS = (
    Project(repo="Sahifa", slug="sahifa"),
    Project(repo="Thawr", slug="thawr"),
    Project(repo="Khandaq", slug="khandaq"),
)

BACKLINK = (
    '<p class="sira-labs-backlink" style="margin: 24px auto 0; text-align: center; '
    'font-size: 14px; opacity: 0.8"><a href="/" style="color: inherit">'
    "A Sira Labs project</a></p>\n"
)


class SyncError(RuntimeError):
    """A project's page could not be found, fetched or adjusted."""


def adjust_page(html: str, project: Project, *, preview_path: str | None) -> str:
    """Return the page HTML adjusted for its address on siralabs.org.

    ``preview_path`` is the social preview's path inside the page folder, or None when the
    page has no preview file; it is used only when the page has no ``og:image`` of its own.
    Raises SyncError when the page lacks the ``</head>`` or ``</footer>`` it needs.
    """
    if "</head>" not in html:
        raise SyncError(f"{project.repo}: page has no </head>")

    html = html.replace(project.old_url, project.url)

    # Drop any existing canonical/og:url so a re-sync never duplicates them.
    html = re.sub(r'\s*<link rel="canonical"[^>]*>', "", html)
    html = re.sub(r'\s*<meta property="og:url"[^>]*>', "", html)
    head_tags = [
        f'<link rel="canonical" href="{project.url}">',
        f'<meta property="og:url" content="{project.url}">',
    ]
    if preview_path and 'property="og:image"' not in html:
        head_tags.append(
            f'<meta property="og:image" content="{project.url}{preview_path}">'
        )
    html = html.replace("</head>", "\n".join(head_tags) + "\n</head>", 1)

    links_home = re.search(r'href="(/|https://siralabs\.org/?)"', html)
    if not links_home:
        # Prefer linking an existing "Sira Labs" mention over adding a second one.
        html, linked = re.subn(
            r'<span class="sira">([^<]*)</span>',
            r'<a class="sira" href="/">\1</a>',
            html,
            count=1,
        )
        if linked:
            return html
        if "</footer>" not in html:
            raise SyncError(f"{project.repo}: page has no </footer> for the back-link")
        html = html.replace("</footer>", BACKLINK + "</footer>", 1)
    return html


def fetch_repo(project: Project, workdir: Path) -> Path:
    """Shallow, sparse clone of the repository's ``site/`` and ``docs/assets/``."""
    dest = workdir / project.repo
    url = f"https://github.com/{GITHUB_ORG}/{project.repo}"
    commands = [
        [
            "git",
            "clone",
            "--quiet",
            "--depth",
            "1",
            "--filter=blob:none",
            "--sparse",
            url,
            str(dest),
        ],
        ["git", "-C", str(dest), "sparse-checkout", "set", "site", "docs/assets"],
    ]
    for command in commands:
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as error:
            raise SyncError(
                f"{project.repo}: {' '.join(command[:2])} failed: {error.stderr.strip()}"
            ) from error
    return dest


def build_page(project: Project, repo_dir: Path, staging: Path) -> None:
    """Build the adjusted copy of ``<repo_dir>/site/`` in the empty folder ``staging``."""
    source = repo_dir / "site"
    page = source / "index.html"
    if not page.is_file():
        raise SyncError(f"{project.repo}: {page} not found")

    # Adjust first: an invalid page fails here, before anything is copied.
    html = page.read_text(encoding="utf-8")
    site_preview = source / PREVIEW_PATH
    docs_preview = repo_dir / "docs" / "assets" / "social-preview.png"
    has_preview = site_preview.is_file() or docs_preview.is_file()
    adjusted = adjust_page(
        html, project, preview_path=PREVIEW_PATH if has_preview else None
    )

    shutil.copytree(
        source, staging, ignore=shutil.ignore_patterns("README.md"), dirs_exist_ok=True
    )
    if not site_preview.is_file() and docs_preview.is_file():
        (staging / PREVIEW_PATH).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(docs_preview, staging / PREVIEW_PATH)
    (staging / "index.html").write_text(adjusted, encoding="utf-8")


def sync_project(project: Project, repo_dir: Path, site_root: Path) -> None:
    """Replace ``<site_root>/<slug>/`` with a freshly built copy.

    The copy is built in a staging folder and swapped in only when complete, so a failure
    leaves the published folder as it was.
    """
    target = site_root / project.slug
    with tempfile.TemporaryDirectory(dir=site_root, prefix=f".{project.slug}-") as tmp:
        staging = Path(tmp) / "new"
        staging.mkdir()
        build_page(project, repo_dir, staging)

        previous = Path(tmp) / "previous"
        if target.exists():
            target.rename(previous)
        try:
            staging.rename(target)
        except OSError:
            if previous.exists():
                previous.rename(target)
            raise
    size = (target / "index.html").stat().st_size
    LOG.info("%s → /%s/ (%d bytes)", project.repo, project.slug, size)


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--source",
        type=Path,
        help="folder with existing clones named after the repositories (default: clone them)",
    )
    parser.add_argument(
        "--only",
        choices=[project.slug for project in PROJECTS],
        action="append",
        help="sync only this project (repeatable)",
    )
    return parser.parse_args(argv)


def find_clone(project: Project, source: Path) -> Path:
    """Return the clone of ``project`` in ``source``, matching the name case-insensitively."""
    for candidate in source.iterdir():
        if candidate.is_dir() and candidate.name.lower() == project.repo.lower():
            return candidate
    raise SyncError(f"{project.repo}: no clone in {source}")


def main(argv: list[str] | None = None) -> int:
    """Sync the selected product pages; return the process exit code."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args(sys.argv[1:] if argv is None else argv)
    site_root = Path(__file__).resolve().parent.parent
    projects = [p for p in PROJECTS if not args.only or p.slug in args.only]

    try:
        with tempfile.TemporaryDirectory() as tmp:
            for project in projects:
                if args.source:
                    repo_dir = find_clone(project, args.source)
                else:
                    repo_dir = fetch_repo(project, Path(tmp))
                sync_project(project, repo_dir, site_root)
    except (SyncError, OSError) as error:
        LOG.error("%s", error)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
