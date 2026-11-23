"""Large automatic retrieval evaluation over a random sample of products.

    uv run doit rag_sample_eval
    uv run python -m rag.eval.random_sample_eval [--n 600] [--seed 42] [--lams 0,0.3] [--chroma-dir DIR]

Idea taken from the earlier Amazon_Multimodel_RAG project: pick random products, generate queries from their own
fields, and check that the product comes back. No hand labels, so it scales to hundreds of products.

Query types, and how to read them:
  title_short      first 6 content words of the title      BIASED: shares words with the title by construction,
  title_no_brand   title minus the brand, 8 words           so it favours the title-match bonus (hybrid)
  features         first 8 content words of the first       UNBIASED: no title words by construction; the fair
                   feature bullet                           test of semantic retrieval
  brand_subcat     "<brand> <subcategory>"                  AMBIGUOUS on purpose: many products fit, so recall is
                                                            low by design; for comparing settings only

Hits are exact `doc_id` matches, so near-duplicate listings count as misses. `se_r1` is the standard error of recall@1.
Output: random_sample_eval.json and random_sample_eval.md in RAG_EVAL_DIR (config/paths.py, gitignored).
"""
import argparse
import json
import math
import re

import numpy as np
import pandas as pd

import rag.search as search
from config import retrieval
from config.paths import PRODUCTS_PARQUET, RAG_EVAL_DIR
from contracts.tool_schemas import RagSearchInput

QUERY_TYPES = ["title_short", "title_no_brand", "features", "brand_subcat"]
BIASED = {"title_short", "title_no_brand"}


def compact(text: str, n: int) -> str:
    """First n content words of a text, keeping model-number style tokens."""
    words = [w for w in re.findall(r"[A-Za-z0-9][A-Za-z0-9.+'-]*", text) if w.lower() not in search.STOPWORDS]
    return " ".join(words[:n])


def make_queries(row) -> dict[str, str]:
    """Queries for one product row (needs title, brand, subcategory and a non-empty features list)."""
    brand_re = re.compile(re.escape(row["brand"]), re.I)
    queries = {
        "title_short": compact(row["title"], 6),
        "title_no_brand": compact(brand_re.sub("", row["title"]), 8),
        "features": compact(row["features"][0], 8),
        "brand_subcat": f"{row['brand']} {row['subcategory']}",
    }
    return {k: v for k, v in queries.items() if v}


def eligible(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["price"].notna() & df["brand"].notna() & df["features"].notna()]


def metrics(ranks: list) -> dict:
    n = len(ranks)
    r1 = sum(r == 1 for r in ranks) / n
    return {
        "n": n,
        "recall@1": round(r1, 3),
        "recall@5": round(sum(r is not None and r <= 5 for r in ranks) / n, 3),
        "recall@10": round(sum(r is not None for r in ranks) / n, 3),
        "MRR": round(sum(1 / r for r in ranks if r) / n, 3),
        "se_r1": round(math.sqrt(r1 * (1 - r1) / n), 3),
    }


def run(n: int, seed: int, lams: list[float]) -> dict:
    pool = eligible(pd.read_parquet(PRODUCTS_PARQUET))
    sample = pool.iloc[np.random.default_rng(seed).choice(len(pool), size=min(n, len(pool)), replace=False)]
    ranks = {lam: {t: [] for t in QUERY_TYPES} for lam in lams}
    for _, row in sample.iterrows():
        for kind, text in make_queries(row).items():
            for lam in lams:
                retrieval.HYBRID_LAMBDA = lam  # read at call time by rag.search
                ids = [p.doc_id for p in search.rag_search(RagSearchInput(query=text, top_k=10)).results]
                ranks[lam][kind].append(ids.index(row["doc_id"]) + 1 if row["doc_id"] in ids else None)
    return {
        "sample_size": len(sample),
        "seed": seed,
        "results": {str(lam): {t: metrics(r) for t, r in by_type.items() if r} for lam, by_type in ranks.items()},
    }


def write_report(out: dict) -> str:
    lines = [f"# Random-sample retrieval evaluation ({out['sample_size']} products, seed {out['seed']})", "",
             "| Query type | lambda | n | R@1 (se) | R@5 | R@10 | MRR |", "|---|---|---|---|---|---|---|"]
    for lam, by_type in out["results"].items():
        for kind in QUERY_TYPES:
            if kind in by_type:
                m = by_type[kind]
                label = kind + (" *" if kind in BIASED else "")
                lines.append(f"| {label} | {lam} | {m['n']} | {m['recall@1']} ({m['se_r1']}) | {m['recall@5']} | "
                             f"{m['recall@10']} | {m['MRR']} |")
    lines += ["", "\\* biased toward the title-match bonus: the query shares words with the title by construction.",
              "`features` is the unbiased test; `brand_subcat` is ambiguous on purpose (low recall is expected)."]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n", type=int, default=600, help="products to sample")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--lams", default=None, help="comma-separated HYBRID_LAMBDA values (default: 0 and the config value)")
    parser.add_argument("--chroma-dir", default=None, help="evaluate another index (for comparing embedding variants)")
    args = parser.parse_args()
    if args.chroma_dir:
        search.CHROMA_PATH = args.chroma_dir
    lams = [float(x) for x in args.lams.split(",")] if args.lams else sorted({0.0, retrieval.HYBRID_LAMBDA})
    out = run(args.n, args.seed, lams)
    RAG_EVAL_DIR.mkdir(parents=True, exist_ok=True)
    (RAG_EVAL_DIR / "random_sample_eval.json").write_text(json.dumps(out, indent=2))
    report = write_report(out)
    (RAG_EVAL_DIR / "random_sample_eval.md").write_text(report)
    print(report)


if __name__ == "__main__":
    main()
