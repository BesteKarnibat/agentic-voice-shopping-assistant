"""Data-quality tests for products.parquet, the 100-product sample and the preprocessing step.

    uv run python -m unittest rag.test_data -v        (needs `uv run doit preprocess` first; skips otherwise)

These pin the conventions the rest of the team relies on: unknown is None (never 0 or an empty list), doc_id is
stable and unique, age and warning fields are consistent.
"""
import json
import re
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from config.paths import KAGGLE_CSV, PRODUCTS_PARQUET, PRODUCTS_SAMPLE_JSON

COLUMNS = ["doc_id", "sku", "title", "brand", "brand_source", "category", "subcategory", "price", "price_is_range",
           "rating", "features", "ingredients", "age_range", "min_age_years", "max_age_years", "age_source",
           "safety_warnings", "product_url"]
WARNING_LABELS = {"choking hazard", "small parts", "small balls", "button battery hazard", "magnets: swallowing hazard",
                  "suffocation hazard", "sharp points or edges"}
need_data = unittest.skipUnless(PRODUCTS_PARQUET.exists(), "run `uv run doit preprocess` first")


@need_data
class ProductsParquetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = pd.read_parquet(PRODUCTS_PARQUET)

    def test_columns_and_size(self):
        self.assertEqual(list(self.df.columns), COLUMNS)
        self.assertGreater(len(self.df), 6000)

    def test_doc_id_is_unique_and_a_hex_id(self):
        self.assertTrue(self.df.doc_id.is_unique)
        self.assertTrue(self.df.doc_id.map(lambda x: bool(re.fullmatch(r"[0-9a-f]{32}", x))).all())

    def test_sku_is_an_asin_matching_the_url(self):
        self.assertTrue(self.df.sku.notna().all())
        self.assertTrue(self.df.sku.map(lambda x: bool(re.fullmatch(r"[A-Z0-9]{10}", x))).all())
        self.assertTrue(all(sku in url for sku, url in zip(self.df.sku, self.df.product_url)))
        self.assertTrue(self.df.product_url.str.startswith("https://www.amazon.com/").all())

    def test_category_is_the_chosen_slice(self):
        self.assertEqual(set(self.df.category), {"Toys & Games"})
        self.assertTrue(self.df.subcategory.notna().all())
        self.assertEqual(self.df.subcategory.nunique(), 20)

    def test_titles_are_non_empty_text(self):
        self.assertTrue(self.df.title.map(lambda t: isinstance(t, str) and t.strip() == t and len(t) > 0).all())

    def test_price_is_none_or_a_positive_number_never_zero(self):
        p = self.df.price.dropna()
        self.assertTrue((p > 0).all())
        self.assertLess(p.max(), 100_000)
        self.assertLess(self.df.price.isna().mean(), 0.03)  # null rate stays low
        self.assertEqual(self.df.price_is_range.dtype, bool)

    def test_rating_and_ingredients_are_always_unknown(self):
        self.assertTrue(self.df.rating.isna().all())
        self.assertTrue(self.df.ingredients.isna().all())

    def test_features_are_none_or_a_non_empty_list_of_text(self):
        for f in self.df.features:
            if f is None:
                continue
            self.assertGreater(len(f), 0)  # never an empty list
            self.assertTrue(all(isinstance(x, str) and x.strip() for x in f))
            self.assertFalse(any(x.lower().startswith("make sure this fits") for x in f))

    def test_brand_fields_agree(self):
        self.assertTrue(set(self.df.brand_source) <= {"manufacturer_field", "alias", "title_first_word", "unknown"})
        unknown = self.df.brand_source == "unknown"
        self.assertTrue(self.df.brand[unknown].isna().all())
        self.assertTrue(self.df.brand[~unknown].notna().all())
        self.assertTrue(self.df.brand.dropna().map(lambda b: b.strip() == b and len(b) > 0).all())

    def test_brand_names_have_one_spelling(self):
        lower = self.df.brand.dropna().str.lower()
        spellings = self.df.brand.dropna().groupby(lower).nunique()
        self.assertEqual(int((spellings > 1).sum()), 0, "same brand written with different casing")

    def test_age_fields_are_consistent(self):
        d = self.df
        self.assertTrue((d.min_age_years.dropna() >= 0).all())
        both = d.dropna(subset=["min_age_years", "max_age_years"])
        self.assertTrue((both.max_age_years >= both.min_age_years).all())
        self.assertTrue(d.max_age_years.dropna().index.isin(d.min_age_years.dropna().index).all(),
                        "a max age without a min age")
        self.assertTrue(set(d.age_source.dropna()) <= {"structured", "text"})
        self.assertTrue((d.age_source.isna() == d.min_age_years.isna()).all())
        self.assertGreater(d.min_age_years.notna().mean(), 0.7)

    def test_warnings_are_none_or_known_labels(self):
        for w in self.df.safety_warnings:
            if w is None:
                continue
            self.assertGreater(len(w), 0)
            for label in w:
                self.assertTrue(label in WARNING_LABELS or re.fullmatch(r"not for children under \d+ (years|months)", label), label)
        self.assertLess(self.df.safety_warnings.notna().mean(), 0.1)  # rare: unknown must not be read as safe


@need_data
class TextRecipeTests(unittest.TestCase):
    """The text that is embedded, the text the reranker reads, and the stored evidence must stay consistent."""

    @classmethod
    def setUpClass(cls):
        cls.df = pd.read_parquet(PRODUCTS_PARQUET)
        cls.rows = [r for _, r in cls.df.sample(300, random_state=3).iterrows()]

    def test_reranker_passage_rebuilt_from_the_index_equals_the_recipe(self):
        from rag import texts
        from rag.build_index import metadata
        for r in self.rows:
            self.assertEqual(texts.passage_from_metadata(metadata(r)), texts.recipe_brand_cat_all(r), r.doc_id)

    def test_embedded_text_carries_brand_and_category_but_listing_text_does_not(self):
        from rag import texts
        branded = [r for r in self.rows if isinstance(r.brand, str)]
        self.assertTrue(branded)
        for r in branded:
            self.assertIn(f"Brand: {r.brand}", texts.embed_text(r, "brand_cat_first3"))
            self.assertIn(f"Category: {r.subcategory}", texts.embed_text(r, "brand_cat_first3"))
            self.assertNotIn("Brand: ", texts.listing_text(r))  # exclusions must not match labels we added

    def test_embedded_text_keeps_only_the_first_three_features(self):
        from rag import texts
        many = [r for r in self.rows if r.features is not None and len(r.features) > 3]
        self.assertTrue(many)
        for r in many:
            t = texts.embed_text(r, "brand_cat_first3")
            self.assertIn(r.features[2], t)
            self.assertNotIn(r.features[3], t)

    def test_snippet_is_a_prefix_of_the_features_and_age(self):
        from rag import texts
        for r in self.rows:
            snip = texts.snippet(r, 220)
            if snip is None:
                self.assertTrue(r.features is None and not isinstance(r.age_range, str))
                continue
            full = ". ".join(([" ".join(r.features)] if r.features is not None else [])
                             + ([f"Recommended age: {r.age_range}"] if isinstance(r.age_range, str) else []))
            self.assertTrue(full.startswith(snip[:-3] if snip.endswith("...") else snip), snip)
            self.assertLessEqual(len(snip), 223)


@need_data
@unittest.skipUnless(PRODUCTS_SAMPLE_JSON.exists(), "sample not built")
class SampleFileTests(unittest.TestCase):
    def test_sample_has_the_same_schema_and_real_products(self):
        df = pd.read_parquet(PRODUCTS_PARQUET)
        sample = json.loads(PRODUCTS_SAMPLE_JSON.read_text())
        self.assertEqual(len(sample), 100)
        self.assertTrue(all(list(row) == COLUMNS for row in sample))
        ids = [row["doc_id"] for row in sample]
        self.assertEqual(len(set(ids)), 100)
        self.assertTrue(set(ids) <= set(df.doc_id))
        self.assertEqual({row["subcategory"] for row in sample}, set(df.subcategory))
        self.assertTrue(all(row["price"] is not None for row in sample))


@unittest.skipUnless(KAGGLE_CSV.exists(), "raw CSV not downloaded")
class PreprocessIsDeterministicTests(unittest.TestCase):
    def test_two_runs_give_identical_output(self):
        from rag.preprocess import main
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a", Path(tmp) / "b"
            a.mkdir(), b.mkdir()
            main(KAGGLE_CSV, a / "p.parquet", a / "s.json")
            main(KAGGLE_CSV, b / "p.parquet", b / "s.json")
            pd.testing.assert_frame_equal(pd.read_parquet(a / "p.parquet"), pd.read_parquet(b / "p.parquet"))
            self.assertEqual((a / "s.json").read_text(), (b / "s.json").read_text())

    def test_every_row_comes_from_the_toys_slice_and_none_is_lost(self):
        raw = pd.read_csv(KAGGLE_CSV, usecols=["Uniq Id", "Category"])
        toys = raw[raw.Category.astype(str).str.startswith("Toys & Games")]
        out = pd.read_parquet(PRODUCTS_PARQUET)
        self.assertEqual(set(out.doc_id), set(toys["Uniq Id"]))


if __name__ == "__main__":
    unittest.main()
