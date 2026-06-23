# Monthly 100,000 Yen Revenue Roadmap

## Goal

Build toward 100,000 yen in monthly affiliate and owned-book revenue. This is a business target, not a guarantee.

The operating equation is:

```text
commercial-intent pageviews
x affiliate click-through rate
x earnings per click
= monthly revenue
```

Run the planning model after reading `commercial_metrics_28d.pageviews` from
the latest GA4 JSON:

```powershell
python scripts/report_revenue_target.py `
  --commercial-pageviews <commercial_metrics_28d.pageviews> `
  --affiliate-ctr 0.08 `
  --epc-yen 40
```

The default planning case requires about 31,250 commercial-intent pageviews:

```text
31,250 pageviews x 8% CTR x 40 yen EPC = 100,000 yen
```

EPC must be replaced with actual Amazon, Rakuten, Yahoo, and KDP results. GA4 measures clicks; partner reports control revenue and conversions.

## Official Revenue Anchors

As of June 22, 2026:

- Kindle books: 8% standard Amazon Associates rate
- Kindle devices: 4.5% standard Amazon Associates rate
- Kindle Unlimited eligible registration: 500 yen
- Audible eligible new registration: 1,500 yen

Sources:

- https://affiliate.amazon.co.jp/help/node/topic/GRXPHT8U84RAYDXZ
- https://affiliate.amazon.co.jp/help/node/topic/GDFUA9UXMWT4L5UR
- https://affiliate.amazon.co.jp/help/node/topic/GSQVXX57YEX6QXEH

Always verify current conditions before publishing a numerical claim.

## KPI System

Primary outcomes:

1. Monthly confirmed revenue from partner/KDP reports
2. Commercial-intent pageviews, defined by `data/commercial-pages.csv` plus
   active experiment pages
3. Affiliate clicks and affiliate CTR

Drivers:

- Search clicks to `/recommend/`, Kindle/Kobo LPs, reviews, subscription comparisons, and Audible
- CTA clicks by `affiliate_store`, `affiliate_slot`, and `link_id`
- Revenue per click by program and page

Guardrails:

- Expired campaigns are noindex or rewritten as evergreen content
- No misleading current-price or current-campaign claims
- New candidates do not cannibalize a stronger existing pillar page

## Milestones

### Stage 1: Measurement works

- Local development traffic is excluded from GA4
- At least one real `affiliate_click` is visible
- Amazon/Rakuten/Yahoo/KDP revenue is recorded monthly

### Stage 2: First repeatable conversions

- 1,000 commercial-intent pageviews/month
- Affiliate CTR at least 3%
- Identify the first page, slot, and program producing revenue

### Stage 3: Scale proven pages

- 10,000 commercial-intent pageviews/month
- Affiliate CTR at least 5%
- Refresh and internally link only pages with demonstrated search or revenue potential

### Stage 4: Approach 100,000 yen

- Approximately 31,250 commercial-intent pageviews/month at 8% CTR and 40 yen EPC
- Diversified revenue across subscriptions, devices/books, Rakuten/Yahoo, and owned Kindle titles

## Weekly Operating Loop

1. Run `python scripts/report_ga4.py --top 40`.
2. Run `python scripts/report_gsc.py --days 28 --top 20`, then
   `python scripts/record_kpi_snapshot.py` to preserve the weekly baseline.
3. Export monthly partner revenue and run
   `python scripts/report_business_kpis.py --month YYYY-MM`.
4. Improve the highest-view zero-click page or the highest-click zero-revenue page.
5. Audit expired campaigns with `python scripts/check_expired_campaigns.py --report-only`.
6. Approve a new article only when it fills a measured search gap or supports a proven revenue page.
7. Keep active CTA experiments unchanged for 28 days or 100 pageviews unless a link is broken.
