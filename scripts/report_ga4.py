#!/usr/bin/env python3
"""Print a compact GA4 traffic and affiliate-click report."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


REPO_ROOT = Path(__file__).resolve().parents[1]
SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]


def env_path(name: str) -> Path:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        raise SystemExit(f"{name} is not set in .env")
    path = Path(raw)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def load_credentials(
    force_auth: bool = False,
    *,
    open_browser: bool = True,
    auth_timeout_seconds: int | None = 180,
) -> Credentials:
    client_file = env_path("GA4_OAUTH_CLIENT_FILE")
    token_file = env_path("GA4_OAUTH_TOKEN_FILE")

    creds = None
    if token_file.exists() and not force_auth:
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError as exc:
            print(
                "Saved GA4 OAuth token is expired or revoked; starting OAuth again.",
                file=sys.stderr,
            )
            token_file.unlink(missing_ok=True)
            creds = None

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(client_file), SCOPES)
        try:
            creds = flow.run_local_server(
                port=0,
                open_browser=open_browser,
                timeout_seconds=auth_timeout_seconds,
            )
        except (TimeoutError, AttributeError) as exc:
            raise SystemExit(
                "GA4 OAuth authorization did not complete in time. "
                "Run again with --force-auth after approving the Google browser prompt, "
                "or increase --auth-timeout-seconds."
            ) from exc

    token_file.write_text(creds.to_json(), encoding="utf-8")
    return creds


def run_report(service, property_id: str, body: dict) -> dict:
    return service.properties().runReport(property=f"properties/{property_id}", body=body).execute()


def metric_totals(service, property_id: str, start: date, end: date) -> list[float]:
    resp = run_report(
        service,
        property_id,
        {
            "dateRanges": [{"startDate": start.isoformat(), "endDate": end.isoformat()}],
            "metrics": [
                {"name": "activeUsers"},
                {"name": "sessions"},
                {"name": "screenPageViews"},
                {"name": "eventCount"},
            ],
        },
    )
    rows = resp.get("rows") or []
    values = rows[0].get("metricValues", []) if rows else []
    nums = [float(v.get("value", "0")) for v in values]
    return nums + [0.0] * (4 - len(nums))


def affiliate_click_filter() -> dict:
    return {
        "filter": {
            "fieldName": "eventName",
            "stringFilter": {"matchType": "EXACT", "value": "affiliate_click"},
        }
    }


def print_top_pages(service, property_id: str, start: date, end: date, limit: int) -> list[dict]:
    resp = run_report(
        service,
        property_id,
        {
            "dateRanges": [{"startDate": start.isoformat(), "endDate": end.isoformat()}],
            "dimensions": [{"name": "pagePath"}],
            "metrics": [{"name": "screenPageViews"}, {"name": "activeUsers"}],
            "orderBys": [{"metric": {"metricName": "screenPageViews"}, "desc": True}],
            "limit": limit,
        },
    )
    print("\nTop pages 28d")
    print("views\tusers\tpath")
    pages = []
    for row in resp.get("rows", []):
        path = row["dimensionValues"][0]["value"]
        views = int(float(row["metricValues"][0]["value"]))
        users = int(float(row["metricValues"][1]["value"]))
        pages.append({"path": path, "views": views, "users": users})
        print(f"{views}\t{users}\t{path}")
    return pages


def print_affiliate_clicks(service, property_id: str, start: date, end: date) -> tuple[int, dict[str, int]]:
    dimension_filter = affiliate_click_filter()
    body = {
        "dateRanges": [{"startDate": start.isoformat(), "endDate": end.isoformat()}],
        "dimensions": [{"name": "eventName"}],
        "metrics": [{"name": "eventCount"}],
        "dimensionFilter": dimension_filter,
        "limit": 10,
    }
    resp = run_report(service, property_id, body)
    total = sum(int(float(row["metricValues"][0]["value"])) for row in resp.get("rows", []))
    print(f"\nAffiliate clicks 28d: {total}")

    click_pages: dict[str, int] = {}
    by_page = run_report(
        service,
        property_id,
        {
            "dateRanges": [{"startDate": start.isoformat(), "endDate": end.isoformat()}],
            "dimensions": [{"name": "pagePath"}],
            "metrics": [{"name": "eventCount"}],
            "dimensionFilter": dimension_filter,
            "orderBys": [{"metric": {"metricName": "eventCount"}, "desc": True}],
            "limit": 20,
        },
    )
    print("\nAffiliate click pages 28d")
    print("clicks\tpath")
    for row in by_page.get("rows", []):
        path = row["dimensionValues"][0]["value"]
        count = int(float(row["metricValues"][0]["value"]))
        click_pages[path] = count
        print(f"{count}\t{path}")
    if not click_pages:
        print("0\t(no affiliate click page rows yet)")

    for dimension in ("customEvent:affiliate_store", "customEvent:affiliate_slot"):
        try:
            by_dimension = run_report(
                service,
                property_id,
                {
                    "dateRanges": [{"startDate": start.isoformat(), "endDate": end.isoformat()}],
                    "dimensions": [{"name": dimension}],
                    "metrics": [{"name": "eventCount"}],
                    "dimensionFilter": dimension_filter,
                    "orderBys": [{"metric": {"metricName": "eventCount"}, "desc": True}],
                    "limit": 10,
                },
            )
        except HttpError:
            print(f"{dimension}: unavailable; register it as a GA4 custom definition first.")
            continue
        print(f"\n{dimension}")
        for row in by_dimension.get("rows", []):
            value = row["dimensionValues"][0]["value"] or "(not set)"
            count = row["metricValues"][0]["value"]
            print(f"{count}\t{value}")
    return total, click_pages


def print_opportunity_pages(top_pages: list[dict], click_pages: dict[str, int], limit: int = 8) -> None:
    print("\nOpportunity pages 28d")
    print("views\tclicks\tctr\tpath")
    rows = []
    for page in top_pages:
        views = int(page["views"])
        clicks = click_pages.get(page["path"], 0)
        ctr = (clicks / views * 100) if views else 0
        rows.append((clicks > 0, views, clicks, ctr, page["path"]))

    opportunities = [row for row in rows if not row[0]]
    if not opportunities:
        print("0\t0\t0.00%\t(no zero-click top pages in this report)")
        return

    for _has_clicks, views, clicks, ctr, path in opportunities[:limit]:
        print(f"{views}\t{clicks}\t{ctr:.2f}%\t{path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Report GA4 traffic and affiliate clicks.")
    parser.add_argument("--force-auth", action="store_true", help="Ignore saved token and run OAuth again")
    parser.add_argument(
        "--no-open-browser",
        action="store_true",
        help="Print the OAuth URL instead of opening a browser automatically",
    )
    parser.add_argument(
        "--auth-timeout-seconds",
        type=int,
        default=180,
        help="Seconds to wait for OAuth approval when a fresh token is needed",
    )
    parser.add_argument("--top", type=int, default=10, help="Number of top pages to show")
    args = parser.parse_args()

    load_dotenv(dotenv_path=REPO_ROOT / ".env")
    property_id = (os.getenv("GA4_PROPERTY_ID") or "").strip()
    if not property_id:
        raise SystemExit("GA4_PROPERTY_ID is not set in .env")

    creds = load_credentials(
        force_auth=args.force_auth,
        open_browser=not args.no_open_browser,
        auth_timeout_seconds=args.auth_timeout_seconds,
    )
    service = build("analyticsdata", "v1beta", credentials=creds, cache_discovery=False)

    end = date.today() - timedelta(days=1)
    start28 = end - timedelta(days=27)
    start7 = end - timedelta(days=6)

    print(f"GA4 property: {property_id}")
    print(f"28d range: {start28.isoformat()} to {end.isoformat()}")

    last28_views = 0.0
    for label, start in (("Last 28 days", start28), ("Last 7 days", start7)):
        users, sessions, views, events = metric_totals(service, property_id, start, end)
        if label == "Last 28 days":
            last28_views = views
        print(f"{label}: activeUsers={users:.0f}, sessions={sessions:.0f}, pageViews={views:.0f}, events={events:.0f}")

    top_pages = print_top_pages(service, property_id, start28, end, args.top)
    total_clicks, click_pages = print_affiliate_clicks(service, property_id, start28, end)
    if last28_views:
        print(f"\nSite affiliate CTR 28d: {(total_clicks / last28_views * 100):.2f}%")
    print_opportunity_pages(top_pages, click_pages)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
