"""
Audit Hugo content for AdSense review readiness.

Outputs:
- Counts of potentially low-value pages (off-topic, very short, mojibake-like text)
- Example filenames for manual review

This script is intentionally heuristic; use results to decide which pages to unpublish/noindex.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
POSTS_DIR = REPO_ROOT / "content" / "posts"

# Broad topic keywords for this site (ebook/reading focused).
RELEVANCE_KEYWORDS = [
    "kindle",
    "kobo",
    "電子書籍",
    "電子書籍リーダー",
    "電子リーダー",
    "電子ペーパー",
    "e-ink",
    "eink",
    "epub",
    "pdf",
    "読書",
    "paperwhite",
    "scribe",
    "clara",
    "libra",
    "sage",
    "forma",
    "oasis",
    "voyage",
    "audible",
    "オーディオブック",
]


@dataclass(frozen=True)
class Post:
    path: Path
    fm: dict[str, str]
    body: str

    @property
    def title(self) -> str:
        return (self.fm.get("title") or "").strip()

    @property
    def categories_raw(self) -> str:
        return (self.fm.get("categories") or "").strip()

    @property
    def tags_raw(self) -> str:
        return (self.fm.get("tags") or "").strip()

    @property
    def char_count(self) -> int:
        return len(self.body.strip())


def parse_front_matter(md: str) -> tuple[dict[str, str], str]:
    m = re.match(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n(.*)$", md, flags=re.S)
    if not m:
        return {}, md
    fm_text = m.group(1)
    body = m.group(2)
    fm: dict[str, str] = {}
    for line in fm_text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        fm[key.strip()] = value.strip().strip('"').strip("'")
    return fm, body


def is_relevant(post: Post) -> bool:
    hay = f"{post.title}\n{post.body}".lower()
    return any(k.lower() in hay for k in RELEVANCE_KEYWORDS)


def looks_mojibake(text: str) -> bool:
    # Very common mojibake fragments when UTF-8 is mis-decoded as CP932.
    # (Use codepoints to avoid shell encoding issues.)
    fragments = ["\u7e3a", "\u7e67", "\u9aee", "\u8b5b"]  # 縺, 繧, 髮, 譛
    return any(f in text for f in fragments)


def main() -> None:
    if not POSTS_DIR.exists():
        raise SystemExit(f"posts dir not found: {POSTS_DIR}")

    posts: list[Post] = []
    for p in sorted(POSTS_DIR.glob("*.md")):
        if p.name == "_index.md":
            continue
        md = p.read_text(encoding="utf-8")
        fm, body = parse_front_matter(md)
        posts.append(Post(path=p, fm=fm, body=body))

    total = len(posts)
    published = [p for p in posts if (p.fm.get("draft") or "").strip().lower() != "true"]
    off_topic = [p for p in posts if not is_relevant(p)]
    short = [p for p in posts if p.char_count < 900]
    mojibake = [p for p in posts if looks_mojibake(p.title) or looks_mojibake(p.body)]
    non_ebook_cat = [p for p in posts if p.categories_raw and ("電子書籍" not in p.categories_raw)]
    longest = sorted(posts, key=lambda p: p.char_count, reverse=True)[:10]
    ge_900 = [p for p in posts if p.char_count >= 900]
    ge_1500 = [p for p in posts if p.char_count >= 1500]
    ge_2200 = [p for p in posts if p.char_count >= 2200]

    def show(label: str, items: list[Post], limit: int = 10) -> None:
        print(f"{label}: {len(items)}")
        for p in items[:limit]:
            print(f"  - {p.path.name} | {p.title}")

    print(f"total_posts: {total}")
    print(f"published(draft!=true): {len(published)}")
    print(f"body_len>=900: {len(ge_900)}")
    print(f"body_len>=1500: {len(ge_1500)}")
    print(f"body_len>=2200: {len(ge_2200)}")
    show("off_topic_by_keywords", off_topic)
    show("very_short_body", sorted(short, key=lambda p: p.char_count))
    show("mojibake_like_text", mojibake)
    show("non_ebook_categories", non_ebook_cat)
    show("longest_posts", longest)


if __name__ == "__main__":
    main()
