"""What text represents a product: the text that gets embedded, and the evidence snippet shown to the Answerer.

Both the index build and the tests use these functions, so the embedded text and the stored listing text cannot drift
apart. The recipe is chosen in config/retrieval.py (EMBED_TEXT); changing it means rebuilding the index.
"""
from __future__ import annotations


def _features(r) -> list[str]:
    return list(r["features"]) if r["features"] is not None else []


def _age_line(r) -> list[str]:
    return [f"Recommended age: {r['age_range']}"] if isinstance(r["age_range"], str) else []


def recipe_base(r) -> str:
    """title. all features. age"""
    return ". ".join([r["title"]] + ([" ".join(_features(r))] if _features(r) else []) + _age_line(r))


def recipe_brand_cat_first3(r) -> str:
    """title. brand. subcategory. first three feature bullets. age. Brand and category make 'a Melissa & Doug puzzle'
    findable; keeping only the first bullets keeps long marketing text from diluting the vector."""
    return ". ".join(
        [r["title"]]
        + ([f"Brand: {r['brand']}"] if isinstance(r["brand"], str) else [])
        + ([f"Category: {r['subcategory']}"] if isinstance(r["subcategory"], str) else [])
        + ([" ".join(_features(r)[:3])] if _features(r) else [])
        + _age_line(r)
    )


def recipe_brand_cat_all(r) -> str:
    """What the reranker reads: title. brand. subcategory. ALL features. age. The labels let it match 'a Melissa &
    Doug puzzle'; without them reranking made brand+category queries worse in the trials."""
    return ". ".join(
        [r["title"]]
        + ([f"Brand: {r['brand']}"] if isinstance(r["brand"], str) else [])
        + ([f"Category: {r['subcategory']}"] if isinstance(r["subcategory"], str) else [])
        + ([" ".join(_features(r))] if _features(r) else [])
        + _age_line(r)
    )


def passage_from_metadata(meta: dict) -> str:
    """recipe_brand_cat_all rebuilt from what the index stores (so search needs no access to the parquet)."""
    title = meta["title"]
    listing = meta.get("listing_text", title)
    features = listing[len(title) + 2:] if listing.startswith(title + ". ") else ""
    parts = [title]
    if meta.get("brand"):
        parts.append(f"Brand: {meta['brand']}")
    if meta.get("subcategory"):
        parts.append(f"Category: {meta['subcategory']}")
    if features:
        parts.append(features)
    if meta.get("age_range"):
        parts.append(f"Recommended age: {meta['age_range']}")
    return ". ".join(parts)


RECIPES = {"base": recipe_base, "brand_cat_first3": recipe_brand_cat_first3}


def embed_text(r, recipe: str) -> str:
    return RECIPES[recipe](r)


def listing_text(r) -> str:
    """Everything the listing itself says (title, all features), with no brand/category labels added by us.
    Used to decide whether a product mentions an excluded feature such as 'small parts'."""
    return ". ".join([r["title"]] + ([" ".join(_features(r))] if _features(r) else []))


def snippet(r, chars: int) -> str | None:
    """Short evidence excerpt: the features, then the stated age. A prefix of what the listing says."""
    parts = ([" ".join(_features(r))] if _features(r) else []) + _age_line(r)
    text = ". ".join(parts)
    if not text:
        return None
    return text if len(text) <= chars else text[:chars].rsplit(" ", 1)[0] + "..."
