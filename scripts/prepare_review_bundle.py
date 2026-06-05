#!/usr/bin/env python3
"""Prepare review artifacts for generated article candidates."""

from __future__ import annotations

import argparse
import difflib
import json
import shutil
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / ".review-output"


def run_git(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout


def changed_paths() -> list[Path]:
    tracked = run_git(["diff", "--name-only", "--diff-filter=ACMRTUXB", "--", "content", "data"])
    untracked = run_git(["ls-files", "--others", "--exclude-standard", "--", "content", "data"])
    paths: set[Path] = set()
    for out in (tracked, untracked):
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            path = (REPO_ROOT / line).resolve()
            if path.exists():
                paths.add(path)
    return sorted(paths)


def rel(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT).as_posix()


def copy_changed_files(paths: list[Path], output_dir: Path) -> None:
    files_dir = output_dir / "files"
    for path in paths:
        target = files_dir / rel(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def write_summary(paths: list[Path], output_dir: Path) -> None:
    posts = [path for path in paths if rel(path).startswith("content/posts/") and path.suffix == ".md"]
    updates = [path for path in paths if path not in posts]

    lines = [
        "# Daily Article Review",
        "",
        "Generated or updated article candidates are not committed or deployed automatically.",
        "Review the files and patch in this artifact, then commit approved changes manually.",
        "",
        f"- Changed post candidates: {len(posts)}",
        f"- Other changed files: {len(updates)}",
        "",
    ]
    if posts:
        lines.append("## Post Candidates")
        lines.extend(f"- `{rel(path)}`" for path in posts)
        lines.append("")
    if updates:
        lines.append("## Other Changes")
        lines.extend(f"- `{rel(path)}`" for path in updates)
        lines.append("")
    if not paths:
        lines.append("No generated article candidates were produced in this run.")
        lines.append("")
    supply_report = REPO_ROOT / "data" / "supply_gap_report.json"
    if supply_report.exists():
        lines.extend(summarize_supply_report(supply_report))
    lines.extend(
        [
            "## Review Checklist",
            "",
            "- Search intent is clear and not already covered by an existing stronger article.",
            "- Claims, dates, prices, campaigns, and service conditions are not over-stated.",
            "- Affiliate links use sponsored/nofollow handling and the CTA density is reasonable.",
            "- The article has exactly one related-articles section and useful internal links.",
            "- Approve only candidates that improve the site's revenue or authority.",
            "",
        ]
    )
    (output_dir / "review-summary.md").write_text("\n".join(lines), encoding="utf-8")


def summarize_supply_report(path: Path) -> list[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    meta = data.get("meta") if isinstance(data, dict) else {}
    rows = data.get("audit_rows") if isinstance(data, dict) else []
    lines = [
        "## Supply Audit",
        "",
    ]
    if isinstance(meta, dict):
        source = meta.get("source") or "-"
        provider = meta.get("serp_provider") or "-"
        fallback = meta.get("fallback_reason") or "-"
        used = meta.get("serp_used_calls", 0)
        lines.append(f"- Source: `{source}`")
        lines.append(f"- SERP provider: `{provider}`")
        lines.append(f"- SERP used calls: `{used}`")
        lines.append(f"- Fallback reason: `{fallback}`")
        lines.append("")
    if isinstance(rows, list) and rows:
        lines.append("### Top Audit Rows")
        for row in rows[:10]:
            if not isinstance(row, dict):
                continue
            query = row.get("query") or row.get("topic") or "-"
            page = row.get("page") or row.get("url") or "-"
            score = row.get("opportunity_score") or row.get("score") or "-"
            position = row.get("position") or row.get("avg_position") or "-"
            impressions = row.get("impressions") or "-"
            lines.append(
                f"- `{query}` | page: `{page}` | score: `{score}` | position: `{position}` | impressions: `{impressions}`"
            )
        lines.append("")
    return lines


def untracked_patch(paths: list[Path]) -> str:
    chunks: list[str] = []
    for path in paths:
        rel_path = rel(path)
        if run_git(["ls-files", "--error-unmatch", rel_path]):
            continue
        try:
            new_lines = path.read_text(encoding="utf-8", errors="ignore").splitlines(keepends=True)
        except OSError:
            continue
        chunks.extend(
            difflib.unified_diff(
                [],
                new_lines,
                fromfile="/dev/null",
                tofile=rel_path,
                lineterm="\n",
            )
        )
    return "".join(chunks)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare review artifact files for daily article generation.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = REPO_ROOT / output_dir
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    paths = changed_paths()
    patch = run_git(["diff", "--", "content", "data"])
    patch += untracked_patch(paths)
    (output_dir / "generated-candidates.patch").write_text(patch, encoding="utf-8")
    (output_dir / "changed-files.txt").write_text(
        "\n".join(rel(path) for path in paths) + ("\n" if paths else ""),
        encoding="utf-8",
    )
    copy_changed_files(paths, output_dir)
    write_summary(paths, output_dir)

    print(f"Prepared review bundle at {output_dir}")
    print(f"Changed files: {len(paths)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
