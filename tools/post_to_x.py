from __future__ import annotations

from dataclasses import dataclass

import os
import textwrap
import json

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
    saw_forbidden_not_permitted = False
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

        if resp.status_code == 403 and _looks_like_not_permitted(resp):
            saw_forbidden_not_permitted = True
        errors.append(_format_error(base_url, resp))

    hint_parts: list[str] = []
    if saw_forbidden_not_permitted:
        hint_parts.append(
            "Hint: 403 Forbidden with \"You are not permitted to perform this action.\" usually means "
            "your X App (and/or the issued user access token) does not have write permission for posting. "
            "Check App permissions (Read and write) and re-generate the OAuth 1.0a Access Token/Secret, "
            "then update GitHub Secrets."
        )
    hint_parts.append(
        "Hint: If you see a Cloudflare challenge (\"Just a moment...\") on GitHub-hosted runners, "
        "try setting `X_API_BASE_URL=https://api.x.com` and re-run. "
        "If it still fails, you may need a `self-hosted` runner (different egress IP)."
    )

    raise RuntimeError(
        "X API request failed.\n"
        + "\n".join(textwrap.indent(e, prefix="  ") for e in errors)
        + "\n\n"
        + "\n".join(hint_parts)
    )


def _candidate_base_urls() -> list[str]:
    primary = (os.getenv("X_API_BASE_URL") or "").strip()
    fallback = (os.getenv("X_API_BASE_URL_FALLBACK") or "").strip()
    # Prefer api.x.com. api.twitter.com may trigger Cloudflare challenges on some runners/IP ranges.
    defaults = ["https://api.x.com"]

    ordered: list[str] = []
    if primary:
        candidates = [primary, fallback]
    else:
        candidates = [fallback, *defaults]

    for u in candidates:
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


def _looks_like_not_permitted(resp: requests.Response) -> bool:
    content_type = (resp.headers.get("content-type") or "").lower()
    if "json" not in content_type:
        return False
    try:
        data = resp.json()
    except Exception:
        try:
            data = json.loads(resp.text or "")
        except Exception:
            return False
    if not isinstance(data, dict):
        return False
    detail = str(data.get("detail") or "")
    title = str(data.get("title") or "")
    return ("not permitted" in detail.lower()) or ("forbidden" == title.lower())
