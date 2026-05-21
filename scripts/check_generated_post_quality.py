#!/usr/bin/env python3
"""Quality gate for generated Hugo posts.

By default this checks changed files under content/posts so legacy posts do not
block the daily generation workflow. Use --all for a full audit.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
POSTS_DIR = REPO_ROOT / "content" / "posts"


def run_git(args: list[str]) -> list[Path]:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        return []
    paths: list[Path] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line:
            paths.append(REPO_ROOT / line)
    return paths


def changed_post_paths() -> list[Path]:
    paths: set[Path] = set()
    for git_args in (
        ["diff", "--name-only", "--diff-filter=ACMRTUXB", "--", "content/posts"],
        ["diff", "--cached", "--name-only", "--diff-filter=ACMRTUXB", "--", "content/posts"],
        ["ls-files", "--others", "--exclude-standard", "--", "content/posts"],
    ):
        paths.update(run_git(git_args))
    return sorted(p for p in paths if p.suffix == ".md" and p.exists())


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = re.match(r"\A---\s*\n(?P<frontmatter>.*?)\n---\s*\n?(?P<body>.*)\Z", text, re.S)
    if not match:
        return {}, text
    frontmatter = match.group("frontmatter")
    fields: dict[str, str] = {}
    for key in ("title", "date", "lastmod", "draft", "description", "slug", "robotsNoIndex", "canonicalURL"):
        value_match = re.search(rf"^{re.escape(key)}:\s*(.+)$", frontmatter, re.M)
        if not value_match:
            continue
        value = value_match.group(1).strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        fields[key] = value.strip()
    return fields, match.group("body")


def clean_body_for_count(body: str) -> str:
    text = re.sub(r"(?s)```.*?```", " ", body)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"(?m)^#+\s+", " ", text)
    text = re.sub(r"[*_`~|>#-]+", " ", text)
    return re.sub(r"\s+", "", text)


def truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"true", "1", "yes", "on"}


def has_markdown(value: str) -> bool:
    return bool(re.search(r"(`|\*\*|__|!\[|\[[^\]]+\]\(|<[^>]+>)", value or ""))


def validate_post(path: Path, min_chars: int, max_description_chars: int) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    frontmatter, body = split_frontmatter(text)
    issues: list[str] = []

    if not frontmatter:
        issues.append("front matter がありません")
    for key in ("title", "date", "description", "slug"):
        if not frontmatter.get(key):
            issues.append(f"front matter の {key} がありません")

    if truthy(frontmatter.get("draft")):
        issues.append("draft が true です")

    description = frontmatter.get("description", "")
    if description:
        if len(description) > max_description_chars:
            issues.append(f"description が長すぎます ({len(description)} chars > {max_description_chars})")
        if has_markdown(description):
            issues.append("description に Markdown/HTML 記法が残っています")

    body_chars = len(clean_body_for_count(body))
    if body_chars < min_chars:
        issues.append(f"本文が短すぎます ({body_chars} chars < {min_chars})")

    if re.search(r"(?m)^#\s+\S", body):
        issues.append("本文に H1 見出しがあります（H2 から開始してください）")

    if re.search(r"(?ms)詳しい[^\n]{0,100}は\s*\n\s*も参考にしてみてください。?", body):
        issues.append("読書ガイドリンク削除後の孤立文が残っています")

    if re.search(r"\[読書ガイド\]\(/posts/?\)", body):
        issues.append("モデル由来の [読書ガイド](/posts/) リンクが残っています")

    related_count = len(re.findall(r"(?m)^##\s+関連記事\s*$", body))
    if related_count != 1:
        issues.append(f"関連記事セクション数が不正です ({related_count})")

    return issues


def resolve_paths(args: argparse.Namespace) -> list[Path]:
    if args.paths:
        return sorted((REPO_ROOT / p).resolve() if not Path(p).is_absolute() else Path(p) for p in args.paths)
    if args.all:
        return sorted(POSTS_DIR.glob("*.md"))
    return changed_post_paths()


def main() -> int:
    parser = argparse.ArgumentParser(description="Check generated Hugo post quality.")
    parser.add_argument("paths", nargs="*", help="Specific markdown files to check")
    parser.add_argument("--all", action="store_true", help="Check every post under content/posts")
    parser.add_argument("--changed", action="store_true", help="Check changed/new posts under content/posts")
    parser.add_argument("--min-chars", type=int, default=800, help="Minimum body character count")
    parser.add_argument("--max-description-chars", type=int, default=140, help="Maximum meta description length")
    parser.add_argument("--report-only", action="store_true", help="Print issues but exit 0")
    args = parser.parse_args()

    paths = resolve_paths(args)
    if not paths:
        print("No post files to check.")
        return 0

    failures: dict[Path, list[str]] = {}
    for path in paths:
        if path.suffix != ".md" or not path.exists():
            continue
        issues = validate_post(path, min_chars=args.min_chars, max_description_chars=args.max_description_chars)
        if issues:
            failures[path] = issues

    if failures:
        print(f"Generated post quality check failed for {len(failures)} file(s):")
        for path, issues in failures.items():
            rel = path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path
            print(f"\n{rel}")
            for issue in issues:
                print(f"  - {issue}")
        return 0 if args.report_only else 1

    print(f"Generated post quality check passed for {len(paths)} file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
