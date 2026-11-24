"""Non-secret settings for web.search (the key SERPER_API_KEY lives in .env)."""

SERPER_URL = "https://google.serper.dev/search"
SERPER_TIMEOUT_S = 10.0
SERPER_NUM_RESULTS = 10  # up to 10 costs one Serper credit; we filter, then cut to max_results
PROVIDER_NAME = "serper"

# TTL cache (the assignment asks for 60-300 s).
CACHE_TTL_S = 300

# Rate limit on calls that reach Serper (cache hits are free): at most N calls per window.
RATE_LIMIT_CALLS = 10
RATE_LIMIT_WINDOW_S = 60

# Only results from these domains (and their subdomains) are returned.
ALLOWED_DOMAINS = (
    "amazon.com",
    "walmart.com",
    "target.com",
    "bestbuy.com",
    "ebay.com",
    "lego.com",
    "toysrus.com",
    "barnesandnoble.com",
    "costco.com",
    "kohls.com",
    "mattel.com",
    "hasbro.com",
    "fisher-price.com",
)
