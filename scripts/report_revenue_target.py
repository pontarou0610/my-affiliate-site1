#!/usr/bin/env python3
"""Calculate traffic and conversion requirements for a monthly revenue target."""

from __future__ import annotations

import argparse
import math


def required_count(target: int, reward: float) -> int:
    return math.ceil(target / reward) if reward > 0 else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-yen", type=int, default=100_000)
    parser.add_argument("--affiliate-ctr", type=float, default=0.08)
    parser.add_argument("--epc-yen", type=float, default=40.0)
    parser.add_argument("--commercial-pageviews", type=int, default=0)
    parser.add_argument("--kindle-device-aov", type=float, default=25_000.0)
    parser.add_argument("--kindle-book-aov", type=float, default=1_200.0)
    args = parser.parse_args()

    if not 0 < args.affiliate_ctr <= 1:
        raise SystemExit("--affiliate-ctr must be between 0 and 1")
    if args.epc_yen <= 0:
        raise SystemExit("--epc-yen must be greater than 0")

    target_clicks = required_count(args.target_yen, args.epc_yen)
    target_pageviews = math.ceil(target_clicks / args.affiliate_ctr)
    current_click_capacity = args.commercial_pageviews * args.affiliate_ctr
    current_revenue_capacity = current_click_capacity * args.epc_yen

    device_reward = args.kindle_device_aov * 0.045
    book_reward = args.kindle_book_aov * 0.08

    print("Monthly revenue target model")
    print(f"- target: {args.target_yen:,} yen")
    print(f"- assumed affiliate CTR: {args.affiliate_ctr:.1%}")
    print(f"- assumed earnings per click: {args.epc_yen:,.0f} yen")
    print(f"- required affiliate clicks: {target_clicks:,}")
    print(f"- required commercial-intent pageviews: {target_pageviews:,}")
    if args.commercial_pageviews:
        print(f"- current commercial-intent pageviews: {args.commercial_pageviews:,}")
        print(f"- modeled revenue at current traffic: {current_revenue_capacity:,.0f} yen")
        print(f"- traffic multiple still required: {target_pageviews / args.commercial_pageviews:.1f}x")

    print("\nSingle-program equivalents")
    print(f"- Kindle Unlimited registrations (500 yen): {required_count(args.target_yen, 500):,}")
    print(f"- Audible registrations (1,500 yen): {required_count(args.target_yen, 1_500):,}")
    print(
        f"- Kindle device orders ({args.kindle_device_aov:,.0f} yen AOV x 4.5%): "
        f"{required_count(args.target_yen, device_reward):,}"
    )
    print(
        f"- Kindle book orders ({args.kindle_book_aov:,.0f} yen AOV x 8%): "
        f"{required_count(args.target_yen, book_reward):,}"
    )
    print("\nReplace assumptions with actual partner-report values every month.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
