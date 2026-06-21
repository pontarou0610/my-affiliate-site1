#!/usr/bin/env python3
"""Report indexed posts that still contain an expired campaign deadline."""

from __future__ import annotations

import argparse
import datetime as dt
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
POSTS_DIR = REPO_ROOT / "content" / "posts"
FRONTMATTER_RE = re.compile(r"\A---\s*\n(?P<fm>.*?)\n---\s*\n?(?P<body>.*)\Z", re.S)
JP_DEADLINE_RE = re.compile(r"(?P<month>\d{1,2})月(?P<day>\d{1,2})日(?:\s*まで|まで|迄)")
SLASH_DEADLINE_RE = re.compile(r"(?P<month>\d{1,2})/(?P<day>\d{1,2})(?:\s*まで|まで)")


def frontmatter_value(frontmatter: str, key: str) -> str:
    match = re.search(rf"^{re.escape(key)}:\s*(.+)$", frontmatter, re.M)
    return match.group(1).strip().strip("\"'") if match else ""


def truthy(value: str) -> bool:
    return value.lower() in {"true", "1", "yes", "on"}


def parse_post_date(frontmatter: str) -> dt.date | None:
    raw = frontmatter_value(frontmatter, "date")[:10]
    try:
        return dt.date.fromisoformat(raw)
    except ValueError:
        return None


def inferred_deadlines(text: str, published: dt.date | None) -> set[dt.date]:
    if not published:
        return set()
    deadlines: set[dt.date] = set()
    for pattern in (JP_DEADLINE_RE, SLASH_DEADLINE_RE):
        for match in pattern.finditer(text):
            try:
                deadlines.add(
                    dt.date(
                        published.year,
                        int(match.group("month")),
                        int(match.group("day")),
                    )
                )
            except ValueError:
                continue
    if "明日まで" in text:
        deadlines.add(published + dt.timedelta(days=1))
    return deadlines


def audit(path: Path, today: dt.date) -> list[dt.date]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    match = FRONTMATTER_RE.match(text)
    if not match:
        return []
    frontmatter = match.group("fm")
    if truthy(frontmatter_value(frontmatter, "robotsNoIndex")):
        return []
    published = parse_post_date(frontmatter)
    deadlines = inferred_deadlines(text, published)
    return sorted(deadline for deadline in deadlines if deadline < today)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--today", help="Override current date (YYYY-MM-DD)")
    parser.add_argument("--report-only", action="store_true", help="Always exit 0")
    args = parser.parse_args()

    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    findings: list[tuple[Path, list[dt.date]]] = []
    for path in sorted(POSTS_DIR.glob("*.md")):
        expired = audit(path, today)
        if expired:
            findings.append((path, expired))

    if not findings:
        print(f"Expired campaign check passed for {today.isoformat()}.")
        return 0

    print(f"Expired campaign candidates: {len(findings)} (as of {today.isoformat()})")
    for path, deadlines in findings:
        rel = path.relative_to(REPO_ROOT)
        dates = ", ".join(deadline.isoformat() for deadline in deadlines)
        print(f"- {rel}: {dates}")
    return 0 if args.report_only else 1


if __name__ == "__main__":
    raise SystemExit(main())
