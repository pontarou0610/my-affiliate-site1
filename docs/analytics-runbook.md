# Analytics Runbook

## Current Sources

- GA4 traffic and affiliate-click report: `python scripts/report_ga4.py --top 20`
- GA4 auth/config check without opening a browser: `python scripts/report_ga4.py --auth-status`
- OAuth refresh when the token is missing or revoked: `python scripts/report_ga4.py --force-auth`

The GA4 report reads `.env` values:

- `GA4_PROPERTY_ID`
- `GA4_OAUTH_CLIENT_FILE`
- `GA4_OAUTH_TOKEN_FILE`

If `--auth-status` reports `oauth_token_file: missing`, run `--force-auth` and approve the Google browser prompt. A successful run creates the token file locally.

## GA4 Custom Definitions

Register these event-scoped custom dimensions in GA4 so affiliate clicks can be analyzed by CTA placement:

| Custom dimension name | Event parameter | Use |
| --- | --- | --- |
| affiliate_store | `affiliate_store` | Amazon, Rakuten, Yahoo, or other store grouping |
| affiliate_slot | `affiliate_slot` | CTA placement such as hero, bottom, offerbox, related products |
| link_domain | `link_domain` | Destination domain sanity check |
| link_id | `link_id` | Stable low-cardinality link identifier for repeated CTA analysis |

Avoid reporting directly on `link_url` and `link_text` unless needed for debugging. They can produce too many unique values.

## Interpreting The Report

- Top pages with high views and zero affiliate clicks are CTA-improvement candidates.
- Pages with clicks but low traffic are SEO/internal-link candidates.
- `affiliate_slot` shows which CTA positions actually get clicked.
- `affiliate_store` shows whether Amazon, Rakuten, or Yahoo links are getting traction.

The report's opportunity list is based on the selected `--top` page count, not every page on the site. Increase `--top` when doing a broader audit.
