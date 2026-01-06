from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha1
from pathlib import Path
from typing import Any, Iterable

import re

from .parse_frontmatter import parse_markdown


@dataclass(frozen=True)
class Article:
    source_path: Path
    rel_source_path: str
    meta: dict[str, Any]
    body: str
    title: str
    slug: str
    section: str
    sort_dt: datetime
    date_dt: datetime | None
    url: str | None
    article_id: str


_RE_DATE_PREFIX = re.compile(r"^(\d{4})-(\d{2})-(\d{2})-(.+)$")


def select_latest_unposted(
    repo_root: Path,
    *,
    content_globs: Iterable[str],
    posted_ids: set[str],
) -> Article | None:
    candidates: list[Article] = []
    for path in _iter_markdown_paths(repo_root, content_globs=content_globs):
        rel = path.relative_to(repo_root).as_posix()
        parsed = parse_markdown(path.read_text(encoding="utf-8"))
        meta = parsed.meta if isinstance(parsed.meta, dict) else {}

        if _is_draft(meta):
            continue

        article_id = sha1(rel.encode("utf-8")).hexdigest()
        if article_id in posted_ids:
            continue

        dt = _parse_datetime(meta.get("date"))
        mtime_dt = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        sort_dt = (dt or mtime_dt).astimezone(timezone.utc)

        title = str(meta.get("title") or "").strip() or path.stem
        url = _coerce_str(meta.get("url"))
        section = _infer_section(rel)
        slug = _infer_slug(path, meta, url=url)

        candidates.append(
            Article(
                source_path=path,
                rel_source_path=rel,
                meta=meta,
                body=parsed.body or "",
                title=title,
                slug=slug,
                section=section,
                sort_dt=sort_dt,
                date_dt=dt.astimezone(timezone.utc) if dt else None,
                url=url,
                article_id=article_id,
            )
        )

    if not candidates:
        return None

    candidates.sort(key=lambda a: (a.sort_dt, a.rel_source_path), reverse=True)
    return candidates[0]


def _iter_markdown_paths(repo_root: Path, *, content_globs: Iterable[str]) -> list[Path]:
    seen: set[Path] = set()
    paths: list[Path] = []
    for pattern in content_globs:
        for path in repo_root.glob(pattern):
            if not path.is_file():
                continue
            if path.name.startswith("."):
                continue
            if path.name == "_index.md":
                continue
            if path.suffix.lower() not in {".md", ".markdown"}:
                continue
            if path in seen:
                continue
            seen.add(path)
            paths.append(path)
    return paths


def _is_draft(meta: dict[str, Any]) -> bool:
    value = meta.get("draft")
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return False


def _infer_section(rel_source_path: str) -> str:
    parts = rel_source_path.split("/")
    if len(parts) >= 2 and parts[0] == "content":
        return parts[1]
    if parts:
        return parts[0]
    return ""


def _infer_slug(path: Path, meta: dict[str, Any], *, url: str | None) -> str:
    slug = _coerce_str(meta.get("slug"))
    if slug:
        return slug
    if url:
        cleaned = url.strip()
        if cleaned.startswith("http://") or cleaned.startswith("https://"):
            from urllib.parse import urlparse

            cleaned = urlparse(cleaned).path
        cleaned = cleaned.strip("/")
        if cleaned:
            return cleaned.split("/")[-1]
    if path.name == "index.md":
        return path.parent.name
    stem = path.stem
    m = _RE_DATE_PREFIX.match(stem)
    if m:
        return m.group(4)
    return stem


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if isinstance(value, str):
        s = value.strip().strip('"').strip("'")
        if not s:
            return None
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


def _coerce_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return str(value).strip() or None
