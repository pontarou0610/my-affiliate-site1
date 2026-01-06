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
    base_url = os.getenv("X_API_BASE_URL", "https://api.twitter.com").rstrip("/")
    endpoint = f"{base_url}/2/tweets"

    auth = OAuth1(api_key, api_key_secret, access_token, access_token_secret)
    resp = requests.post(
        endpoint,
        json={"text": tweet_text},
        auth=auth,
        timeout=timeout_sec,
        headers={"User-Agent": "hugo-x-autopost/1.0"},
    )

    if resp.status_code not in {200, 201}:
        body = resp.text
        body = body[:2000] + ("..." if len(body) > 2000 else "")
        raise RuntimeError(
            f"X API error: status={resp.status_code}\n"
            + textwrap.indent(body, prefix="  ")
        )

    data = resp.json()
    tweet_id = (data.get("data") or {}).get("id")
    if not tweet_id:
        raise RuntimeError(f"X API response missing tweet id: {data}")
    return PostResult(tweet_id=str(tweet_id), tweet_text=tweet_text)

