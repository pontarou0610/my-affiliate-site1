# Five-Expert Review: 白い転居届 Hugo掲載

## Scope

- Target: `content/fiction/_index.md`
- Product: `白い転居届: 父が住めなかった部屋には、誰も住んでいなかった`
- ASIN: `B0H6NSVW8H`
- Planned public URL: `https://pontarou0610.github.io/my-affiliate-site1/fiction/`

## Review

| Expert | Verdict | Evidence and decision |
|---|---|---|
| SEO editor | approved | The title, subtitle, and concise synopsis make the work discoverable within the existing fiction catalog without duplicating a long sales page. |
| Affiliate and conversion reviewer | approved | The Amazon URL uses the existing `naoto0610-22` tag and a distinct `fiction-featured-housing` measurement slot. |
| Legal and disclosure reviewer | approved | The page already discloses the author's own works and promotion links. The CTA keeps `nofollow sponsored noopener noreferrer`; no price or revenue claim is added. |
| UX and accessibility reviewer | approved | The card follows the existing featured-card pattern, has descriptive alt text, and keeps the image lazy-loaded. |
| Technical and analytics reviewer | approved | The exact ASIN product page was previously verified as HTTP 200. The existing Hugo GA4 click handler can receive the card's affiliate data attributes. |

## Publication Gate

All five reviewers approve the scoped addition. Before release, run the Hugo build and affiliate, JSON-LD, search-index, link, and test checks. After release, verify the public fiction page contains the title, ASIN, tagged Amazon link, and GA4 measurement ID.
