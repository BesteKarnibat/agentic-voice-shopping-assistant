## Decision: web-search API behind `web.search`

**Status:** proposed, to confirm with test queries

### 1. What web search is for

Web search only gathers information about a product we already know: its current price, availability, and any fact the catalog is missing. It is not used to discover new products. Product discovery comes from the private catalog (`rag.search`).

`web.search` returns only what the search API provides (title, URL, snippet, and price/availability when present). It never visits store pages.

### 2. Options

| API | Type | Free tier | Card needed | Structured price | Status |
|-----|------|-----------|-------------|------------------|--------|
| **Serper** | Google results (web + Shopping) | 2,500 searches, one-time | No | Yes (`/shopping`) | Active |
| **SerpApi** | Google results (web + Shopping) | 250 searches/month | No | Yes (`extracted_price`) | Active; reportedly sued by Google (Dec 2025) |
| **Brave Search** | Own independent index | $5 credit/month (~1,000) | Yes | Partial, not reliable | Active |
| **Tavily** | AI-agent search (cleaned page text) | 1,000 credits/month | No | No | Active |
| **Exa** | AI-agent semantic search | $10 credit/month | No | No | Active |
| Google Custom Search | Google results | — | — | — | Closed to new customers; shuts down Jan 1, 2027 |
| Bing Search API | Bing results | — | — | — | Retired Aug 11, 2025 |

### 3. Criteria

1. **Cost.** The free tier must cover the whole project (estimated at 1,000–2,000 searches) without a credit card, so every teammate can get a key.
2. **Product data.** For a known product, results must include a structured price and a real source URL to cite. This criterion separates the APIs most: Google Shopping-based APIs return prices, AI-agent search APIs return text.
3. **Assignment compliance.** A legitimate, active API whose terms allow what the assignment requires: a 60–300 s cache and keeping source URLs.

| API | 1. Cost | 2. Product data | 3. Compliance |
|-----|---------|-----------------|---------------|
| **Serper** | ✅ 2,500 free, no card | ✅ Price via `/shopping`, real URLs via `/search` | ✅ Named in the assignment; terms don't restrict caching |
| SerpApi | ⚠️ 250/month is tight | ✅ Numeric price + merchant link | ⚠️ Reported Google lawsuit |
| Brave | ⚠️ Card required | ⚠️ Prices not reliable | ⚠️ Terms only allow "transient" storage |
| Tavily | ✅ 1,000/month, no card | ❌ No structured price | ✅ |
| Exa | ✅ $10/month, no card | ❌ No structured price | ✅ |

### 4. Decision

**Serper.** It is the only option that passes all three criteria.

- `/shopping` gives the price. `/search` gives the citable retailer URL.
- Known limitation: `/shopping` links point to Google, not the store. Live facts are cited with the `/search` URL.
- **Fallback:** SerpApi, if test queries show Serper's price data is insufficient.

**Next step:** run 20–30 real product queries against Serper to measure how often a price comes back.

<details>
<summary>Sources (checked 2026-11-20, mostly third-party summaries; confirm on official pages)</summary>

- [Serper](https://serper.dev/) · [Serper pricing](https://websearchapi.space/blog/serper-pricing) · [Serper terms](https://serper.dev/terms)
- [SerpApi pricing](https://serpapi.com/pricing) · [SerpApi Google Shopping results](https://serpapi.com/shopping-results)
- [Brave Search API pricing](https://api-dashboard.search.brave.com/documentation/pricing) · [Brave terms](https://api-dashboard.search.brave.com/terms-of-service)
- [Tavily credits & pricing](https://docs.tavily.com/documentation/api-credits)
- [Exa pricing](https://exa.ai/docs/admin/pricing)
- [Google Custom Search shutdown](https://www.firecrawl.dev/blog/google-search-json-api-alternative) · [Bing Search API retirement](https://cloro.dev/blog/google-custom-search-api-shutdown/)

</details>
