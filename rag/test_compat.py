"""Compatibility tests: does rag_search() still fit what the other four components expect?

    uv run python -m unittest rag.test_compat -v

Guards the shared interfaces (contracts/). If one of these fails because a teammate changed a contract, that is the
point: fix it together before merging. Needs the index for the end-to-end cases (they skip otherwise).
"""
import json
import tempfile
import unittest
from pathlib import Path

from config.paths import CHROMA_DIR, PRODUCTS_PARQUET, ROOT
from contracts import state, tool_schemas
from contracts.tool_schemas import TOOLS, RagProduct, RagSearchInput, RagSearchOutput

READY = PRODUCTS_PARQUET.exists() and (CHROMA_DIR / "chroma.sqlite3").exists()
need_index = unittest.skipUnless(READY, "run `uv run doit preprocess index` first")

# What rag_search() reads and writes today. A change here means the contract moved: tell Juan and Devanshu.
INPUT_FIELDS = {"query", "top_k", "category", "brand", "min_price", "max_price", "min_rating", "child_age_years",
                "exclude_features"}
PRODUCT_FIELDS = {"doc_id", "sku", "title", "brand", "category", "price", "rating", "min_age_years", "max_age_years",
                  "safety_warnings", "features_snippet", "score"}


class ContractShapeTests(unittest.TestCase):
    def test_input_fields_are_the_ones_we_implement(self):
        self.assertEqual(set(RagSearchInput.model_fields), INPUT_FIELDS)

    def test_product_fields_are_the_ones_we_return(self):
        self.assertEqual(set(RagProduct.model_fields), PRODUCT_FIELDS)

    def test_rag_search_is_registered_for_mcp_discovery(self):
        self.assertIn("rag.search", TOOLS)
        self.assertIs(TOOLS["rag.search"]["input"], RagSearchInput)
        self.assertIs(TOOLS["rag.search"]["output"], RagSearchOutput)

    def test_committed_json_schema_matches_the_models(self):
        """contracts/tool_schemas.json is generated; it must not drift from tool_schemas.py."""
        committed = ROOT / "contracts" / "tool_schemas.json"
        with tempfile.TemporaryDirectory() as tmp:
            fresh = tool_schemas.export_json_schemas(str(Path(tmp) / "s.json"))
        self.assertEqual(json.loads(committed.read_text()), json.loads(json.dumps(fresh)))

    def test_every_optional_filter_defaults_to_not_set(self):
        d = RagSearchInput(query="x")
        self.assertEqual((d.top_k, d.category, d.brand, d.min_price, d.max_price, d.min_rating, d.child_age_years,
                          d.exclude_features), (5, None, None, None, None, None, None, []))

    def test_the_planner_state_vocabulary_maps_onto_our_filters(self):
        """state.Constraints and state.Plan.rag_filters feed RagSearchInput; the overlapping names must agree."""
        shared = set(state.Constraints.__annotations__) & INPUT_FIELDS
        self.assertTrue({"category", "brand", "child_age_years", "exclude_features", "min_rating"} <= shared, shared)


@need_index
class EndToEndWithTheOtherComponentsTests(unittest.TestCase):
    def test_retriever_style_call_from_a_plan(self):
        """What Devanshu's Retriever will do: plan -> RagSearchInput -> rag_search -> state dicts."""
        from rag.search import rag_search
        plan: state.Plan = {"use_rag": True, "use_web": False, "rag_query": "cooperative board game for the family",
                            "rag_filters": {"category": "board games", "max_price": 30, "child_age_years": 6,
                                            "exclude_features": ["small parts"], "brand": None},
                            "web_query": None, "comparison_criteria": ["price", "age_range"], "top_k": 3,
                            "reasoning": "private catalog is enough"}
        out = rag_search(RagSearchInput(query=plan["rag_query"], top_k=plan["top_k"], **plan["rag_filters"]))
        update = {"rag_results": [p.model_dump() for p in out.results],
                  **state.log_step("retriever", f"rag.search returned {len(out.results)}", filters=out.filters_applied,
                                   took_ms=out.took_ms)}
        json.dumps(update)  # the whole state update must stay JSON-serializable
        self.assertEqual(len(update["rag_results"]), 3)
        self.assertEqual(update["step_log"][0]["node"], "retriever")

    def test_a_comparison_row_can_be_built_from_every_result(self):
        """Beste's Answerer builds state.ComparisonRow from our output: every field it needs must be derivable."""
        from rag.search import rag_search
        needed = set(state.ComparisonRow.__annotations__) - {"rank", "price_source", "live_url", "citation_markers"}
        for rank, p in enumerate(rag_search(RagSearchInput(query="stuffed animal", top_k=5)).results, 1):
            d = p.model_dump()
            row = {"rank": rank, "title": d["title"], "brand": d["brand"], "price": d["price"], "price_source": "catalog",
                   "rating": d["rating"], "doc_id": d["doc_id"], "safety_warnings": d["safety_warnings"],
                   "age_range": None if d["min_age_years"] is None else (
                       f"{d['min_age_years']:g}+ years" if d["max_age_years"] is None
                       else f"{d['min_age_years']:g}-{d['max_age_years']:g} years"),
                   "live_url": None, "citation_markers": [f"[{rank}]"]}
            self.assertEqual(set(row), set(state.ComparisonRow.__annotations__))
            self.assertTrue(needed <= set(row))

    def test_a_citation_can_always_be_built(self):
        """'No citation, no claim': every product must carry a stable doc_id and a title to cite."""
        from rag.search import rag_search
        for p in rag_search(RagSearchInput(query="puzzle", top_k=10)).results:
            citation = {"marker": "[1]", "source_type": "private", "doc_id": p.doc_id, "url": None, "title": p.title}
            self.assertEqual(set(citation), set(state.Citation.__annotations__))
            self.assertTrue(citation["doc_id"] and citation["title"])

    def test_a_reconciliation_input_is_available(self):
        """Devanshu matches private and live results by SKU, brand and title: the catalog side must supply them."""
        from rag.search import rag_search
        results = rag_search(RagSearchInput(query="lego building set", top_k=10)).results
        self.assertTrue(all(p.title for p in results))
        self.assertTrue(all(p.sku for p in results), "every catalog product has an ASIN to match on")
        self.assertTrue(any(p.brand for p in results))

    def test_no_secret_or_environment_variable_is_needed(self):
        """The repo rule: .env holds secrets only. Searching must work with an empty environment of API keys."""
        import os
        from rag.search import rag_search
        keys = [k for k in os.environ if k.endswith("_API_KEY") or k.endswith("_TOKEN")]
        saved = {k: os.environ.pop(k) for k in keys}
        try:
            self.assertTrue(rag_search(RagSearchInput(query="puzzle", top_k=2)).results)
        finally:
            os.environ.update(saved)


if __name__ == "__main__":
    unittest.main()
