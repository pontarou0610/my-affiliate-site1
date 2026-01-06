from __future__ import annotations

import re


_RE_URL = re.compile(r"https?://\S+")


def compose_tweet(summary: str, *, url: str, hashtags: list[str] | tuple[str, ...] = (), max_chars: int = 280) -> str:
    summary = (summary or "").strip()
    url = (url or "").strip()
    tags = _normalize_hashtags(list(hashtags))

    tweet = _join_parts(summary, url=url, hashtags=tags)
    if _tweet_length(tweet) <= max_chars:
        return tweet

    # If hashtags cause overflow, drop them first.
    if tags:
        tweet_no_tags = _join_parts(summary, url=url, hashtags="")
        if _tweet_length(tweet_no_tags) <= max_chars:
            return tweet_no_tags
        tags = ""

    placeholder = "__SUMMARY__"
    base = _join_parts(placeholder, url=url, hashtags=tags)
    base_len_without_summary = _tweet_length(base) - len(placeholder)
    allowed = max(0, max_chars - base_len_without_summary)
    summary_trimmed = _truncate(summary, allowed)
    return _join_parts(summary_trimmed, url=url, hashtags=tags)


def _join_parts(summary: str, *, url: str, hashtags: str) -> str:
    parts: list[str] = []
    if summary.strip():
        parts.append(summary.strip())
    if url.strip():
        parts.append(url.strip())
    if hashtags.strip():
        parts.append(hashtags.strip())
    return "\n".join(parts).strip()


def _normalize_hashtags(tags: list[str]) -> str:
    normalized: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        t = (tag or "").strip()
        if not t:
            continue
        if t.startswith("#"):
            t = "#" + t[1:].strip()
        else:
            t = "#" + t
        if t == "#":
            continue
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(t)
    return " ".join(normalized)


def _tweet_length(text: str) -> int:
    # Approximate X counting: URLs are t.co-shortened (typically 23 chars).
    def repl(_: re.Match[str]) -> str:
        return "x" * 23

    return len(_RE_URL.sub(repl, text))


def _truncate(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rstrip()
    last = max(cut.rfind("。"), cut.rfind("！"), cut.rfind("？"), cut.rfind("!"), cut.rfind("?"))
    if last >= max(0, max_chars - 20):
        cut = cut[: last + 1].rstrip()
    return cut
