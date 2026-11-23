## Decision: web-search API behind `web.search`

**Status:** proposed, to confirm with test queries

**Decision: Serper.**

`web.search` only looks up live facts (price, availability, missing data) for products already found by `rag.search`. It never visits store pages.

Options compared (Google Custom Search and Bing Search API are excluded: closed or retired):

| API | 1. Cost | 2. Product data | 3. Compliance |
|-----|---------|-----------------|---------------|
| **Serper** | ✅ 2,500 free, no card | ✅ Price via `/shopping`, real URLs via `/search` | ✅ Named in the assignment; terms don't restrict caching |
| SerpApi | ⚠️ 250/month is tight | ✅ Numeric price + merchant link | ⚠️ Reported Google lawsuit |
| Brave | ⚠️ Card required | ⚠️ Prices not reliable | ⚠️ Terms only allow "transient" storage |
| Tavily | ✅ 1,000/month, no card | ❌ No structured price | ✅ |
| Exa | ✅ $10/month, no card | ❌ No structured price | ✅ |

Criteria:
1. **Cost:** the free tier must cover the project (about 1,000–2,000 searches) without a card, so every teammate can get a key.
2. **Product data:** for a known product, results must include a structured price and a real source URL to cite. This criterion separates the options most.
3. **Compliance:** an active API whose terms allow a 60–300 s cache and keeping source URLs.

Limitation: `/shopping` links point to Google, so live facts are cited with the `/search` URL.

Fallback: SerpApi (250 searches/month), if Serper's price data is insufficient.

Next step: run 20–30 real product queries against Serper and measure how often a price comes back.
