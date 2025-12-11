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


def _tokenize(text: str) -> set[str]:

    # Simple tokenization for Japanese/English mixed titles
    cleaned = re.sub(r"[^0-9A-Za-z\u3040-\u30ff\u4e00-\u9fff]+", " ", text.lower())
    return {t for t in cleaned.split() if len(t) >= 2}

def find_similar_titles(posts: Iterable[Path], threshold: float = 0.7) -> Dict[str, list]:
    title_map = {}
    for post in posts:
        fm = extract_front_matter(post)
        t = fm.get("title")
        if t:
            title_map[post] = t

    similar_groups = {}
    ignore_set = set()
    
    paths = list(title_map.keys())
    for i in range(len(paths)):
        p1 = paths[i]
        t1 = title_map[p1]
        if p1 in ignore_set:
            continue
            
        tokens1 = _tokenize(t1)
        if not tokens1:
            continue
            
        group = [p1]
        for j in range(i + 1, len(paths)):
            p2 = paths[j]
            if p2 in ignore_set:
                continue
            
            t2 = title_map[p2]
            tokens2 = _tokenize(t2)
            if not tokens2:
                continue
                
            # Jaccard Similarity
            intersection = len(tokens1 & tokens2)
            union = len(tokens1 | tokens2)
            
            if union > 0 and (intersection / union) >= threshold:
                group.append(p2)
                ignore_set.add(p2)
        
        if len(group) > 1:
            similar_groups[t1] = group

    return similar_groups

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
    similar_titles = find_similar_titles(posts)

    if not dup_titles and not dup_slugs and not similar_titles:
        print("No duplicate titles, slugs, or similar content detected.")
        return 0

    has_error = False

    if dup_titles:
        print("Duplicate titles found (Exact match):", file=sys.stderr)
        for title, paths in dup_titles.items():
            print(f'  - "{title}"', file=sys.stderr)
            for path in paths:
                print(f"      {path}", file=sys.stderr)
        has_error = True

    if dup_slugs:
        print("Duplicate slugs found:", file=sys.stderr)
        for slug, paths in dup_slugs.items():
            print(f'  - "{slug}"', file=sys.stderr)
            for path in paths:
                print(f"      {path}", file=sys.stderr)
        has_error = True
        
    if similar_titles:
        print("Similar titles found (Potential duplicate content):", file=sys.stderr)
        for base_title, paths in similar_titles.items():
            print(f'  - Group around "{base_title}":', file=sys.stderr)
            for path in paths:
                # Show title for each path to see why it matched
                fm = extract_front_matter(path)
                print(f"      {path} ('{fm.get('title')}')", file=sys.stderr)
        # Warning only, or error? Let's make it an error to be safe as requested.
        has_error = True

    return 1 if has_error else 0


if __name__ == "__main__":
    sys.exit(main())
