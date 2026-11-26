"""Large automatic retrieval evaluation over a random sample of products.

    uv run doit rag_sample_eval
    uv run python -m rag.eval.random_sample_eval [--n 600] [--seed 42] [--chroma-dir DIR]

Idea taken from the earlier Amazon_Multimodel_RAG project: pick random products, generate queries from their own
fields, and check that the product comes back. No hand labels, so it scales to hundreds of products.

Query types, and how to read them:
  title_short      first 6 content words of the title      BIASED: shares words with the title by construction,
  title_no_brand   title minus the brand, 8 words           so it favours the title-match bonus (hybrid)
  features         first 8 content words of the first       UNBIASED: no title words by construction; the fair
                   feature bullet                           test of semantic retrieval
  brand_subcat     "<brand> <subcategory>"                  AMBIGUOUS on purpose: many products fit, so exact recall
                                                            is low by design. Scored as precision@5: the share of
                                                            the top 5 with that brand AND subcategory.

Three systems are compared so each component's contribution is visible: vector search alone, plus the title/brand
match bonus, plus the cross-encoder reranker (only if config/retrieval.py enables it).

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


def systems() -> list[tuple[str, float, bool]]:
    """(label, hybrid weight, reranker on) for the three systems compared."""
    out = [("vector only", 0.0, False), ("+ title match", retrieval.HYBRID_LAMBDA, False)]
    if retrieval.RERANKER_MODEL:
        out.append(("+ reranker (shipped)", retrieval.HYBRID_LAMBDA, True))
    return out


def precision_at_5(top5_keys: list, key) -> float:
    return sum(k == key for k in top5_keys) / len(top5_keys) if top5_keys else 0.0


def run(n: int, seed: int) -> dict:
    df = pd.read_parquet(PRODUCTS_PARQUET)
    group_of = {r.doc_id: (r.brand, r.subcategory) for r in df.itertuples()}
    pool = eligible(df)
    sample = pool.iloc[np.random.default_rng(seed).choice(len(pool), size=min(n, len(pool)), replace=False)]
    state = search._load()
    shipped_reranker = state["reranker"]
    results = {}
    for label, lam, rerank in systems():
        retrieval.HYBRID_LAMBDA = lam  # read at call time by rag.search
        state["reranker"] = shipped_reranker if rerank else None
        ranks = {t: [] for t in QUERY_TYPES}
        p5 = []
        for _, row in sample.iterrows():
            for kind, text in make_queries(row).items():
                found = search.rag_search(RagSearchInput(query=text, top_k=10)).results
                ids = [p.doc_id for p in found]
                ranks[kind].append(ids.index(row["doc_id"]) + 1 if row["doc_id"] in ids else None)
                if kind == "brand_subcat":
                    p5.append(precision_at_5([group_of[i] for i in ids[:5]], (row["brand"], row["subcategory"])))
        results[label] = {t: metrics(r) for t, r in ranks.items() if r}
        results[label]["brand_subcat"]["P@5"] = round(float(np.mean(p5)), 3)
    state["reranker"] = shipped_reranker
    retrieval.HYBRID_LAMBDA = dict((l, w) for l, w, _ in systems())["+ title match"]
    return {"sample_size": len(sample), "seed": seed, "results": results}


def write_report(out: dict) -> str:
    lines = [f"# Random-sample retrieval evaluation ({out['sample_size']} products, seed {out['seed']})", "",
             "| Query type | System | n | R@1 (se) | R@10 | MRR | P@5 |", "|---|---|---|---|---|---|---|"]
    for kind in QUERY_TYPES:
        for label, by_type in out["results"].items():
            if kind in by_type:
                m = by_type[kind]
                name = kind + (" *" if kind in BIASED else "")
                lines.append(f"| {name} | {label} | {m['n']} | {m['recall@1']} ({m['se_r1']}) | {m['recall@10']} | "
                             f"{m['MRR']} | {m.get('P@5', '')} |")
    lines += ["", "\\* biased toward the title-match bonus: the query shares words with the title by construction.",
              "`features` is the unbiased test; `brand_subcat` is ambiguous on purpose (judge it by P@5)."]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n", type=int, default=600, help="products to sample")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--chroma-dir", default=None, help="evaluate another index (for comparing embedding variants)")
    args = parser.parse_args()
    if args.chroma_dir:
        search.CHROMA_PATH = args.chroma_dir
    out = run(args.n, args.seed)
    RAG_EVAL_DIR.mkdir(parents=True, exist_ok=True)
    (RAG_EVAL_DIR / "random_sample_eval.json").write_text(json.dumps(out, indent=2))
    report = write_report(out)
    (RAG_EVAL_DIR / "random_sample_eval.md").write_text(report)
    print(report)


if __name__ == "__main__":
    main()
