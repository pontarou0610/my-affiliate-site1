#!/usr/bin/env python3
"""
Validate that Hugo posts have unique titles and slugs.
Supports both TOML (+++) and YAML (---) front matter.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, Tuple


POSTS_ROOT = Path("content/posts")


def extract_front_matter(path: Path) -> Dict[str, str]:
    """Return a dict with at least title/slug when present."""
    data: Dict[str, str] = {}
    try:
        with path.open(encoding="utf-8") as f:
            first_line = f.readline()
            if not first_line:
                return data
            delimiter = first_line.strip()
            if delimiter not in ("---", "+++"):
                return data
            for raw in f:
                line = raw.strip()
                if line == delimiter:
                    break
                if not line or line.startswith(("#", "//")):
                    continue
                if delimiter == "+++":  # TOML
                    match = re.match(r'([A-Za-z0-9_\-]+)\s*=\s*"(.*)"\s*$', line)
                else:  # YAML
                    match = re.match(r'([A-Za-z0-9_\-]+)\s*:\s*"(.*)"\s*$', line)
                    if not match:
                        match = re.match(r"([A-Za-z0-9_\-]+)\s*:\s*([^\"#]+)\s*$", line)
                if match:
                    key = match.group(1)
                    value = match.group(2).strip()
                    data[key] = value.strip('"\'')
    except OSError:
        return data
    return data


def find_duplicates(posts: Iterable[Path]) -> Tuple[Dict[str, list], Dict[str, list]]:
    titles: Dict[str, list] = {}
    slugs: Dict[str, list] = {}

    for post in posts:
        fm = extract_front_matter(post)
        title = fm.get("title")
        slug = fm.get("slug")

        if title:
            titles.setdefault(title, []).append(post)
        if slug:
            slugs.setdefault(slug, []).append(post)

    dup_titles = {k: v for k, v in titles.items() if len(v) > 1}
    dup_slugs = {k: v for k, v in slugs.items() if len(v) > 1}
    return dup_titles, dup_slugs


def main() -> int:
    parser = argparse.ArgumentParser(description="Ensure Hugo posts have unique titles and slugs.")
    parser.add_argument(
        "--posts-dir",
        type=Path,
        default=POSTS_ROOT,
        help="Base directory to scan (default: content/posts)",
    )
    args = parser.parse_args()

    posts_dir = args.posts_dir
    if not posts_dir.exists():
        print(f"[WARN] Posts directory {posts_dir} does not exist.", file=sys.stderr)
        return 0

    posts = sorted(posts_dir.rglob("*.md"))
    dup_titles, dup_slugs = find_duplicates(posts)

    if not dup_titles and not dup_slugs:
        print("No duplicate titles or slugs detected.")
        return 0

    if dup_titles:
        print("Duplicate titles found:", file=sys.stderr)
        for title, paths in dup_titles.items():
            print(f'  - "{title}"', file=sys.stderr)
            for path in paths:
                print(f"      {path}", file=sys.stderr)

    if dup_slugs:
        print("Duplicate slugs found:", file=sys.stderr)
        for slug, paths in dup_slugs.items():
            print(f'  - "{slug}"', file=sys.stderr)
            for path in paths:
                print(f"      {path}", file=sys.stderr)

    return 1


if __name__ == "__main__":
    sys.exit(main())
