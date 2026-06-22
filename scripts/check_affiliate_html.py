#!/usr/bin/env python3
"""Check generated HTML for unwrapped affiliate links."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DIRECT_RAKUTEN_HREF = re.compile(
    r"""href=(?P<quote>["']?)(?P<url>https://(?:books|search)\.rakuten\.co\.jp[^\s"'<>]*)""",
    re.I,
)
AMBIGUOUS_AFFILIATE_SLOT = re.compile(
    r"""data-affiliate-slot=(?P<quote>["']?)(?P<slot>article-(?:top|bottom)|lp-(?:hero|bottom)|home-info|shortcode-(?:affbtn|cta3|offerbox))(?P=quote)(?=[\s>])""",
    re.I,
)


def find_direct_rakuten_links(root: Path) -> list[tuple[Path, str]]:
    findings: list[tuple[Path, str]] = []
    for path in sorted(root.rglob("*.html")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in DIRECT_RAKUTEN_HREF.finditer(text):
            findings.append((path, match.group("url")))
    return findings


def find_ambiguous_affiliate_slots(root: Path) -> list[tuple[Path, str]]:
    findings: list[tuple[Path, str]] = []
    for path in sorted(root.rglob("*.html")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in AMBIGUOUS_AFFILIATE_SLOT.finditer(text):
            findings.append((path, match.group("slot")))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Check generated HTML affiliate link wrapping.")
    parser.add_argument(
        "html_root",
        nargs="?",
        default="public",
        help="Generated Hugo output directory to scan, default: public",
    )
    args = parser.parse_args()

    root = Path(args.html_root)
    if not root.is_absolute():
        root = REPO_ROOT / root
    if not root.exists():
        print(f"Generated HTML directory does not exist: {root}")
        return 1

    findings = find_direct_rakuten_links(root)
    if findings:
        print(f"Direct Rakuten links found in generated HTML ({len(findings)}):")
        for path, url in findings:
            rel = path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path
            print(f"  - {rel}: {url}")
        print("Use the Rakuten affiliate wrapper before deploying.")
        return 1

    ambiguous_slots = find_ambiguous_affiliate_slots(root)
    if ambiguous_slots:
        print(f"Ambiguous affiliate slots found in generated HTML ({len(ambiguous_slots)}):")
        for path, slot in ambiguous_slots:
            rel = path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path
            print(f"  - {rel}: {slot}")
        print("Use a button-specific affiliate_slot so GA4 can identify the clicked offer.")
        return 1

    print(f"Affiliate HTML check passed for {root}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
