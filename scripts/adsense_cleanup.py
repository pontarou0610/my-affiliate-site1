"""
AdSense review cleanup (heuristic).

Goals:
- Remove clearly off-topic / low-value posts from the built site (set draft: true)
- Reduce "related links" blocks that point to off-topic pages
- Keep the site focused on ebook/reading intent

This script edits files under content/posts in-place.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
POSTS_DIR = REPO_ROOT / "content" / "posts"

KEEP_FILES = {
    "kindle-vs-kobo.md",
    "kindle-paperwhite-review.md",
    "kobo-clara-review.md",
    "_index.md",
}

# Treat posts shorter than this as thin content during AdSense review.
MIN_BODY_CHARS = 1500

# Keep the site niche-focused: only keep posts that include this category.
REQUIRED_CATEGORY = "電子書籍"

# Topics to exclude for AdSense safety / niche focus.
EXCLUDE_KEYWORDS = [
    "Facebook Dating",
    "Dating",
    "デーティング",
    "マッチング",
    "婚活",
    "恋活",
]


def parse_front_matter(md: str) -> tuple[str, str, str]:
    """Return (prefix, front_matter, body) for the *first* YAML front matter block."""
    m = re.match(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n(.*)$", md, flags=re.S)
    if not m:
        return "", "", md
    fm = m.group(1)
    body = m.group(2)
    return "---\n", fm.rstrip() + "\n", body


def get_fm_value(fm: str, key: str) -> str | None:
    m = re.search(rf"(?m)^{re.escape(key)}:\s*(.+)\s*$", fm)
    if not m:
        return None
    return m.group(1).strip()


def set_fm_value(fm: str, key: str, value: str) -> str:
    line = f"{key}: {value}"
    if re.search(rf"(?m)^{re.escape(key)}:\s*", fm):
        fm = re.sub(rf"(?m)^{re.escape(key)}:\s*.*$", line, fm)
        return fm
    fm = fm.rstrip() + "\n" + line + "\n"
    return fm


def strip_section_to_eof(body: str, heading_text: str) -> str:
    """Remove a '## {heading_text}' section from its heading until EOF."""
    pat = re.compile(rf"(?m)^##\s*{re.escape(heading_text)}\s*$")
    m = pat.search(body)
    if not m:
        return body
    return body[: m.start()].rstrip() + "\n"


def should_draft(filename: str, fm: str, body: str) -> tuple[bool, list[str]]:
    if filename in KEEP_FILES:
        return False, []

    reasons: list[str] = []

    categories = get_fm_value(fm, "categories") or ""
    if REQUIRED_CATEGORY not in categories:
        reasons.append("category_out_of_scope")

    if len(body.strip()) < MIN_BODY_CHARS:
        reasons.append("thin_body")

    hay = f"{get_fm_value(fm, 'title') or ''}\n{body}"
    if any(k in hay for k in EXCLUDE_KEYWORDS):
        reasons.append("excluded_topic")

    return bool(reasons), reasons


def main() -> None:
    if not POSTS_DIR.exists():
        raise SystemExit(f"posts dir not found: {POSTS_DIR}")

    changed = 0
    drafted = 0
    stripped = 0

    for path in sorted(POSTS_DIR.glob("*.md")):
        if not path.is_file():
            continue
        md = path.read_text(encoding="utf-8")
        prefix, fm, body = parse_front_matter(md)

        if not fm:
            continue

        original_body = body
        body = strip_section_to_eof(body, "関連記事")
        body = strip_section_to_eof(body, "関連リーダーガイド")
        if body != original_body:
            stripped += 1

        draft_flag, reasons = should_draft(path.name, fm, body)
        if draft_flag:
            fm2 = set_fm_value(fm, "draft", "true")
            # Also set noindex/sitemap-disable for safety if the page is accidentally published later.
            fm2 = set_fm_value(fm2, "robotsNoIndex", "true")
            if not re.search(r"(?m)^sitemap:\s*$", fm2):
                fm2 = fm2.rstrip() + "\n" + "sitemap:\n  disable: true\n"
            fm = fm2
            drafted += 1

        new_md = f"{prefix}{fm}---\n{body.lstrip()}"
        if new_md != md:
            path.write_text(new_md, encoding="utf-8")
            changed += 1

    print(f"files_changed: {changed}")
    print(f"files_drafted: {drafted}")
    print(f"files_stripped_related_sections: {stripped}")


if __name__ == "__main__":
    main()
