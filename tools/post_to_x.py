from __future__ import annotations

from dataclasses import dataclass

import os
import textwrap

import requests
from requests_oauthlib import OAuth1


@dataclass(frozen=True)
class PostResult:
    tweet_id: str
    tweet_text: str


def post_to_x(
    tweet_text: str,
    *,
    api_key: str,
    api_key_secret: str,
    access_token: str,
    access_token_secret: str,
    timeout_sec: int = 30,
) -> PostResult:
    base_urls = _candidate_base_urls()

    auth = OAuth1(api_key, api_key_secret, access_token, access_token_secret)

    errors: list[str] = []
    for base_url in base_urls:
        endpoint = f"{base_url.rstrip('/')}/2/tweets"
        resp = requests.post(
            endpoint,
            json={"text": tweet_text},
            auth=auth,
            timeout=timeout_sec,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; hugo-x-autopost/1.0)",
                "Accept": "application/json",
            },
        )

        if resp.status_code in {200, 201}:
            data = resp.json()
            tweet_id = (data.get("data") or {}).get("id")
            if not tweet_id:
                raise RuntimeError(f"X API response missing tweet id: {data}")
            return PostResult(tweet_id=str(tweet_id), tweet_text=tweet_text)

        errors.append(_format_error(base_url, resp))

    raise RuntimeError(
        "X API request failed.\n"
        + "\n".join(textwrap.indent(e, prefix="  ") for e in errors)
        + "\n\n"
        + "Hint: If you see a Cloudflare challenge (\"Just a moment...\") on GitHub-hosted runners, "
        + "try setting `X_API_BASE_URL=https://api.x.com` (or `https://api.twitter.com`) and re-run. "
        + "If it still fails, you may need a `self-hosted` runner (different egress IP)."
    )


def _candidate_base_urls() -> list[str]:
    primary = (os.getenv("X_API_BASE_URL") or "").strip()
    fallback = (os.getenv("X_API_BASE_URL_FALLBACK") or "").strip()
    defaults = ["https://api.x.com", "https://api.twitter.com"]

    ordered: list[str] = []
    for u in [primary, fallback, *defaults]:
        u = (u or "").strip()
        if not u:
            continue
        if not (u.startswith("http://") or u.startswith("https://")):
            continue
        u = u.rstrip("/")
        if u not in ordered:
            ordered.append(u)
    return ordered


def _format_error(base_url: str, resp: requests.Response) -> str:
    content_type = (resp.headers.get("content-type") or "").strip()
    body = resp.text or ""
    is_cloudflare = _looks_like_cloudflare_challenge(body)
    body_preview = body[:600] + ("..." if len(body) > 600 else "")

    note = " (cloudflare challenge detected)" if is_cloudflare else ""
    return (
        f"- base_url={base_url} status={resp.status_code} content_type={content_type}{note}\n"
        + textwrap.indent(body_preview, prefix="    ")
    )


def _looks_like_cloudflare_challenge(body: str) -> bool:
    b = (body or "")[:5000].lower()
    return ("just a moment" in b and "challenge" in b) or ("cdn-cgi" in b and "challenge" in b)
