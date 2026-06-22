from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from check_affiliate_html import (
    find_ambiguous_affiliate_slots,
    find_direct_rakuten_links,
)


class AffiliateHtmlTests(unittest.TestCase):
    def test_detects_ambiguous_slot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.html"
            path.write_text(
                '<a data-affiliate="amazon" data-affiliate-slot="lp-hero">Buy</a>',
                encoding="utf-8",
            )

            findings = find_ambiguous_affiliate_slots(Path(directory))

        self.assertEqual(findings[0][1], "lp-hero")

    def test_accepts_button_specific_slot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.html"
            path.write_text(
                '<a data-affiliate="amazon" data-affiliate-slot="lp-hero-unlimited">Buy</a>',
                encoding="utf-8",
            )

            findings = find_ambiguous_affiliate_slots(Path(directory))

        self.assertEqual(findings, [])

    def test_detects_unquoted_minified_slot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.html"
            path.write_text(
                "<a data-affiliate=amazon data-affiliate-slot=shortcode-affbtn>Buy</a>",
                encoding="utf-8",
            )

            findings = find_ambiguous_affiliate_slots(Path(directory))

        self.assertEqual(findings[0][1], "shortcode-affbtn")

    def test_detects_direct_rakuten_link(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.html"
            path.write_text(
                '<a href="https://books.rakuten.co.jp/e-book/">Rakuten</a>',
                encoding="utf-8",
            )

            findings = find_direct_rakuten_links(Path(directory))

        self.assertEqual(len(findings), 1)


if __name__ == "__main__":
    unittest.main()
