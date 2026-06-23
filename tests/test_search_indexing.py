from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from check_search_indexing import check_indexing


BASE_URL = "https://example.com/site/"


def write_page(root: Path, relative: str, robots: str, canonical: str) -> None:
    path = root / relative / "index.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'<meta name="robots" content="{robots}">'
        f'<link rel="canonical" href="{canonical}">',
        encoding="utf-8",
    )


def write_sitemap(root: Path, urls: list[str]) -> None:
    entries = "".join(f"<url><loc>{url}</loc></url>" for url in urls)
    (root / "sitemap.xml").write_text(
        f'<?xml version="1.0"?><urlset>{entries}</urlset>',
        encoding="utf-8",
    )


class SearchIndexingTests(unittest.TestCase):
    def test_accepts_indexable_page_and_excluded_noindex_page(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_page(root, "guide", "index, follow", BASE_URL + "guide/")
            write_page(root, "archive", "noindex, follow", BASE_URL + "archive/")
            write_sitemap(root, [BASE_URL + "guide/"])

            errors = check_indexing(root, BASE_URL)

        self.assertEqual(errors, [])

    def test_rejects_noindex_page_in_sitemap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_page(root, "archive", "noindex, follow", BASE_URL + "archive/")
            write_sitemap(root, [BASE_URL + "archive/"])

            errors = check_indexing(root, BASE_URL)

        self.assertTrue(any("Noindex page" in error for error in errors))

    def test_rejects_canonical_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_page(root, "guide", "index, follow", BASE_URL + "wrong/")
            write_sitemap(root, [BASE_URL + "guide/"])

            errors = check_indexing(root, BASE_URL)

        self.assertTrue(any("Canonical mismatch" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
