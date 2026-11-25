"""Smoke test for rag_search(): queries covering filters and edge cases. Run: uv run python -m rag.smoke_test"""
import sys

from contracts.tool_schemas import RagSearchInput
from rag.search import rag_search

CASES = [
    ("plain semantic", dict(query="wooden jigsaw puzzle for a 6 year old")),
    ("price range", dict(query="remote control car", min_price=10, max_price=40)),
    ("brand filter", dict(query="building set", brand="lego")),
    ("subcategory as category", dict(query="educational game", category="Puzzles", top_k=3)),
    ("rating filter (unsupported)", dict(query="stuffed animal", min_rating=4.5, top_k=3)),
    ("unknown brand -> empty", dict(query="toy", brand="NotABrand")),
    ("child age 2", dict(query="toy for my toddler", child_age_years=2, top_k=8)),
    ("blank query -> empty", dict(query="   ")),
    ("min_price above max_price -> empty", dict(query="toy", min_price=50, max_price=10)),
    ("exclude small parts", dict(query="building blocks for kids", exclude_features=["small parts", "choking"], top_k=8)),
]


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # product titles have non-ASCII chars; Windows defaults to cp1252
    failures = 0
    for name, kw in CASES:
        out = rag_search(RagSearchInput(**kw))
        print(f"\n[{name}] {kw}\n  filters_applied={out.filters_applied} took_ms={out.took_ms} n={len(out.results)}")
        for p in out.results:
            print(f"   {p.score:.2f} ${p.price} {p.brand} | {p.title[:50]} | age {p.min_age_years}-{p.max_age_years} | warn {p.safety_warnings}")
        if name == "price range":
            failures += any(p.price is None or not (10 <= p.price <= 40) for p in out.results)
        if name == "brand filter":
            failures += any(p.brand != "LEGO" for p in out.results) or not out.results
        if name == "child age 2":
            failures += any(p.min_age_years is not None and p.min_age_years > 2 for p in out.results)
        if name == "exclude small parts":
            failures += any(p.safety_warnings and ("small parts" in p.safety_warnings or "choking hazard" in p.safety_warnings) for p in out.results)
        if name.endswith("-> empty"):
            failures += bool(out.results) or not out.filters_applied  # empty AND explained
        if not name.endswith("-> empty") and not out.results:
            failures += 1
    print("\nFAILED" if failures else "\nOK: all checks passed", failures or "")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
