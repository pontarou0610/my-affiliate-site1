#!/usr/bin/env python3
"""Print a compact GA4 traffic and affiliate-click report."""

from __future__ import annotations

import argparse
import csv
import json
import os
import posixpath
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
SITE_PATH_PREFIX = "/my-affiliate-site1"
COMMERCIAL_PAGES_PATH = REPO_ROOT / "data" / "commercial-pages.csv"
EXPERIMENTS_PATH = REPO_ROOT / "data" / "optimization-experiments.csv"


def env_path(name: str) -> Path:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        raise SystemExit(f"{name} is not set in .env")
    path = Path(raw)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def print_auth_status() -> int:
    """Print GA4 OAuth configuration status without starting browser auth."""
    load_dotenv(dotenv_path=REPO_ROOT / ".env")
    property_id = (os.getenv("GA4_PROPERTY_ID") or "").strip()
    missing = []
    for name in ("GA4_PROPERTY_ID", "GA4_OAUTH_CLIENT_FILE", "GA4_OAUTH_TOKEN_FILE"):
        if not (os.getenv(name) or "").strip():
            missing.append(name)
    if missing:
        print("GA4 auth status: incomplete")
        for name in missing:
            print(f"- missing: {name}")
        return 1

    client_file = env_path("GA4_OAUTH_CLIENT_FILE")
    token_file = env_path("GA4_OAUTH_TOKEN_FILE")
    print("GA4 auth status")
    print(f"- property_id: {property_id}")
    print(f"- oauth_client_file: {client_file} ({'exists' if client_file.exists() else 'missing'})")
    print(f"- oauth_token_file: {token_file} ({'exists' if token_file.exists() else 'missing'})")

    if not client_file.exists():
        print("- next: create/download the OAuth client JSON and update GA4_OAUTH_CLIENT_FILE")
        return 1
    if not token_file.exists():
        print("- next: run `python scripts/report_ga4.py --force-auth` and approve the Google prompt")
        return 1

    try:
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
    except ValueError as exc:
        print(f"- token: unreadable ({exc})")
        print("- next: delete the token file and run `python scripts/report_ga4.py --force-auth`")
        return 1

    if creds.valid:
        print("- token: valid")
        return 0
    if creds.expired and creds.refresh_token:
        print("- token: expired but refreshable")
        return 0
    print("- token: invalid or missing refresh token")
    print("- next: run `python scripts/report_ga4.py --force-auth` and approve the Google prompt")
    return 1


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


def response_complete(response: dict) -> bool:
    rows = response.get("rows") or []
    return int(response.get("rowCount", len(rows))) <= len(rows)


def realtime_affiliate_clicks(service, property_id: str) -> int:
    response = (
        service.properties()
        .runRealtimeReport(
            property=f"properties/{property_id}",
            body={
                "dimensions": [{"name": "eventName"}],
                "metrics": [{"name": "eventCount"}],
                "dimensionFilter": affiliate_click_filter(),
                "limit": 10,
            },
        )
        .execute()
    )
    return sum(
        int(float(row["metricValues"][0]["value"]))
        for row in response.get("rows", [])
    )


def normalize_page_path(path: str) -> str:
    raw = (path or "/").split("?", 1)[0].strip() or "/"
    if raw == SITE_PATH_PREFIX:
        raw = "/"
    elif raw.startswith(f"{SITE_PATH_PREFIX}/"):
        raw = raw[len(SITE_PATH_PREFIX) :]
    normalized = posixpath.normpath(f"/{raw.lstrip('/')}")
    if normalized != "/":
        normalized += "/"
    return normalized


def load_commercial_page_rules(
    rules_path: Path = COMMERCIAL_PAGES_PATH,
    experiments_path: Path = EXPERIMENTS_PATH,
) -> list[dict[str, str]]:
    rules: list[dict[str, str]] = []
    if rules_path.exists():
        with rules_path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                raw_path = (row.get("path") or "").strip()
                if not raw_path or not raw_path.startswith("/"):
                    raise SystemExit(
                        f"Commercial page path must be a non-empty absolute path: `{raw_path}`"
                    )
                path = normalize_page_path(raw_path)
                match_type = (row.get("match_type") or "exact").strip().lower()
                if match_type not in {"exact", "prefix"}:
                    raise SystemExit(
                        f"Invalid commercial page match_type `{match_type}` for {path}"
                    )
                rules.append(
                    {
                        "path": path,
                        "match_type": match_type,
                        "reason": (row.get("reason") or "").strip(),
                    }
                )
    if experiments_path.exists():
        with experiments_path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                if (
                    (row.get("status") or "").strip().lower() != "active"
                    or (row.get("commercial_intent") or "").strip().lower()
                    not in {"true", "yes", "1"}
                ):
                    continue
                raw_page = (row.get("page") or "").strip()
                if not raw_page or not raw_page.startswith("/"):
                    raise SystemExit(
                        f"Active commercial experiment has invalid page: `{raw_page}`"
                    )
                rules.append(
                    {
                        "path": normalize_page_path(raw_page),
                        "match_type": "exact",
                        "reason": f"Active experiment: {row.get('experiment_id') or ''}",
                    }
                )
    unique: dict[tuple[str, str], dict[str, str]] = {}
    for rule in rules:
        unique[(rule["path"], rule["match_type"])] = rule
    return list(unique.values())


def is_commercial_page(path: str, rules: list[dict[str, str]]) -> bool:
    normalized = normalize_page_path(path)
    for rule in rules:
        rule_path = rule["path"]
        if rule["match_type"] == "exact" and normalized == rule_path:
            return True
        if rule["match_type"] == "prefix" and normalized.startswith(rule_path):
            return True
    return False


def commercial_metrics(
    daily_pages: list[dict],
    click_pages: dict[str, int],
    rules: list[dict[str, str]],
    *,
    complete: bool = True,
) -> dict:
    pageviews: dict[str, int] = {}
    for row in daily_pages:
        path = normalize_page_path(row.get("path") or "")
        if is_commercial_page(path, rules):
            pageviews[path] = pageviews.get(path, 0) + int(row.get("views") or 0)
    pages = [
        {
            "path": path,
            "views": views,
            "affiliate_clicks": int(click_pages.get(path, 0)),
            "affiliate_ctr": (int(click_pages.get(path, 0)) / views) if views else 0,
        }
        for path, views in pageviews.items()
    ]
    pages.sort(key=lambda item: (-item["views"], item["path"]))
    views = sum(item["views"] for item in pages)
    clicks = sum(int(click_pages.get(item["path"], 0)) for item in pages)
    return {
        "pageviews": views,
        "affiliate_clicks": clicks,
        "affiliate_ctr": (clicks / views) if views else 0,
        "pages": pages,
        "rule_count": len(rules),
        "complete": complete,
    }


def commercial_program_clicks(
    rows: list[dict],
    rules: list[dict[str, str]],
    *,
    complete: bool,
    reason: str = "",
) -> dict:
    values: dict[str, int] = {}
    for row in rows:
        if not is_commercial_page(row.get("path") or "", rules):
            continue
        program = (row.get("program") or "(not set)").strip().lower()
        values[program] = values.get(program, 0) + int(row.get("clicks") or 0)
    return {
        "values": dict(sorted(values.items())),
        "complete": complete,
        "reason": reason,
    }


def infer_affiliate_program(store: str, slot: str) -> str:
    normalized_store = (store or "").strip().lower()
    normalized_slot = (slot or "").strip().lower()
    if "unlimited" in normalized_slot:
        return "kindle_unlimited"
    if "audible" in normalized_slot:
        return "audible"
    if normalized_slot.startswith("fiction-"):
        return "kdp"
    if normalized_store in {"rakuten", "yahoo"}:
        return normalized_store
    if normalized_store != "amazon":
        return ""
    standard_amazon_signals = (
        "paperwhite",
        "kindle-device",
        "kindle-book",
        "post-europe-kindle",
        "redmi",
        "tablet",
        "mini-pc",
        "storage",
    )
    if any(signal in normalized_slot for signal in standard_amazon_signals):
        return "amazon"
    return ""


def inferred_commercial_program_clicks(
    rows: list[dict],
    rules: list[dict[str, str]],
    *,
    complete: bool,
) -> dict:
    values: dict[str, int] = {}
    unattributed_clicks = 0
    for row in rows:
        if not is_commercial_page(row.get("path") or "", rules):
            continue
        clicks = int(row.get("clicks") or 0)
        program = infer_affiliate_program(
            row.get("store") or "",
            row.get("slot") or "",
        )
        if not program:
            unattributed_clicks += clicks
            continue
        values[program] = values.get(program, 0) + clicks
    return {
        "values": dict(sorted(values.items())),
        "complete": complete,
        "unattributed_clicks": unattributed_clicks,
        "method": "inferred_from_affiliate_store_and_slot",
    }


def commercial_period_snapshot(
    service,
    property_id: str,
    start: date,
    end: date,
    rules: list[dict[str, str]],
) -> dict:
    page_response = run_report(
        service,
        property_id,
        {
            "dateRanges": [{"startDate": start.isoformat(), "endDate": end.isoformat()}],
            "dimensions": [{"name": "pagePath"}],
            "metrics": [{"name": "screenPageViews"}],
            "limit": 100_000,
        },
    )
    page_rows = [
        {
            "path": normalize_page_path(row["dimensionValues"][0]["value"]),
            "views": int(float(row["metricValues"][0]["value"])),
        }
        for row in page_response.get("rows", [])
    ]
    click_response = run_report(
        service,
        property_id,
        {
            "dateRanges": [{"startDate": start.isoformat(), "endDate": end.isoformat()}],
            "dimensions": [{"name": "pagePath"}],
            "metrics": [{"name": "eventCount"}],
            "dimensionFilter": affiliate_click_filter(),
            "limit": 100_000,
        },
    )
    click_pages = {
        normalize_page_path(row["dimensionValues"][0]["value"]): int(
            float(row["metricValues"][0]["value"])
        )
        for row in click_response.get("rows", [])
    }
    result = commercial_metrics(
        page_rows,
        click_pages,
        rules,
        complete=response_complete(page_response) and response_complete(click_response),
    )
    result["range"] = {"start": start.isoformat(), "end": end.isoformat()}
    return result


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
            "limit": max(limit * 3, 100),
        },
    )
    aggregated: dict[str, dict[str, int]] = {}
    for row in resp.get("rows", []):
        path = normalize_page_path(row["dimensionValues"][0]["value"])
        views = int(float(row["metricValues"][0]["value"]))
        users = int(float(row["metricValues"][1]["value"]))
        item = aggregated.setdefault(path, {"views": 0, "users": 0})
        item["views"] += views
        item["users"] += users

    pages = [
        {"path": path, "views": values["views"], "users": values["users"]}
        for path, values in aggregated.items()
    ]
    pages.sort(key=lambda item: (-item["views"], -item["users"], item["path"]))

    print("\nTop pages 28d")
    print("views\tusers\tpath")
    for page in pages[:limit]:
        path = page["path"]
        views = page["views"]
        users = page["users"]
        print(f"{views}\t{users}\t{path}")
    return pages[:limit]


def print_affiliate_clicks(
    service,
    property_id: str,
    start: date,
    end: date,
) -> tuple[int, dict[str, int], dict[str, dict[str, int]], bool]:
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
            "limit": 10_000,
        },
    )
    click_pages_complete = response_complete(by_page)
    print("\nAffiliate click pages 28d")
    print("clicks\tpath")
    for row in by_page.get("rows", []):
        path = normalize_page_path(row["dimensionValues"][0]["value"])
        count = int(float(row["metricValues"][0]["value"]))
        click_pages[path] = click_pages.get(path, 0) + count
    for path, count in sorted(click_pages.items(), key=lambda item: (-item[1], item[0])):
        print(f"{count}\t{path}")
    if not click_pages:
        print("0\t(no affiliate click page rows yet)")

    breakdowns: dict[str, dict[str, int]] = {}
    for dimension in (
        "customEvent:affiliate_store",
        "customEvent:affiliate_program",
        "customEvent:affiliate_slot",
        "customEvent:link_id",
    ):
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
                    "limit": 100,
                },
            )
        except HttpError:
            print(f"{dimension}: unavailable; register it as a GA4 custom definition first.")
            breakdowns[dimension] = {}
            continue
        except TimeoutError:
            print(f"{dimension}: request timed out; rerun the report later to refresh this breakdown.")
            breakdowns[dimension] = {}
            continue
        print(f"\n{dimension}")
        values: dict[str, int] = {}
        for index, row in enumerate(by_dimension.get("rows", [])):
            value = row["dimensionValues"][0]["value"] or "(not set)"
            count = int(float(row["metricValues"][0]["value"]))
            values[value] = values.get(value, 0) + count
            if index < 20:
                print(f"{count}\t{value}")
        breakdowns[dimension] = values
    return total, click_pages, breakdowns, click_pages_complete


def affiliate_program_rows(
    service,
    property_id: str,
    start: date,
    end: date,
) -> tuple[list[dict], bool, str]:
    try:
        response = run_report(
            service,
            property_id,
            {
                "dateRanges": [{"startDate": start.isoformat(), "endDate": end.isoformat()}],
                "dimensions": [
                    {"name": "pagePath"},
                    {"name": "customEvent:affiliate_program"},
                ],
                "metrics": [{"name": "eventCount"}],
                "dimensionFilter": affiliate_click_filter(),
                "limit": 100_000,
            },
        )
    except HttpError:
        return [], False, "Register affiliate_program as an event-scoped GA4 custom dimension."
    except TimeoutError:
        return [], False, "GA4 affiliate_program request timed out."
    rows = [
        {
            "path": normalize_page_path(row["dimensionValues"][0]["value"]),
            "program": row["dimensionValues"][1]["value"] or "(not set)",
            "clicks": int(float(row["metricValues"][0]["value"])),
        }
        for row in response.get("rows", [])
    ]
    return rows, response_complete(response), ""


def daily_experiment_metrics(
    service,
    property_id: str,
    start: date,
    end: date,
) -> tuple[list[dict], list[dict], dict[str, bool]]:
    page_response = run_report(
        service,
        property_id,
        {
            "dateRanges": [{"startDate": start.isoformat(), "endDate": end.isoformat()}],
            "dimensions": [{"name": "date"}, {"name": "pagePath"}],
            "metrics": [{"name": "screenPageViews"}],
            "limit": 100_000,
        },
    )
    daily_pages = [
        {
            "date": row["dimensionValues"][0]["value"],
            "path": normalize_page_path(row["dimensionValues"][1]["value"]),
            "views": int(float(row["metricValues"][0]["value"])),
        }
        for row in page_response.get("rows", [])
    ]

    daily_slots: list[dict] = []
    status = {
        "page_views": response_complete(page_response),
        "page_slot_clicks": True,
    }
    try:
        slot_response = run_report(
            service,
            property_id,
            {
                "dateRanges": [{"startDate": start.isoformat(), "endDate": end.isoformat()}],
                "dimensions": [
                    {"name": "date"},
                    {"name": "pagePath"},
                    {"name": "customEvent:affiliate_store"},
                    {"name": "customEvent:affiliate_slot"},
                ],
                "metrics": [{"name": "eventCount"}],
                "dimensionFilter": affiliate_click_filter(),
                "limit": 100_000,
            },
        )
        daily_slots = [
            {
                "date": row["dimensionValues"][0]["value"],
                "path": normalize_page_path(row["dimensionValues"][1]["value"]),
                "store": row["dimensionValues"][2]["value"] or "(not set)",
                "slot": row["dimensionValues"][3]["value"] or "(not set)",
                "clicks": int(float(row["metricValues"][0]["value"])),
            }
            for row in slot_response.get("rows", [])
        ]
        status["page_slot_clicks"] = response_complete(slot_response)
    except (HttpError, TimeoutError):
        status["page_slot_clicks"] = False
    return daily_pages, daily_slots, status


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
    parser.add_argument(
        "--auth-status",
        action="store_true",
        help="Check GA4 OAuth configuration without opening a browser or querying GA4",
    )
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
    parser.add_argument(
        "--json-output",
        type=Path,
        help="Write the report data as JSON for downstream KPI reporting",
    )
    parser.add_argument(
        "--realtime-check",
        action="store_true",
        help="Also print affiliate_click events visible in the GA4 realtime window",
    )
    args = parser.parse_args()

    if args.auth_status:
        return print_auth_status()

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
    realtime_clicks = None
    if args.realtime_check:
        realtime_clicks = realtime_affiliate_clicks(service, property_id)
        print(f"Realtime affiliate clicks: {realtime_clicks}")

    end = date.today() - timedelta(days=1)
    start28 = end - timedelta(days=27)
    previous_end = start28 - timedelta(days=1)
    previous_start = previous_end - timedelta(days=27)
    start7 = end - timedelta(days=6)

    print(f"GA4 property: {property_id}")
    print(f"28d range: {start28.isoformat()} to {end.isoformat()}")

    totals_by_period: dict[str, dict[str, int]] = {}
    for label, start in (("Last 28 days", start28), ("Last 7 days", start7)):
        users, sessions, views, events = metric_totals(service, property_id, start, end)
        totals_by_period[label] = {
            "active_users": int(users),
            "sessions": int(sessions),
            "pageviews": int(views),
            "events": int(events),
        }
        print(f"{label}: activeUsers={users:.0f}, sessions={sessions:.0f}, pageViews={views:.0f}, events={events:.0f}")

    top_pages = print_top_pages(service, property_id, start28, end, args.top)
    total_clicks, click_pages, click_breakdowns, click_pages_complete = print_affiliate_clicks(
        service,
        property_id,
        start28,
        end,
    )
    daily_pages, daily_slots, experiment_data_status = daily_experiment_metrics(
        service,
        property_id,
        start28,
        end,
    )
    program_rows, program_rows_complete, program_reason = affiliate_program_rows(
        service,
        property_id,
        start28,
        end,
    )
    experiment_data_status["affiliate_click_pages"] = click_pages_complete
    commercial_rules = load_commercial_page_rules()
    commercial = commercial_metrics(
        daily_pages,
        click_pages,
        commercial_rules,
        complete=(
            experiment_data_status["page_views"]
            and experiment_data_status["affiliate_click_pages"]
        ),
    )
    commercial_programs = commercial_program_clicks(
        program_rows,
        commercial_rules,
        complete=program_rows_complete,
        reason=program_reason,
    )
    inferred_commercial_programs = inferred_commercial_program_clicks(
        daily_slots,
        commercial_rules,
        complete=experiment_data_status["page_slot_clicks"],
    )
    previous_commercial = commercial_period_snapshot(
        service,
        property_id,
        previous_start,
        previous_end,
        commercial_rules,
    )
    last28_views = totals_by_period["Last 28 days"]["pageviews"]
    if last28_views:
        print(f"\nSite affiliate CTR 28d: {(total_clicks / last28_views * 100):.2f}%")
    print_opportunity_pages(top_pages, click_pages)
    print(
        "\nCommercial-intent pages 28d: "
        f"pageViews={commercial['pageviews']}, "
        f"affiliateClicks={commercial['affiliate_clicks']}, "
        f"CTR={commercial['affiliate_ctr']:.2%}"
    )

    if args.json_output:
        output_path = args.json_output
        if not output_path.is_absolute():
            output_path = REPO_ROOT / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "property_id": property_id,
            "generated_on": date.today().isoformat(),
            "range_28d": {"start": start28.isoformat(), "end": end.isoformat()},
            "range_7d": {"start": start7.isoformat(), "end": end.isoformat()},
            "totals_28d": totals_by_period["Last 28 days"],
            "totals_7d": totals_by_period["Last 7 days"],
            "affiliate_clicks_28d": total_clicks,
            "affiliate_ctr_28d": (total_clicks / last28_views) if last28_views else 0,
            "top_pages_28d": [
                {
                    **page,
                    "affiliate_clicks": click_pages.get(page["path"], 0),
                    "affiliate_ctr": (
                        click_pages.get(page["path"], 0) / page["views"]
                        if page["views"]
                        else 0
                    ),
                }
                for page in top_pages
            ],
            "affiliate_click_pages_28d": click_pages,
            "affiliate_click_breakdowns_28d": click_breakdowns,
            "daily_page_metrics_28d": daily_pages,
            "daily_affiliate_page_slots_28d": daily_slots,
            "experiment_data_status": experiment_data_status,
            "commercial_metrics_28d": commercial,
            "previous_commercial_metrics_28d": previous_commercial,
            "commercial_program_clicks_28d": commercial_programs,
            "inferred_commercial_program_clicks_28d": inferred_commercial_programs,
        }
        if realtime_clicks is not None:
            payload["affiliate_clicks_realtime"] = realtime_clicks
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"\nJSON report: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
