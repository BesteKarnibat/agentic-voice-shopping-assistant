"""Preprocess the Amazon Product Dataset 2020 (Toys & Games slice) into products.parquet.

    uv run doit preprocess          # preferred
    uv run python -m rag.preprocess [raw_csv]

Outputs (paths in config/paths.py): PRODUCTS_PARQUET (full slice) and PRODUCTS_SAMPLE_JSON (~100 products).
rating and ingredients are always None: the raw file has neither.
"""
import re
import sys
from pathlib import Path

import pandas as pd

from config.paths import KAGGLE_CSV, PRODUCTS_PARQUET, PRODUCTS_SAMPLE_JSON

SLICE = "Toys & Games"
PRICE_RE = re.compile(r"\$\s?(\d[\d,]*\.\d\d)")
ASIN_RE = re.compile(r"/dp/([A-Z0-9]{10})")
BOILERPLATE = ("make sure this fits",)


def parse_price(raw):
    """Return (price, is_range). Price is the lowest dollar amount, or None."""
    if not isinstance(raw, str):
        return None, False
    vals = [float(m.replace(",", "")) for m in PRICE_RE.findall(raw)]
    if not vals:
        return None, False
    is_range = bool(re.search(r"\$[\d.,]+\s*-\s*\$[\d.,]+", raw))
    return (min(vals) if is_range else vals[0]), is_range


def spec_field(spec, key):
    if not isinstance(spec, str):
        return None
    m = re.search(rf"(?:^|\|){key}:([^|]*)", spec)
    return m.group(1).strip() if m else None


def unsquash(s):
    """'AnagramInternational' -> 'Anagram International' (spec text has spaces removed)."""
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)


# Known multi-word brands, curated from the most common title prefixes in this catalog.
# Matching is on a normalized title prefix (lowercase, hyphens/quotes -> space).
BRAND_ALIASES = [
    "Melissa & Doug", "Aurora World", "Learning Resources", "Redcat Racing", "Wild Republic", "Hot Wheels",
    "Forum Novelties", "Trends International", "Manhattan Toy", "Buffalo Games", "Great Eastern",
    "Mega Construx", "Privateer Press", "Constructive Playthings", "Educational Insights",
    "Rhode Island Novelty", "Diamond Select", "Creativity for Kids", "Mary Meyer", "White Mountain",
    "Kids Preferred", "Green Toys", "Carson Dellosa", "Ultimate Guard", "Gorilla Playsets",
    "Fantasy Flight", "Ultra Pro", "Hey! Play!", "Stephen Joseph", "Junior Learning", "Glitter Girls",
    "3B Scientific", "Trend Enterprises", "Just Play", "JC Toys", "Bright Starts", "B. Toys",
    "Q Workshop", "McFarlane Toys", "Tamashii Nations", "Pillow Pets", "Jada Toys", "Hampton Nautical",
    "Crocodile Creek", "Badger Basket", "Thames & Kosmos", "Stages Learning", "Royal Brush",
    "Petit Collage", "California Costumes", "Horizon Group", "Fashion Angels", "Ginger Ray",
    "Little Tikes", "Fisher-Price", "Small Foot", "Sago Mini", "American Educational",
    "The Puppet Company", "The Learning Journey", "Baby Alive", "Cuddle Pal", "Click N' Play",
    "Springbok Puzzles", "Bepuzzled", "Watchover Voodoo", "Good Smile", "Pacific Play Tents",
]
# First words that are descriptions, not brands. With no alias and no manufacturer field the
# brand is unknown (None) rather than a wrong guess like "Remote" from "Remote Control Truck".
GENERIC_FIRST_WORDS = {
    "remote", "wooden", "wood", "plush", "toy", "toys", "kids", "kid", "children", "childrens", "large",
    "big", "small", "new", "set", "mini", "3d", "puzzle", "puzzles", "swing", "party", "halloween",
    "christmas", "stuffed", "magnetic", "giant", "jumbo", "baby", "educational", "costume", "little",
    "first", "just", "green", "white", "world", "in", "my", "your", "our", "super", "classic", "deluxe",
    "wild", "great", "play", "learning", "creative", "fun", "happy", "rc", "mighty", "ultimate",
}


def _norm(text):
    return re.sub(r"\s+", " ", re.sub(r"[-\"'’]", " ", text.lower())).strip()


_ALIASES_NORM = sorted(((_norm(a), a) for a in BRAND_ALIASES), key=lambda x: -len(x[0]))


def parse_brand(spec, title):
    """Return (brand, source). source: manufacturer_field | alias | title_first_word | unknown."""
    m = spec_field(spec, "Manufacturer")
    if m:
        return unsquash(m), "manufacturer_field"
    if not isinstance(title, str) or not title.split():
        return None, "unknown"
    nt = _norm(title)
    for key, brand in _ALIASES_NORM:
        if nt == key or nt.startswith(key + " "):
            return brand, "alias"
    words = [w.strip(",:-") for w in title.split()]
    words = [w for w in words if w]
    if words[0].lower() in ("the", "a", "an") and len(words) > 1:
        words = words[1:]
    if words[0].lower() in GENERIC_FIRST_WORDS:
        return None, "unknown"
    return words[0], "title_first_word"


def parse_age(spec):
    a = spec_field(spec, "Manufacturerrecommendedage")
    if not a:
        return None
    a = re.sub(r"(?<=\d)(?=[A-Za-z])", " ", a)
    a = re.sub(r"(?<=[a-z])and(?=up)", " and ", a)
    a = re.sub(r"\band(?=up)", "and ", a)
    return re.sub(r"\s+", " ", a).strip()


def _to_years(value, unit):
    v = float(value)
    return round(v / 12, 2) if unit.lower().startswith("month") else v


def age_bounds(age_range, text):
    """Return (min_age_years, max_age_years, source).

    1) structured field, e.g. '14 years and up', '4-12 years', '36 months-15 years'
    2) fallback: 'Ages 6+' / 'ages 3-5' / 'ages 3 and up' in the listing text
    None means not stated (never 0, never 'any age').
    """
    if isinstance(age_range, str):
        m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(months?|years?)?\s*-\s*(\d+(?:\.\d+)?)\s*(months?|years?)", age_range)
        if m:
            lo_unit = m.group(2) or m.group(4)  # '4-12 years' -> both years
            lo, hi = _to_years(m.group(1), lo_unit), _to_years(m.group(3), m.group(4))
            if hi < lo:  # corrupt source like '14-1 years': keep the minimum, drop the unreliable max
                hi = None
            return lo, hi, "structured"
        m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(months?|years?)\s*and up", age_range)
        if m:
            return _to_years(m.group(1), m.group(2)), None, "structured"
    if isinstance(text, str):
        m = re.search(r"\bages?:?\s*(\d{1,2})\s*(?:-|to)\s*(\d{1,2})\s*(months?|years?|yrs?)?", text, re.I)
        if m and int(m.group(1)) <= int(m.group(2)):
            unit = m.group(3) or "years"
            return _to_years(m.group(1), unit), _to_years(m.group(2), unit), "text"
        m = re.search(r"\bages?:?\s*(\d{1,2})\s*(months?|years?|yrs?)?\s*(?:\+|(?:and|&)\s*up)", text, re.I)
        if m:
            return _to_years(m.group(1), m.group(2) or "years"), None, "text"
    return None, None, None


# label -> regex. Searched in title + About Product + Technical Details only
# (Product Specification is excluded: it holds a Prop 65 boilerplate link, not a toy warning).
WARNING_PATTERNS = [
    ("choking hazard", re.compile(r"chok(?:e|ing)\s+hazard|choking", re.I)),
    ("small parts", re.compile(r"small\s+parts?", re.I)),
    ("small balls", re.compile(r"small\s+balls?", re.I)),
    ("button battery hazard", re.compile(r"(?:button|coin)[\s-]*(?:cell\s+)?batter", re.I)),
    ("magnets: swallowing hazard", re.compile(r"magnets?\W+(?:\w+\W+){0,12}(?:swallow|ingest|hazard)|(?:swallow|ingest|hazard)\W+(?:\w+\W+){0,12}magnets?", re.I)),
    ("suffocation hazard", re.compile(r"suffocat", re.I)),
    ("sharp points or edges", re.compile(r"sharp\s+(?:points?|edges?)", re.I)),
]
UNDER_RE = re.compile(r"not\s+(?:suitable|recommended|intended)?\s*for\s+(?:children|kids|ages)\s+under\s+(\d+)\s*(months?|years?)?", re.I)


def parse_warnings(text):
    """List of normalized warning labels found in the listing text, or None if none found.
    None means 'not stated in the listing', never 'safe'."""
    if not isinstance(text, str):
        return None
    found = [label for label, rx in WARNING_PATTERNS if rx.search(text)]
    m = UNDER_RE.search(text)
    if m:
        unit = "months" if (m.group(2) or "").lower().startswith("month") else "years"
        found.append(f"not for children under {m.group(1)} {unit}")
    return found or None


def parse_features(about):
    if not isinstance(about, str):
        return []
    parts = [p.strip() for p in about.split("|")]
    return [p for p in parts if p and not p.lower().startswith(BOILERPLATE)]


def main(raw_csv=KAGGLE_CSV, parquet_path=PRODUCTS_PARQUET, sample_path=PRODUCTS_SAMPLE_JSON):
    df = pd.read_csv(raw_csv)
    df = df[df["Category"].astype(str).str.startswith(SLICE)].copy()
    cats = df["Category"].astype(str).str.split("|").apply(lambda p: [x.strip() for x in p])

    prices = df["Selling Price"].apply(parse_price)
    age_ranges = df["Product Specification"].apply(parse_age)
    age_text = df[["Product Name", "About Product", "Technical Details"]].fillna("").agg(" ".join, axis=1)
    bounds = [age_bounds(a, t) for a, t in zip(age_ranges, age_text)]
    warnings = age_text.apply(parse_warnings)
    brands = df.apply(lambda r: parse_brand(r["Product Specification"], r["Product Name"]), axis=1)

    out = pd.DataFrame({
        "doc_id": df["Uniq Id"],
        "sku": df["Product Url"].str.extract(ASIN_RE)[0],
        "title": df["Product Name"].str.strip(),
        "brand": brands.str[0],
        "brand_source": brands.str[1],
        "category": cats.str[0],
        "subcategory": cats.str[1],
        "price": prices.str[0],
        "price_is_range": prices.str[1],
        "rating": None,
        "features": df["About Product"].apply(parse_features),
        "ingredients": None,
        "age_range": age_ranges,
        "min_age_years": [b[0] for b in bounds],
        "max_age_years": [b[1] for b in bounds],
        "age_source": [b[2] for b in bounds],
        "safety_warnings": warnings,
        "product_url": df["Product Url"],
    }).reset_index(drop=True)

    # one canonical casing per brand (amscan/Amscan -> most common form)
    low = out["brand"].str.lower()
    canon = out.groupby(low)["brand"].agg(lambda x: x.value_counts().index[0])
    out["brand"] = low.map(canon)
    out["rating"] = out["rating"].astype("float64")  # all NaN, numeric dtype
    out["ingredients"] = out["ingredients"].astype("object")
    # features: empty list means unknown, keep None as the issue asks
    out["features"] = out["features"].apply(lambda f: f if f else None)

    Path(parquet_path).parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(parquet_path, index=False)

    # ~100-product sample, spread across subcategories, fixed seed, only rows with a price
    pool = out[out["price"].notna()]
    n_sub = pool["subcategory"].nunique()
    per = max(1, 100 // max(n_sub, 1))
    sample = (pool.groupby("subcategory", group_keys=False)
              .apply(lambda g: g.sample(min(len(g), per), random_state=42)))
    if len(sample) < 100:
        rest = pool.drop(sample.index).sample(100 - len(sample), random_state=42)
        sample = pd.concat([sample, rest])
    sample.head(100).to_json(sample_path, orient="records", indent=2)

    print(f"rows: {len(out)}")
    print("null rate:\n", out.isna().mean().round(3).to_string())
    print("brand_source:\n", out["brand_source"].value_counts().to_string())
    print("age_source:\n", out["age_source"].value_counts(dropna=False).to_string())
    print("with warnings:", int(out["safety_warnings"].notna().sum()))
    print("doc_id unique:", out["doc_id"].is_unique, "| sample rows:", min(100, len(sample)))


if __name__ == "__main__":
    main(*(sys.argv[1:2] or [KAGGLE_CSV]))
