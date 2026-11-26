"""Unit tests for the preprocessing parsers and the search helpers.

    uv run python -m unittest rag.test_parsers -v      (or: uv run doit rag_unit_test)

No index or raw data needed. Several cases are bugs found while building this (units, corrupt ranges, noise).
"""
import unittest

from rag.preprocess import age_bounds, parse_age, parse_brand, parse_features, parse_price, parse_warnings
from rag.eval.random_sample_eval import compact, make_queries, metrics
from rag.search import _key, _tokens


class PriceTests(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(parse_price("$17.49"), (17.49, False))

    def test_thousands_separator(self):
        self.assertEqual(parse_price("$1,234.50"), (1234.5, False))

    def test_range_takes_the_lowest_and_is_flagged(self):
        self.assertEqual(parse_price("$74.99 - $249.99"), (74.99, True))

    def test_duplicated_screen_reader_text(self):
        self.assertEqual(parse_price("$6.94 $ 6 . 94"), (6.94, False))

    def test_junk_and_missing_are_none(self):
        self.assertEqual(parse_price("Total price:"), (None, False))
        self.assertEqual(parse_price(float("nan")), (None, False))
        self.assertEqual(parse_price(None), (None, False))


class AgeTests(unittest.TestCase):
    def test_spec_text_is_unsquashed(self):
        self.assertEqual(parse_age("ItemWeight:1ounces|Manufacturerrecommendedage:8yearsandup"), "8 years and up")
        self.assertEqual(parse_age("Manufacturerrecommendedage:36months-15years"), "36 months-15 years")
        self.assertIsNone(parse_age("ItemWeight:1ounces"))

    def test_structured_formats(self):
        self.assertEqual(age_bounds("14 years and up", ""), (14.0, None, "structured"))
        self.assertEqual(age_bounds("4-12 years", ""), (4.0, 12.0, "structured"))
        self.assertEqual(age_bounds("36 months-15 years", ""), (3.0, 15.0, "structured"))
        self.assertEqual(age_bounds("18 months and up", ""), (1.5, None, "structured"))
        self.assertEqual(age_bounds("1-18 months", ""), (0.08, 1.5, "structured"))

    def test_corrupt_range_keeps_minimum_only(self):
        self.assertEqual(age_bounds("14-1 years", ""), (14.0, None, "structured"))
        self.assertEqual(age_bounds("36 months-1 years", ""), (3.0, None, "structured"))

    def test_text_fallback(self):
        self.assertEqual(age_bounds(None, "Base Ten Blocks, Ages 5+"), (5.0, None, "text"))
        self.assertEqual(age_bounds(None, "fun toy ages 3-5 years"), (3.0, 5.0, "text"))

    def test_months_in_text_are_not_read_as_years(self):
        self.assertEqual(age_bounds(None, "Stroller Sloth for ages 0-36 months"), (0.0, 3.0, "text"))

    def test_nothing_stated_is_none_not_zero(self):
        self.assertEqual(age_bounds(None, "A nice toy"), (None, None, None))
        self.assertEqual(age_bounds(None, None), (None, None, None))

    def test_structured_value_wins_over_text(self):
        self.assertEqual(age_bounds("8 years and up", "ages 3+"), (8.0, None, "structured"))


class WarningTests(unittest.TestCase):
    def test_typical_listing(self):
        w = parse_warnings("Warning: Choking Hazard - Small parts. Not for children under 3 years.")
        self.assertEqual(w, ["choking hazard", "small parts", "not for children under 3 years"])

    def test_months_unit_kept(self):
        self.assertEqual(parse_warnings("Not suitable for children under 36 months."),
                         ["not for children under 36 months"])

    def test_battery_and_sharp(self):
        w = parse_warnings("Contains button cell batteries. Has sharp points.")
        self.assertIn("button battery hazard", w)
        self.assertIn("sharp points or edges", w)

    def test_prop65_boilerplate_is_not_a_toy_warning(self):
        self.assertIsNone(parse_warnings("Californiaresidents: Click here for Proposition 65 warning"))

    def test_no_warning_is_none_never_empty_list(self):
        self.assertIsNone(parse_warnings("A lovely wooden train set"))
        self.assertIsNone(parse_warnings(None))


class BrandTests(unittest.TestCase):
    def test_manufacturer_field_wins_and_is_unsquashed(self):
        spec = "ItemWeight:1ounces|Manufacturer:AnagramInternational|ASIN:B00XH4Z6SC"
        self.assertEqual(parse_brand(spec, "Some Balloon"), ("Anagram International", "manufacturer_field"))

    def test_multi_word_alias(self):
        self.assertEqual(parse_brand(None, "Melissa & Doug Lovey Lamb Stuffed Animal"), ("Melissa & Doug", "alias"))
        self.assertEqual(parse_brand(None, "The Puppet Company Raven"), ("The Puppet Company", "alias"))

    def test_alias_ignores_hyphen_and_case(self):
        self.assertEqual(parse_brand(None, "Fisher Price Classic Toys"), ("Fisher-Price", "alias"))
        self.assertEqual(parse_brand(None, "fisher-price Farmer Says"), ("Fisher-Price", "alias"))

    def test_first_word_fallback(self):
        self.assertEqual(parse_brand(None, "LEGO Creator Expert Taj Mahal"), ("LEGO", "title_first_word"))

    def test_generic_first_word_is_unknown_not_a_wrong_brand(self):
        self.assertEqual(parse_brand(None, "Remote Control Monster Truck"), (None, "unknown"))
        self.assertEqual(parse_brand(None, "Wooden Train Set"), (None, "unknown"))

    def test_empty_title(self):
        self.assertEqual(parse_brand(None, None), (None, "unknown"))


class FeatureTests(unittest.TestCase):
    def test_boilerplate_dropped_and_split(self):
        about = "Make sure this fits by entering your model number. | 500 pieces | Great for fans"
        self.assertEqual(parse_features(about), ["500 pieces", "Great for fans"])

    def test_missing_is_empty_list_before_the_none_conversion(self):
        self.assertEqual(parse_features(None), [])


class SearchHelperTests(unittest.TestCase):
    def test_brand_key_tolerates_speech_variants(self):
        self.assertEqual(_key("Fisher Price"), _key("Fisher-Price"))
        self.assertEqual(_key("Melissa and Doug"), _key("Melissa & Doug"))
        self.assertEqual(_key("LEGO"), _key("lego"))
        self.assertNotEqual(_key("Hot Wheels"), _key("Hot Toys"))

    def test_tokens_fold_plurals_and_drop_stopwords(self):
        self.assertEqual(_tokens("puzzles"), ["puzzle"])
        self.assertEqual(_tokens("a puzzle for the kids"), ["puzzle"])  # 'kid' is a stopword too
        self.assertEqual(_tokens("glass"), ["glass"])  # double-s is not a plural


class SampleEvalHelperTests(unittest.TestCase):
    ROW = {"title": "Melissa & Doug Wooden Jigsaw Puzzle (24 pcs)", "brand": "Melissa & Doug",
           "subcategory": "Puzzles", "features": ["Chunky wooden pieces for small hands", "Easy to clean"]}

    def test_compact_drops_stopwords_and_caps_length(self):
        self.assertEqual(compact("The best wooden puzzle for a kid", 10), "wooden puzzle")
        self.assertEqual(len(compact("alpha beta gamma delta epsilon zeta eta", 3).split()), 3)

    def test_feature_query_has_no_title_words(self):
        q = make_queries(self.ROW)
        self.assertNotIn("jigsaw", q["features"].lower())  # what makes it the unbiased query type

    def test_title_no_brand_removes_the_brand(self):
        q = make_queries(self.ROW)
        self.assertNotIn("melissa", q["title_no_brand"].lower())
        self.assertEqual(q["brand_subcat"], "Melissa & Doug Puzzles")

    def test_metrics(self):
        m = metrics([1, 2, None, 6])
        self.assertEqual((m["n"], m["recall@1"], m["recall@5"], m["recall@10"]), (4, 0.25, 0.5, 0.75))
        self.assertAlmostEqual(m["MRR"], (1 + 0.5 + 0 + 1 / 6) / 4, places=3)


if __name__ == "__main__":
    unittest.main()
