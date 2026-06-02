#!/usr/bin/env python3
"""Run the Hugo article publish cycle.

Cycle:
1. Generate/update posts.
2. Apply deterministic repairs to changed posts.
3. Run site quality checks.
4. Optionally commit, push, and wait for GitHub Pages deploy.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
POSTS_ROOT = REPO_ROOT / "content" / "posts"
TMP_BUILD_DIR = ".tmp-public-check"
DEFAULT_REPAIR_ATTEMPTS = 1
DEFAULT_MAX_DESCRIPTION_CHARS = 140
DEFAULT_MIN_CHARS = 800

sys.path.insert(0, str(REPO_ROOT / "scripts"))
import normalize_tags  # noqa: E402


class CycleError(RuntimeError):
    pass


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def run(
    cmd: list[str],
    *,
    check: bool = True,
    capture: bool = False,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    print(f"\n$ {' '.join(cmd)}", flush=True)
    result = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
        env=env,
        check=False,
    )
    if capture and result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if check and result.returncode != 0:
        raise CycleError(f"Command failed ({result.returncode}): {' '.join(cmd)}")
    return result


def git_output(args: list[str]) -> str:
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
    return result.stdout.strip()


def git_status(paths: list[str] | None = None) -> str:
    args = ["status", "--short"]
    if paths:
        args.extend(["--", *paths])
    return git_output(args)


def ensure_worktree_ready(allow_dirty: bool) -> None:
    status = git_status()
    if status and not allow_dirty:
        raise CycleError(
            "Working tree is not clean. Commit/stash changes or pass --allow-dirty.\n"
            + status
        )


def changed_post_paths() -> list[Path]:
    paths: set[Path] = set()
    queries = [
        ["diff", "--name-only", "--diff-filter=ACMRTUXB", "--", "content/posts"],
        ["diff", "--cached", "--name-only", "--diff-filter=ACMRTUXB", "--", "content/posts"],
        ["ls-files", "--others", "--exclude-standard", "--", "content/posts"],
    ]
    for query in queries:
        out = git_output(query)
        for line in out.splitlines():
            path = (REPO_ROOT / line.strip()).resolve()
            if path.suffix == ".md" and path.exists():
                paths.add(path)
    return sorted(paths)


def split_front_matter(text: str) -> tuple[str, str, str] | None:
    match = re.match(r"\A(?P<delim>---|\+\+\+)\s*\n(?P<fm>.*?)\n(?P=delim)\s*\n?(?P<body>.*)\Z", text, re.S)
    if not match:
        return None
    return match.group("delim"), match.group("fm"), match.group("body")


def json_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def clean_meta_description(value: str) -> str:
    text = value.strip().strip("\"'")
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[*_`~#|]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def trim_description(value: str, max_chars: int) -> str:
    value = clean_meta_description(value)
    if len(value) <= max_chars:
        return value
    boundary = max(value.rfind(p, 0, max_chars - 3) for p in ("。", "、", "！", "？", "."))
    if boundary >= max_chars // 2:
        return value[: boundary + 1]
    return value[: max_chars - 3].rstrip() + "..."


def repair_front_matter(delim: str, fm: str, max_description_chars: int) -> tuple[str, list[str]]:
    repairs: list[str] = []

    def replace_description(match: re.Match[str]) -> str:
        key = match.group("key")
        value = match.group("value").strip()
        cleaned = trim_description(value, max_description_chars)
        if cleaned != value.strip().strip("\"'"):
            repairs.append("descriptionを整形")
        return f"{key}: {json_string(cleaned)}"

    if delim == "---":
        fm = re.sub(
            r"(?m)^(?P<key>description):\s*(?P<value>.+?)\s*$",
            replace_description,
            fm,
            count=1,
        )
    return fm, repairs


def repair_body(body: str) -> tuple[str, list[str]]:
    repairs: list[str] = []
    updated = body

    h1_fixed = re.sub(r"(?m)^#(\s+\S)", r"##\1", updated)
    if h1_fixed != updated:
        repairs.append("本文H1をH2へ変更")
        updated = h1_fixed

    guide_fixed = re.sub(
        r"(?ms)(?:^|\n)詳しい[^\n]{0,100}は\s*\n\s*\[読書ガイド\]\(/posts/?\)\s*\n\s*も参考にしてみてください。?",
        "\n",
        updated,
    )
    guide_fixed = re.sub(r"(?m)^\s*.*\[読書ガイド\]\(/posts/?\).*も参考にしてみてください。?\s*$\n?", "", guide_fixed)
    guide_fixed = re.sub(r"(?m)^\s*\[読書ガイド\]\(/posts/?\)\s*$\n?", "", guide_fixed)
    if guide_fixed != updated:
        repairs.append("モデル由来の読書ガイドリンクを削除")
        updated = guide_fixed

    orphan_fixed = re.sub(r"(?ms)詳しい[^\n]{0,100}は\s*\n\s*も参考にしてみてください。?", "", updated)
    if orphan_fixed != updated:
        repairs.append("孤立した読書ガイド文を削除")
        updated = orphan_fixed

    return updated, repairs


def repair_post(path: Path, max_description_chars: int) -> list[str]:
    repairs: list[str] = []
    raw = path.read_text(encoding="utf-8")
    parsed = split_front_matter(raw)
    if parsed:
        delim, fm, body = parsed
        fm, fm_repairs = repair_front_matter(delim, fm, max_description_chars)
        body, body_repairs = repair_body(body)
        updated = f"{delim}\n{fm}\n{delim}\n{body}"
        if updated != raw:
            path.write_text(updated, encoding="utf-8")
            repairs.extend(fm_repairs + body_repairs)

    did_tag_repair, normalized = normalize_tags.normalize_tags_for_post(path)
    if did_tag_repair:
        path.write_text(normalized, encoding="utf-8")
        repairs.append("タグを正規化")

    return repairs


def auto_repair_changed_posts(max_description_chars: int) -> None:
    posts = changed_post_paths()
    if not posts:
        print("[repair] No changed posts to repair.")
        return

    print(f"[repair] Inspecting {len(posts)} changed post(s).")
    for path in posts:
        repairs = repair_post(path, max_description_chars=max_description_chars)
        if repairs:
            print(f"[repair] {rel(path)}: {', '.join(dict.fromkeys(repairs))}")
        else:
            print(f"[repair] {rel(path)}: no deterministic repairs needed")


def generate_posts(args: argparse.Namespace, cycle_index: int) -> None:
    daily_target = min(3, max(1, args.count) * cycle_index)
    cmd = [
        sys.executable,
        "scripts/generate_post.py",
        "--count",
        str(daily_target),
        "--updates",
        str(args.updates),
        "--serp-provider",
        args.serp_provider,
        "--cse-budget",
        str(args.cse_budget),
        "--gsc-days",
        str(args.gsc_days),
        "--gsc-min-impressions",
        str(args.gsc_min_impressions),
        "--gsc-min-position",
        str(args.gsc_min_position),
    ]
    if args.external_supply_check:
        cmd.append("--external-supply-check")
    run(cmd)


def run_quality_gates(args: argparse.Namespace) -> None:
    run(
        [
            sys.executable,
            "scripts/check_generated_post_quality.py",
            "--changed",
            "--min-chars",
            str(args.min_chars),
            "--max-description-chars",
            str(args.max_description_chars),
        ]
    )
    run([sys.executable, "scripts/check_unique_posts.py"])
    run([sys.executable, "scripts/check_links.py"])
    run(["git", "diff", "--check"])
    if not args.skip_hugo:
        run(["hugo", "--minify", "--destination", TMP_BUILD_DIR, "--cleanDestinationDir"])


def run_repair_and_checks(args: argparse.Namespace) -> None:
    last_error: Exception | None = None
    for attempt in range(args.repair_attempts + 1):
        auto_repair_changed_posts(max_description_chars=args.max_description_chars)
        try:
            run_quality_gates(args)
            return
        except CycleError as exc:
            last_error = exc
            if attempt >= args.repair_attempts:
                break
            print(f"[repair] Quality gate failed; retrying deterministic repair ({attempt + 1}/{args.repair_attempts}).")
    raise CycleError(f"Quality gates still failing after repair attempts: {last_error}")


def commit_changes(args: argparse.Namespace) -> str | None:
    run(["git", "add", "-A", "content/posts"])
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=REPO_ROOT).returncode == 0:
        print("[publish] No content/posts changes to commit.")
        return None
    message = args.commit_message or "chore(site): publish automated article cycle"
    run(["git", "commit", "-m", message])
    return git_output(["rev-parse", "HEAD"])


def wait_for_deploy(repo: str, head_sha: str, timeout_seconds: int) -> str:
    deadline = time.time() + timeout_seconds
    url = f"https://api.github.com/repos/{repo}/actions/runs?branch=main&per_page=10"
    headers = {"User-Agent": "site-publish-cycle"}
    while time.time() < deadline:
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=15) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, json.JSONDecodeError) as exc:
            print(f"[deploy] Unable to read GitHub Actions yet: {exc}")
            time.sleep(10)
            continue

        for run_info in payload.get("workflow_runs", []):
            if run_info.get("head_sha") != head_sha:
                continue
            status = run_info.get("status")
            conclusion = run_info.get("conclusion")
            html_url = run_info.get("html_url", "")
            print(f"[deploy] {run_info.get('name')}: {status}/{conclusion or '-'} {html_url}")
            if status == "completed":
                if conclusion == "success":
                    return html_url
                raise CycleError(f"Deploy failed: {html_url}")
        time.sleep(10)
    raise CycleError(f"Timed out waiting for deploy for {head_sha}")


def push_and_wait(args: argparse.Namespace, head_sha: str | None) -> None:
    if not args.push:
        return
    run(["git", "push", "origin", "HEAD:main"])
    if head_sha and args.wait_deploy_seconds > 0:
        wait_for_deploy(args.github_repo, head_sha, args.wait_deploy_seconds)


def run_cycle(args: argparse.Namespace, index: int) -> None:
    print(f"\n=== Publish cycle {index}/{args.cycles} ===")
    if not args.skip_generate:
        generate_posts(args, cycle_index=index)
    else:
        print("[generate] Skipped by --skip-generate.")
    run_repair_and_checks(args)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate posts, repair common issues, and validate the Hugo site.")
    parser.add_argument("--cycles", type=int, default=1, help="How many generate/check cycles to run.")
    parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="Generated post increment per cycle. generate_post.py caps the daily target at 3.",
    )
    parser.add_argument("--updates", type=int, default=1, help="Existing post update count per cycle.")
    parser.add_argument("--external-supply-check", action="store_true", help="Use external SERP/GSC supply checks.")
    parser.add_argument("--serp-provider", choices=["auto", "brave", "cse"], default="auto")
    parser.add_argument("--cse-budget", type=int, default=80)
    parser.add_argument("--gsc-days", type=int, default=28)
    parser.add_argument("--gsc-min-impressions", type=int, default=5)
    parser.add_argument("--gsc-min-position", type=float, default=10)
    parser.add_argument("--min-chars", type=int, default=DEFAULT_MIN_CHARS)
    parser.add_argument("--max-description-chars", type=int, default=DEFAULT_MAX_DESCRIPTION_CHARS)
    parser.add_argument("--repair-attempts", type=int, default=DEFAULT_REPAIR_ATTEMPTS)
    parser.add_argument("--skip-generate", action="store_true", help="Run repair/checks without generating a post.")
    parser.add_argument("--skip-hugo", action="store_true", help="Skip Hugo build gate.")
    parser.add_argument("--allow-dirty", action="store_true", help="Allow unrelated working-tree changes.")
    parser.add_argument("--pull", action="store_true", help="git pull --rebase origin main before running.")
    parser.add_argument("--publish", action="store_true", help="Commit content/posts changes after successful checks.")
    parser.add_argument("--push", action="store_true", help="Push HEAD to origin/main after commit.")
    parser.add_argument("--commit-message", default="")
    parser.add_argument("--wait-deploy-seconds", type=int, default=0)
    parser.add_argument("--github-repo", default="pontarou0610/my-affiliate-site1")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    os.chdir(REPO_ROOT)
    if args.cycles < 1:
        raise CycleError("--cycles must be >= 1")
    if args.count < 0 or args.updates < 0:
        raise CycleError("--count and --updates must be >= 0")

    ensure_worktree_ready(args.allow_dirty)
    if args.pull:
        run(["git", "pull", "--rebase", "origin", "main"])

    for index in range(1, args.cycles + 1):
        run_cycle(args, index)

    head_sha: str | None = None
    if args.publish:
        head_sha = commit_changes(args)
    push_and_wait(args, head_sha=head_sha)
    print("\n[done] Site publish cycle completed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CycleError as exc:
        print(f"\n[error] {exc}", file=sys.stderr)
        raise SystemExit(1)
