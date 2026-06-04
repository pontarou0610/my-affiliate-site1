#!/usr/bin/env python3
"""Check changed commercial content for risky price/benefit claims."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RISKY_PATTERNS = [
    re.compile(pattern)
    for pattern in (
        r"損せず",
        r"損しない",
        r"最安",
        r"失敗しません",
        r"必ず(?:安く|得)",
        r"実質価格が(?:大きく)?下が",
    )
]


def resolve_path(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else REPO_ROOT / path


def check_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    issues: list[str] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for pattern in RISKY_PATTERNS:
            if pattern.search(line):
                issues.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {pattern.pattern}: {line.strip()}")
                break
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Check commercial claim wording in changed content.")
    parser.add_argument("paths", nargs="*", help="Markdown or template files to check")
    parser.add_argument("--report-only", action="store_true", help="Report issues but exit 0")
    args = parser.parse_args()

    paths = [resolve_path(p) for p in args.paths]
    paths = [p for p in paths if p.exists() and p.suffix in {".md", ".html"}]
    if not paths:
        print("No commercial claim files to check.")
        return 0

    issues: list[str] = []
    for path in paths:
        issues.extend(check_file(path))

    if issues:
        print(f"Commercial claim check found {len(issues)} issue(s):")
        for issue in issues:
            print(f"  - {issue}")
        return 0 if args.report_only else 1

    print(f"Commercial claim check passed for {len(paths)} file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
