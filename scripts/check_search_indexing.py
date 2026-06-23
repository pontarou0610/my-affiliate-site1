#!/usr/bin/env python3
"""Validate robots, canonical, and sitemap consistency in generated HTML."""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, urlparse


REPO_ROOT = Path(__file__).resolve().parents[1]


class SearchMetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.robots: list[str] = []
        self.canonicals: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() == "meta" and values.get("name", "").lower() == "robots":
            self.robots.append(values.get("content", ""))
        if tag.lower() == "link" and "canonical" in values.get("rel", "").lower().split():
            self.canonicals.append(values.get("href", ""))


def parse_sitemap(path: Path) -> list[str]:
    try:
        root = ET.fromstring(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Sitemap is missing: {path}") from exc
    except ET.ParseError as exc:
        raise ValueError(f"Sitemap XML is invalid: {path}") from exc
    return [
        (node.text or "").strip()
        for node in root.findall(".//{*}loc")
        if (node.text or "").strip()
    ]


def local_url(path: Path, root: Path, base_url: str) -> str:
    relative = path.relative_to(root).as_posix()
    if relative == "index.html":
        suffix = ""
    elif relative.endswith("/index.html"):
        suffix = relative[: -len("index.html")]
    else:
        suffix = relative
    return base_url.rstrip("/") + "/" + quote(suffix, safe="/:@-._~!$&'()*+,;=")


def inspect_html(path: Path) -> SearchMetaParser:
    parser = SearchMetaParser()
    parser.feed(path.read_text(encoding="utf-8", errors="ignore"))
    return parser


def check_indexing(root: Path, base_url: str) -> list[str]:
    errors: list[str] = []
    sitemap_urls = parse_sitemap(root / "sitemap.xml")
    sitemap_set = set(sitemap_urls)
    if len(sitemap_urls) != len(sitemap_set):
        errors.append("Sitemap contains duplicate URLs.")

    local_pages: dict[str, tuple[Path, SearchMetaParser]] = {}
    for path in sorted(root.rglob("*.html")):
        meta = inspect_html(path)
        if not meta.robots:
            continue
        page_url = local_url(path, root, base_url)
        local_pages[page_url] = (path, meta)

    for page_url, (path, meta) in local_pages.items():
        noindex = any("noindex" in value.lower() for value in meta.robots)
        if noindex and page_url in sitemap_set:
            errors.append(f"Noindex page appears in sitemap: {path}")
        if not noindex:
            if len(meta.canonicals) != 1:
                errors.append(
                    f"Indexable page must have exactly one canonical: {path} "
                    f"({len(meta.canonicals)} found)"
                )
            elif meta.canonicals[0] != page_url:
                errors.append(
                    f"Canonical mismatch: {path} -> {meta.canonicals[0]} "
                    f"(expected {page_url})"
                )

    for sitemap_url in sitemap_urls:
        parsed = urlparse(sitemap_url)
        if not sitemap_url.startswith(base_url.rstrip("/") + "/") and sitemap_url != base_url.rstrip("/") + "/":
            errors.append(f"Sitemap URL is outside the configured site: {sitemap_url}")
            continue
        if sitemap_url not in local_pages:
            errors.append(f"Sitemap URL has no generated HTML page: {sitemap_url}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("html_root", nargs="?", default="public")
    parser.add_argument(
        "--base-url",
        default="https://pontarou0610.github.io/my-affiliate-site1/",
    )
    args = parser.parse_args()
    root = Path(args.html_root)
    if not root.is_absolute():
        root = REPO_ROOT / root
    try:
        errors = check_indexing(root, args.base_url)
    except ValueError as exc:
        print(exc)
        return 1
    if errors:
        print(f"Search indexing check failed ({len(errors)}):")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(f"Search indexing check passed for {root}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
