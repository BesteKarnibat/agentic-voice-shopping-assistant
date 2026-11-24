"""Behaviour tests for the Chroma index and rag_search().

    uv run python -m unittest rag.test_search -v      (needs `uv run doit preprocess index` first; skips otherwise)

Model-agnostic: nothing here depends on which embedding model is configured, only on what rag_search() promises.
Filter tests are property-style: draw random filter combinations from real catalog values, and check that every
returned product obeys every filter, using the parquet as ground truth.
"""
import json
import random
import subprocess
import sys
import tempfile
import threading
import unittest

import pandas as pd

from config import retrieval
from config.paths import CHROMA_DIR, PRODUCTS_PARQUET
from contracts.tool_schemas import RagProduct, RagSearchInput, RagSearchOutput

READY = PRODUCTS_PARQUET.exists() and (CHROMA_DIR / "chroma.sqlite3").exists()
need_index = unittest.skipUnless(READY, "run `uv run doit preprocess index` first")

QUERIES = ["wooden puzzle for a toddler", "remote control car", "stuffed animal", "building blocks", "board game for the family",
           "birthday party decorations", "action figure", "art supplies for kids", "doll with accessories", "science kit",
           "jigsaw puzzle 500 pieces", "baby rattle", "costume for halloween", "card game", "plush dinosaur"]
FEATURE_TERMS = ["small parts", "batteries", "choking", "magnets", "balloons"]


def search(**kw):
    from rag.search import rag_search
    return rag_search(RagSearchInput(**kw))


def broken_filters(df, ids, f):
    """doc_ids among `ids` that violate the filters in `f` (RagSearchInput kwargs)."""
    from rag.search import _key, _phrase
    bad = []
    for i in ids:
        r = df.loc[i]
        ok = True
        if f.get("max_price") is not None:
            ok &= pd.notna(r.price) and r.price <= f["max_price"]
        if f.get("min_price") is not None:
            ok &= pd.notna(r.price) and r.price >= f["min_price"]
        if f.get("brand"):
            ok &= isinstance(r.brand, str) and _key(r.brand) == _key(f["brand"])
        if f.get("subcategory"):
            ok &= r.subcategory == f["subcategory"]
        if f.get("child_age_years") is not None:  # unknown age passes, a stated higher age does not
            ok &= pd.isna(r.min_age_years) or r.min_age_years <= f["child_age_years"]
        text = _phrase(" ".join([r.title] + (list(r.features) if r.features is not None else [])
                                + (list(r.safety_warnings) if r.safety_warnings is not None else [])))
        for term in f.get("exclude_features", []):
            ok &= _phrase(term) not in text
        if not ok:
            bad.append(i)
    return bad


@need_index
class IndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import chromadb
        cls.df = pd.read_parquet(PRODUCTS_PARQUET)
        cls.col = chromadb.PersistentClient(path=str(CHROMA_DIR)).get_collection(retrieval.COLLECTION_NAME)

    def test_every_product_is_indexed_exactly_once(self):
        got = self.col.get(include=[])["ids"]
        self.assertEqual(len(got), len(self.df))
        self.assertEqual(set(got), set(self.df.doc_id))

    def test_index_was_built_with_the_configured_model(self):
        self.assertEqual(self.col.metadata.get("embedding_model"), retrieval.EMBEDDING_MODEL,
                         "index and query models differ: rebuild with `uv run doit clean index index`")

    def test_stored_metadata_matches_the_parquet(self):
        sample = self.df.sample(150, random_state=1)
        got = self.col.get(ids=sample.doc_id.tolist(), include=["metadatas"])
        by_id = dict(zip(got["ids"], got["metadatas"]))
        for _, r in sample.iterrows():
            m = by_id[r.doc_id]
            self.assertEqual(m["title"], r.title)
            self.assertEqual(m.get("brand"), r.brand if isinstance(r.brand, str) else None)
            self.assertEqual(m.get("price"), None if pd.isna(r.price) else float(r.price))
            self.assertEqual(m["age_known"], bool(pd.notna(r.min_age_years)))
            self.assertEqual(m.get("min_age_years"), None if pd.isna(r.min_age_years) else float(r.min_age_years))
            self.assertEqual(m.get("safety_warnings"), " | ".join(r.safety_warnings) if r.safety_warnings is not None else None)
            self.assertNotIn(None, m.values())  # Chroma rejects None: unknowns are omitted instead


@need_index
class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = pd.read_parquet(PRODUCTS_PARQUET).set_index("doc_id")

    def test_output_validates_and_survives_json(self):
        out = search(query="wooden puzzle", top_k=5)
        self.assertIsInstance(out, RagSearchOutput)
        again = RagSearchOutput.model_validate(json.loads(json.dumps(out.model_dump())))
        self.assertEqual(again, out)

    def test_results_are_ranked_unique_and_bounded(self):
        for q in QUERIES:
            for k in (1, 5, 20):
                out = search(query=q, top_k=k)
                ids = [p.doc_id for p in out.results]
                self.assertEqual(len(ids), k, (q, k))
                self.assertEqual(len(set(ids)), k)
                scores = [p.score for p in out.results]
                self.assertEqual(scores, sorted(scores, reverse=True), "score is not non-increasing")
                self.assertTrue(set(ids) <= set(self.df.index))

    def test_every_returned_field_matches_the_catalog(self):
        for q in QUERIES[:6]:
            for p in search(query=q, top_k=10).results:
                r = self.df.loc[p.doc_id]
                self.assertEqual(p.title, r.title)
                self.assertEqual(p.sku, r.sku)
                self.assertEqual(p.brand, r.brand if isinstance(r.brand, str) else None)
                self.assertEqual(p.category, r.category)
                self.assertEqual(p.price, None if pd.isna(r.price) else float(r.price))
                self.assertEqual(p.min_age_years, None if pd.isna(r.min_age_years) else float(r.min_age_years))
                self.assertEqual(p.max_age_years, None if pd.isna(r.max_age_years) else float(r.max_age_years))
                self.assertEqual(p.safety_warnings, list(r.safety_warnings) if r.safety_warnings is not None else None)
                self.assertIsNone(p.rating)  # the dataset has none; never invent one

    def test_snippet_is_short_and_grounded_in_the_listing(self):
        """The snippet is evidence for the Answerer, so it must be a prefix of what the listing says."""
        shown = 0
        for q in ["plush toy", "wooden puzzle", "board game", "remote control car", "party supplies"]:
            for p in search(query=q, top_k=10).results:
                if p.features_snippet is None:
                    continue
                row = self.df.loc[p.doc_id]
                parts = [" ".join(row.features)] if row.features is not None else []
                if isinstance(row.age_range, str):
                    parts.append(f"Recommended age: {row.age_range}")
                listing = ". ".join(parts)
                core = p.features_snippet[:-3] if p.features_snippet.endswith("...") else p.features_snippet
                self.assertLessEqual(len(p.features_snippet), retrieval.SNIPPET_CHARS + 3)
                self.assertTrue(listing.startswith(core.strip()), f"not grounded: {p.features_snippet!r} vs {listing[:80]!r}")
                shown += 1
        self.assertGreater(shown, 20)

    def test_same_input_gives_the_same_output(self):
        a = search(query="remote control car", top_k=10, max_price=40)
        b = search(query="remote control car", top_k=10, max_price=40)
        self.assertEqual([(p.doc_id, p.score) for p in a.results], [(p.doc_id, p.score) for p in b.results])

    def test_model_dump_fits_the_agent_state(self):
        state = {"rag_results": [p.model_dump() for p in search(query="board game", top_k=5).results]}
        json.dumps(state)  # AgentState must stay JSON-serializable
        for row in state["rag_results"]:
            self.assertEqual(set(row), set(RagProduct.model_fields))


@need_index
class FilterPropertyTests(unittest.TestCase):
    """Random filter combinations drawn from real catalog values: nothing returned may break a filter."""

    @classmethod
    def setUpClass(cls):
        cls.df = pd.read_parquet(PRODUCTS_PARQUET).set_index("doc_id")
        cls.brands = [b for b, n in cls.df.brand.value_counts().items() if n >= 15 and isinstance(b, str)]
        cls.subs = sorted(cls.df.subcategory.unique())

    def draw(self, rng):
        f = {}
        if rng.random() < 0.5:
            lo = rng.choice([0, 5, 10, 20]); f["min_price"] = float(lo)
            if rng.random() < 0.7:
                f["max_price"] = float(lo + rng.choice([5, 15, 40, 100]))
        if rng.random() < 0.3:
            f["brand"] = rng.choice(self.brands)
        if rng.random() < 0.3:
            f["category"] = rng.choice(self.subs)
        if rng.random() < 0.5:
            f["child_age_years"] = float(rng.choice([0.5, 1, 2, 3, 5, 8, 12, 16]))
        if rng.random() < 0.4:
            f["exclude_features"] = rng.sample(FEATURE_TERMS, rng.choice([1, 2]))
        return f

    def test_300_random_filter_combinations(self):
        rng = random.Random(2026)
        checked = nonempty = 0
        for n in range(300):
            f = self.draw(rng)
            out = search(query=rng.choice(QUERIES), top_k=rng.choice([3, 5, 10]), **f)
            check = dict(f)
            if "category" in check:
                check["subcategory"] = check.pop("category")
            ids = [p.doc_id for p in out.results]
            self.assertEqual(broken_filters(self.df, ids, check), [], f"case {n}: {f}")
            checked += 1
            nonempty += bool(ids)
        self.assertGreater(nonempty, 150, "filters should rarely empty the result")
        self.assertEqual(checked, 300)

    def test_age_filter_keeps_products_that_state_no_age(self):
        seen_unknown = 0
        for q in QUERIES:
            for p in search(query=q, top_k=20, child_age_years=8).results:
                self.assertTrue(p.min_age_years is None or p.min_age_years <= 8)
                seen_unknown += p.min_age_years is None
        self.assertGreater(seen_unknown, 0, "products with no stated age must not be dropped")

    def test_filters_are_reported_back(self):
        out = search(query="toy", max_price=20, child_age_years=4, exclude_features=["small parts"])
        self.assertEqual(out.filters_applied["max_price"], 20.0)
        self.assertEqual(out.filters_applied["child_age_years"], 4.0)
        self.assertEqual(out.filters_applied["exclude_features"], ["small parts"])


@need_index
class RouterWordingTests(unittest.TestCase):
    """The Router writes free text. rag_search() must cope with it instead of returning nothing."""

    def test_free_text_categories_resolve_to_the_right_subcategory(self):
        expect = {"puzzle": "Puzzles", "board games": "Games & Accessories", "stuffed animals": "Stuffed Animals & Plush Toys",
                  "costumes": "Dress Up & Pretend Play", "lego": "Building Toys", "action figures": "Toy Figures & Playsets",
                  "cars": "Play Vehicles", "dolls": "Dolls & Accessories", "toddler toys": "Baby & Toddler Toys",
                  "arts and crafts": "Arts & Crafts", "party": "Party Supplies", "educational toys": "Learning & Education"}
        for said, sub in expect.items():
            out = search(query="something nice", top_k=5, category=said)
            self.assertEqual({p.category for p in out.results}, {"Toys & Games"})
            self.assertIn(sub, str(out.filters_applied.get("subcategory")), said)
            self.assertTrue(out.results, said)

    def test_the_whole_catalog_category_is_accepted(self):
        for said in ["Toys & Games", "toys", "Toys"]:
            out = search(query="puzzle", top_k=5, category=said)
            self.assertTrue(out.results)
            self.assertIn("Toys & Games", str(out.filters_applied.get("category")))

    def test_unknown_category_is_not_applied_and_says_so(self):
        out = search(query="wooden puzzle", top_k=5, category="xyzzy")
        self.assertTrue(out.results, "an unmatched category must not empty the search")
        self.assertIn("not applied", out.filters_applied["category"])

    def test_brand_spelling_variants_resolve(self):
        for said, real in {"lego": "LEGO", "Fisher Price": "Fisher-Price", "melissa and doug": "Melissa & Doug",
                           "hot wheel": "Hot Wheels", "Fisher Price Little People": "Fisher-Price"}.items():
            out = search(query="toy", top_k=5, brand=said)
            self.assertTrue(out.results, said)
            self.assertEqual({p.brand for p in out.results}, {real}, said)

    def test_unknown_brand_returns_nothing_and_explains(self):
        out = search(query="toy", brand="NotARealBrand")
        self.assertEqual(out.results, [])
        self.assertIn("no such brand", out.filters_applied["brand"])

    def test_exclude_features_matches_plural_and_singular(self):
        df = pd.read_parquet(PRODUCTS_PARQUET)
        has_battery = df[df.features.map(lambda f: f is not None and any("battery" in x.lower() or "batteries" in x.lower() for x in f))]
        self.assertGreater(len(has_battery), 50)
        out = search(query="electronic toy that lights up", top_k=20, exclude_features=["batteries"])
        banned = set(has_battery.doc_id)
        self.assertEqual([p.doc_id for p in out.results if p.doc_id in banned], [])

    def test_planner_style_filters_with_none_values_are_accepted(self):
        filters = {"category": "board games", "min_price": None, "max_price": 30, "brand": None, "child_age_years": 6,
                   "exclude_features": ["small parts"], "min_rating": None}
        out = search(query="cooperative game for the family", top_k=5, **filters)
        self.assertTrue(out.results)
        self.assertTrue(all(p.price is not None and p.price <= 30 for p in out.results))

    def test_unsupported_rating_filter_is_reported_not_applied(self):
        out = search(query="stuffed animal", top_k=5, min_rating=4.5)
        self.assertTrue(out.results)
        self.assertIn("not applied", out.filters_applied["min_rating"])


@need_index
class EdgeCaseTests(unittest.TestCase):
    def test_empty_results_always_carry_a_reason(self):
        cases = [dict(query="toy", brand="NotARealBrand"), dict(query="   "), dict(query="toy", min_price=50, max_price=10)]
        for kw in cases:
            out = search(**kw)
            self.assertEqual(out.results, [], kw)
            self.assertTrue(out.filters_applied, f"empty result without a reason: {kw}")

    def test_odd_queries_never_crash(self):
        odd = ['"puzzle" & <b>blocks</b>; DROP TABLE -- \' OR 1=1', "恐龙玩具 🦖 jouet pour enfant", "a", "the and for with",
               "wooden puzzle " * 400, "\n\t", "%%%", "C++", "100% cotton", "x" * 5000]
        for q in odd:
            out = search(query=q, top_k=5)
            self.assertIsInstance(out, RagSearchOutput)
            self.assertLessEqual(len(out.results), 5)

    def test_contract_still_rejects_bad_input(self):
        from pydantic import ValidationError
        for kw in [dict(query=""), dict(query="x", top_k=0), dict(query="x", top_k=21), dict(query="x", child_age_years=-1),
                   dict(query="x", min_price=-5)]:
            with self.assertRaises(ValidationError):
                RagSearchInput(**kw)

    def test_filter_that_matches_nothing_returns_empty_not_an_error(self):
        out = search(query="toy", max_price=0.0)
        self.assertEqual(out.results, [])

    def test_excluding_a_word_from_a_result_removes_that_product(self):
        base = search(query="wooden puzzle for a toddler", top_k=10)
        top = base.results[0]
        word = next(w for w in top.title.split() if w.isalpha() and len(w) > 4)
        after = search(query="wooden puzzle for a toddler", top_k=10, exclude_features=[word])
        self.assertNotIn(top.doc_id, [p.doc_id for p in after.results], f"excluded word: {word!r}")
        self.assertEqual(len(after.results), 10, "a full top_k must still come back")

    def test_excluding_a_term_that_matches_nothing_changes_nothing(self):
        a = search(query="remote control car", top_k=10)
        b = search(query="remote control car", top_k=10, exclude_features=["zzzqqq nonsense"])
        self.assertEqual([p.doc_id for p in a.results], [p.doc_id for p in b.results])

    def test_blank_exclusion_terms_are_ignored(self):
        a = search(query="remote control car", top_k=5)
        b = search(query="remote control car", top_k=5, exclude_features=["", "   "])
        self.assertEqual([p.doc_id for p in a.results], [p.doc_id for p in b.results])

    def test_concurrent_calls_agree_with_sequential_ones(self):
        expected = {q: [p.doc_id for p in search(query=q, top_k=5, max_price=60).results] for q in QUERIES[:8]}
        got, errors = {}, []

        def work(q):
            try:
                got[q] = [p.doc_id for p in search(query=q, top_k=5, max_price=60).results]
            except Exception as e:  # noqa: BLE001
                errors.append(repr(e))

        threads = [threading.Thread(target=work, args=(q,)) for q in expected for _ in range(2)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(errors, [])
        self.assertEqual(got, expected)

    def test_a_search_is_fast_once_loaded(self):
        search(query="warm up")
        import time
        times = []
        for q in QUERIES:
            t0 = time.perf_counter(); search(query=q, top_k=5, max_price=50); times.append(time.perf_counter() - t0)
        times.sort()
        self.assertLess(times[int(0.9 * len(times))], 0.5, "p90 latency above 500 ms")


@need_index
@unittest.skipUnless(retrieval.RERANKER_MODEL, "the relevance score needs the reranker")
class NotFoundSignalTests(unittest.TestCase):
    """`score` is the reranker's relevance probability. For SPECIFIC requests it separates real products from ones the
    catalog does not carry, but it is only a hint: vague legitimate requests ("a gift for my niece") also score near 0,
    so by default rag_search() never turns a low score into an empty result (NOT_FOUND_SCORE is None)."""
    NOT_IN_CATALOG = ["PlayStation 5 console", "iPhone 15 Pro case", "laptop charger USB-C", "diamond engagement ring",
                      "organic dog food", "kitchen knife set", "men's running shoes size 10", "car engine oil 5W-30",
                      "Samsung 55 inch TV", "protein powder chocolate", "wireless noise cancelling headphones", "winter jacket for men"]
    IN_CATALOG = ["wooden puzzle for a toddler", "remote control car", "stuffed animal", "building blocks", "board game for the family",
                  "baby rattle", "plush dinosaur", "card game", "doll with accessories", "birthday party decorations"]
    VAGUE_BUT_LEGITIMATE = ["a gift for my five year old niece", "an activity for a rainy day", "a gift under twenty dollars for a kid",
                            "something to calm an anxious child", "what do you recommend for a three year old"]

    def test_specific_out_of_catalog_requests_score_low(self):
        for q in self.NOT_IN_CATALOG:
            self.assertLess(search(query=q, top_k=1).results[0].score, 0.2, q)

    def test_specific_real_requests_score_high(self):
        for q in self.IN_CATALOG:
            self.assertGreater(search(query=q, top_k=1).results[0].score, 0.5, q)

    def test_scores_are_probabilities(self):
        for p in search(query="plush toy", top_k=10).results:
            self.assertTrue(0.0 <= p.score <= 1.0)

    def test_the_cutoff_is_off_by_default(self):
        self.assertIsNone(retrieval.NOT_FOUND_SCORE, "enabling it wrongly rejects about 1 in 4 vague requests")

    def test_vague_but_legitimate_requests_still_return_products_by_default(self):
        for q in self.VAGUE_BUT_LEGITIMATE:
            out = search(query=q, top_k=5)
            self.assertEqual(len(out.results), 5, q)
            self.assertNotIn("relevance", out.filters_applied)

    def test_the_optional_cutoff_returns_empty_with_a_reason(self):
        before = retrieval.NOT_FOUND_SCORE
        retrieval.NOT_FOUND_SCORE = 0.2
        try:
            gone = search(query="PlayStation 5 console", top_k=5)
            kept = search(query="wooden puzzle for a toddler", top_k=5)
        finally:
            retrieval.NOT_FOUND_SCORE = before
        self.assertEqual(gone.results, [])
        self.assertIn("nothing relevant", gone.filters_applied["relevance"])
        self.assertEqual(len(kept.results), 5)
        self.assertNotIn("relevance", kept.filters_applied)


@need_index
class ImportFromAnywhereTests(unittest.TestCase):
    def test_module_imports_and_runs_from_another_directory(self):
        """The MCP server and Streamlit run from other working directories: no relative paths allowed."""
        code = ("from rag.search import rag_search; from contracts.tool_schemas import RagSearchInput; "
                "o = rag_search(RagSearchInput(query='puzzle', top_k=2)); print(len(o.results))")
        with tempfile.TemporaryDirectory() as tmp:
            r = subprocess.run([sys.executable, "-c", code], cwd=tmp, capture_output=True, text=True, timeout=300)
        self.assertEqual(r.returncode, 0, r.stderr[-800:])
        self.assertEqual(r.stdout.strip().splitlines()[-1], "2")


if __name__ == "__main__":
    unittest.main()
