from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any

from .build_site import build_site
from .compose_tweet import compose_tweet
from .config import AutopostConfig, load_hugo_config
from .extract_summary import extract_summary
from .get_canonical_url import get_canonical_url
from .select_article import select_latest_unposted


REQUIRED_X_SECRETS = (
    "X_API_KEY",
    "X_API_KEY_SECRET",
    "X_ACCESS_TOKEN",
    "X_ACCESS_TOKEN_SECRET",
)


def main(argv: list[str]) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    cfg = AutopostConfig.from_env()
    hugo_cfg = load_hugo_config(repo_root)

    dry_run = _env_truthy("DRY_RUN", default=False)
    force_post = _env_truthy("FORCE_POST", default=False)

    state_path = repo_root / cfg.state_path
    state = _load_state(state_path)
    posted_ids = set((state.get("posted") or {}).keys())

    article = select_latest_unposted(repo_root, content_globs=cfg.content_globs, posted_ids=posted_ids)
    if article is None:
        print("No eligible unposted articles found. (no-op)")
        return 0

    print(f"Selected: {article.rel_source_path}")
    print(f"Title: {article.title}")
    print(f"Sort date (UTC): {article.sort_dt.isoformat()}")

    summary = extract_summary(
        article.body,
        target_min_chars=cfg.summary_target_min_chars,
        target_max_chars=cfg.summary_target_max_chars,
    ).strip()
    if not summary:
        summary = article.title.strip()

    public_dir = (repo_root / cfg.output_dir).resolve()
    canonical_url = None
    canonical_source = None
    canonical_html = None

    build_failed = False
    try:
        build_site(
            repo_root,
            hugo_binary=cfg.hugo_binary,
            hugo_args=cfg.hugo_args,
            output_dir=cfg.output_dir,
            clean=True,
        )
    except Exception as e:
        build_failed = True
        print(f"WARNING: hugo build failed: {e}", file=sys.stderr)

    if not build_failed:
        canonical = get_canonical_url(article, public_dir=public_dir, hugo_config=hugo_cfg)
        canonical_url = canonical.url
        canonical_source = canonical.source
        canonical_html = str(canonical.html_path.relative_to(repo_root).as_posix()) if canonical.html_path else None
    else:
        # build failed: fall back to baseURL + guessed path
        canonical = get_canonical_url(article, public_dir=public_dir, hugo_config=hugo_cfg)
        canonical_url = canonical.url
        canonical_source = "fallback"
        canonical_html = None

    tweet = compose_tweet(summary, url=canonical_url, hashtags=list(cfg.hashtags))

    print("\n--- Summary ---")
    print(summary)
    print("\n--- URL ---")
    print(canonical_url)
    if canonical_source:
        print(f"(url source: {canonical_source}{', html=' + canonical_html if canonical_html else ''})")
    if cfg.hashtags:
        print("\n--- Hashtags ---")
        print(" ".join(cfg.hashtags))

    print("\n--- Tweet ---")
    print(tweet)

    if dry_run:
        print("\nDRY_RUN=1: skip posting.")
        return 0

    missing = [name for name in REQUIRED_X_SECRETS if not (os.getenv(name) or "").strip()]
    if missing:
        if force_post:
            print(f"ERROR: Missing required Secrets for posting: {', '.join(missing)}", file=sys.stderr)
            return 2
        print(f"Secrets missing ({', '.join(missing)}). Skip posting for safety. Set FORCE_POST=1 to fail.", file=sys.stderr)
        return 0

    if build_failed:
        print("ERROR: hugo build failed; refusing to post in non-DRY_RUN mode.", file=sys.stderr)
        return 3

    from .post_to_x import post_to_x

    result = post_to_x(
        tweet,
        api_key=os.environ["X_API_KEY"],
        api_key_secret=os.environ["X_API_KEY_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
    )

    print(f"\nPosted to X. tweet_id={result.tweet_id}")

    _record_posted(
        state,
        article_id=article.article_id,
        payload={
            "id": article.article_id,
            "content_path": article.rel_source_path,
            "title": article.title,
            "canonical_url": canonical_url,
            "tweet_id": result.tweet_id,
            "posted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        },
    )
    _save_state(state_path, state)
    print(f"State updated: {state_path.relative_to(repo_root).as_posix()}")
    return 0


def _env_truthy(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off", ""}:
        return False
    return default


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "posted": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"version": 1, "posted": {}}
        if "posted" not in data or not isinstance(data.get("posted"), dict):
            data["posted"] = {}
        if "version" not in data:
            data["version"] = 1
        return data
    except Exception:
        return {"version": 1, "posted": {}}


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _record_posted(state: dict[str, Any], *, article_id: str, payload: dict[str, Any]) -> None:
    posted = state.setdefault("posted", {})
    if not isinstance(posted, dict):
        state["posted"] = {}
        posted = state["posted"]
    posted[article_id] = payload


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
