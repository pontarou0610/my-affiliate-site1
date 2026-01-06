from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from html.parser import HTMLParser

from .config import HugoConfig
from .select_article import Article


@dataclass(frozen=True)
class CanonicalUrlResult:
    url: str
    source: str  # "html" | "fallback"
    html_path: Path | None
    guessed_url_path: str


def get_canonical_url(
    article: Article,
    *,
    public_dir: Path,
    hugo_config: HugoConfig,
) -> CanonicalUrlResult:
    guessed_path = guess_url_path(article, hugo_config=hugo_config)
    guessed_path = _strip_base_path_prefix(guessed_path, base_url=hugo_config.base_url)
    html_candidates = _candidate_html_paths(public_dir, guessed_url_path=guessed_path)

    for html_path in html_candidates:
        canonical = _extract_canonical_from_html(html_path)
        if canonical:
            return CanonicalUrlResult(url=canonical, source="html", html_path=html_path, guessed_url_path=guessed_path)

    # fallback search by slug
    for html_path in _search_html_by_slug(public_dir, slug=article.slug):
        canonical = _extract_canonical_from_html(html_path)
        if canonical:
            return CanonicalUrlResult(url=canonical, source="html", html_path=html_path, guessed_url_path=guessed_path)

    # fallback URL: baseURL + guessed path
    url = _join_base_url(hugo_config.base_url, guessed_path)
    return CanonicalUrlResult(url=url, source="fallback", html_path=None, guessed_url_path=guessed_path)


def guess_url_path(article: Article, *, hugo_config: HugoConfig) -> str:
    url = (article.url or "").strip()
    if url:
        if url.startswith("http://") or url.startswith("https://"):
            return urlparse(url).path or "/"
        return url if url.startswith("/") else f"/{url}"

    pattern = hugo_config.permalinks.get(article.section)
    if pattern:
        dt = article.date_dt or article.sort_dt
        year = f"{dt.year:04d}"
        month = f"{dt.month:02d}"
        day = f"{dt.day:02d}"
        filename = article.source_path.stem
        slug = article.slug

        path = str(pattern)
        if not path.startswith("/"):
            path = f"/{path}"
        path = (
            path.replace(":year", year)
            .replace(":month", month)
            .replace(":day", day)
            .replace(":slug", slug)
            .replace(":filename", filename)
        )
        return path

    section = article.section.strip("/")
    slug = article.slug.strip("/")
    if section and slug:
        return f"/{section}/{slug}/"
    if slug:
        return f"/{slug}/"
    return "/"


def _candidate_html_paths(public_dir: Path, *, guessed_url_path: str) -> list[Path]:
    rel = guessed_url_path.lstrip("/")
    if rel == "":
        return [public_dir / "index.html"]

    rel = rel.rstrip("/")
    candidates: list[Path] = []

    if rel.endswith(".html"):
        candidates.append(public_dir / rel)
        return candidates

    candidates.append(public_dir / rel / "index.html")
    candidates.append(public_dir / f"{rel}.html")
    return candidates


def _search_html_by_slug(public_dir: Path, *, slug: str) -> Iterable[Path]:
    if not slug:
        return []
    slug_lower = slug.lower()
    matches: list[Path] = []
    for path in public_dir.rglob("*.html"):
        p = path.as_posix().lower()
        if slug_lower in p:
            matches.append(path)
            if len(matches) >= 50:
                break
    return matches


def _strip_base_path_prefix(url_path: str, *, base_url: str) -> str:
    url_path = url_path if url_path.startswith("/") else f"/{url_path}"
    if not base_url:
        return url_path
    prefix = urlparse(base_url).path or "/"
    if not prefix.startswith("/"):
        prefix = f"/{prefix}"
    if not prefix.endswith("/"):
        prefix += "/"
    if prefix == "/":
        return url_path
    if url_path.startswith(prefix):
        stripped = url_path[len(prefix) :].lstrip("/")
        return f"/{stripped}" if stripped else "/"
    return url_path


def _join_base_url(base_url: str, url_path: str) -> str:
    base = (base_url or "").strip()
    if not base:
        return url_path
    if not base.endswith("/"):
        base += "/"
    return base.rstrip("/") + "/" + url_path.lstrip("/")


class _CanonicalLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.canonical: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.canonical is not None:
            return
        if tag.lower() != "link":
            return
        attr_map = {k.lower(): (v or "") for k, v in attrs}
        rel = attr_map.get("rel", "").lower()
        if "canonical" not in {part.strip() for part in rel.split()}:
            return
        href = attr_map.get("href", "").strip()
        if href:
            self.canonical = href


def _extract_canonical_from_html(html_path: Path) -> str | None:
    if not html_path.exists() or not html_path.is_file():
        return None
    try:
        content = html_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    parser = _CanonicalLinkParser()
    try:
        parser.feed(content)
    except Exception:
        return None
    return parser.canonical

