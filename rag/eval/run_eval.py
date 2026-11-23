"""RAG evaluation for rag_search() (issues #25 plan, #56 run).

Usage: uv run python -m rag.eval.run_eval [--lam 0.3]
Reads rag/eval/eval_queries.json, scores rag_search() against ground truth taken from PRODUCTS_PARQUET,
writes eval_results.json and EVAL_REPORT.md into RAG_EVAL_DIR (config/paths.py, gitignored).
--lam overrides config.retrieval.HYBRID_LAMBDA for one run (used for the lambda sweep).

Metrics
  known_item   recall@1/5/10 and MRR: is the one described product retrieved?
  constraint   constraint satisfaction (every result obeys every filter; target 100%),
               relevance@5 (share of top-5 whose title/features contain a topic keyword)
  edge         pass/fail on each expected behaviour
  latency      p50 / p95 ms after a warm-up query
"""
import argparse
import json
import statistics
import time
from pathlib import Path

import pandas as pd

from config import retrieval
from config.paths import PRODUCTS_PARQUET, RAG_EVAL_DIR
from contracts.tool_schemas import RagSearchInput
from rag.search import _key, rag_search

HERE = Path(__file__).resolve().parent
catalog = pd.read_parquet(PRODUCTS_PARQUET).set_index("doc_id")


def text_of(doc_id):
    r = catalog.loc[doc_id]
    feats = " ".join(r["features"]) if r["features"] is not None else ""
    warns = " ".join(r["safety_warnings"]) if r["safety_warnings"] is not None else ""
    return f"{r['title']} {feats} {warns}".lower()


def violations(check, ids):
    """Return doc_ids that break the filter described in `check`."""
    bad = []
    for i in ids:
        r = catalog.loc[i]
        ok = True
        if "max_price" in check:
            ok &= pd.notna(r["price"]) and r["price"] <= check["max_price"]
        if "min_price" in check:
            ok &= pd.notna(r["price"]) and r["price"] >= check["min_price"]
        if "brand" in check:
            ok &= isinstance(r["brand"], str) and _key(r["brand"]) == _key(check["brand"])
        if "subcategory" in check:
            ok &= r["subcategory"] == check["subcategory"]
        if "child_age_years" in check:  # unknown age is allowed, a stated higher age is not
            ok &= pd.isna(r["min_age_years"]) or r["min_age_years"] <= check["child_age_years"]
        for term in check.get("exclude_features", []):
            ok &= term.lower() not in text_of(i)
        if not ok:
            bad.append(i)
    return bad


def run(q, top_k):
    out = rag_search(RagSearchInput(query=q["query"], top_k=top_k, **q["filters"]))
    return out, [p.doc_id for p in out.results]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lam", type=float, default=None, help="override HYBRID_LAMBDA for this run")
    args = parser.parse_args()
    if args.lam is not None:
        retrieval.HYBRID_LAMBDA = args.lam
    RAG_EVAL_DIR.mkdir(parents=True, exist_ok=True)
    queries = json.loads((HERE / "eval_queries.json").read_text())
    rag_search(RagSearchInput(query="warm up"))  # load model/index outside the timings
    results, latencies = [], []

    for q in queries:
        t0 = time.perf_counter()
        out, ids = run(q, top_k=10)
        latencies.append((time.perf_counter() - t0) * 1000)
        rec = {"id": q["id"], "type": q["type"], "query": q["query"], "filters": q["filters"],
               "n_results": len(ids), "top_score": out.results[0].score if out.results else None}

        if q["type"] == "known_item":
            exp = q["expected_doc_ids"][0]
            rank = ids.index(exp) + 1 if exp in ids else None
            rec.update(rank=rank, passed=rank is not None, expected=exp)
        elif q["type"] == "constraint":
            bad = violations(q["check"], ids)
            top5 = ids[:5]
            kw = q["relevance_keywords"]
            rel = sum(any(k in text_of(i) for k in kw) for i in top5) / len(top5) if top5 else 0.0
            rec.update(violations=len(bad), relevance_at_5=round(rel, 2),
                       passed=bool(ids) and not bad and rel >= 0.6)
        else:
            exp, f = q["expect"], q["filters"]
            if exp == "expect_empty":
                passed = not ids
            elif exp == "expect_unsupported_flag":
                passed = "not applied" in str(out.filters_applied.get("min_rating", ""))
            elif exp.startswith("expect_low_score:"):
                passed = bool(out.results) and out.results[0].score < float(exp.split(":", 1)[1])
            elif exp == "expect_results_no_crash":
                passed = len(ids) > 0
            elif exp == "expect_age_ok":
                passed = bool(ids) and not violations({"child_age_years": f["child_age_years"]}, ids)
            else:
                raise ValueError(exp)
            rec.update(passed=passed, note=q["note"])
        results.append(rec)

    # ---- aggregate
    known = [r for r in results if r["type"] == "known_item"]
    cons = [r for r in results if r["type"] == "constraint"]
    edge = [r for r in results if r["type"] == "edge"]
    summary = {
        "known_item": {
            "n": len(known),
            "recall@1": round(sum(r["rank"] == 1 for r in known) / len(known), 2),
            "recall@5": round(sum(r["rank"] is not None and r["rank"] <= 5 for r in known) / len(known), 2),
            "recall@10": round(sum(r["rank"] is not None for r in known) / len(known), 2),
            "MRR": round(sum(1 / r["rank"] for r in known if r["rank"]) / len(known), 2),
        },
        "constraint": {
            "n": len(cons),
            "satisfaction": round(sum(r["violations"] == 0 and r["n_results"] > 0 for r in cons) / len(cons), 2),
            "mean_relevance@5": round(statistics.mean(r["relevance_at_5"] for r in cons), 2),
            "passed": sum(r["passed"] for r in cons),
        },
        "edge": {"n": len(edge), "passed": sum(r["passed"] for r in edge)},
        "latency_ms": {"p50": round(statistics.median(latencies)),
                       "p95": round(sorted(latencies)[int(0.95 * (len(latencies) - 1))])},
        "total_passed": f"{sum(r['passed'] for r in results)}/{len(results)}",
    }
    (RAG_EVAL_DIR / "eval_results.json").write_text(json.dumps({"summary": summary, "results": results}, indent=2, default=str))

    # ---- report
    lines = ["# RAG evaluation report", "", f"Total passed: **{summary['total_passed']}**", "",
             "| Metric | Value |", "|---|---|"]
    k, c = summary["known_item"], summary["constraint"]
    lines += [f"| Known-item recall@1 / @5 / @10 | {k['recall@1']} / {k['recall@5']} / {k['recall@10']} |",
              f"| Known-item MRR | {k['MRR']} |",
              f"| Constraint satisfaction | {c['satisfaction']} |",
              f"| Constraint mean relevance@5 | {c['mean_relevance@5']} |",
              f"| Edge cases passed | {summary['edge']['passed']}/{summary['edge']['n']} |",
              f"| Latency p50 / p95 (ms) | {summary['latency_ms']['p50']} / {summary['latency_ms']['p95']} |",
              "", "| ID | Type | Query | Result |", "|---|---|---|---|"]
    for r in results:
        detail = (f"rank {r['rank']}" if r["type"] == "known_item"
                  else f"viol {r['violations']}, rel@5 {r['relevance_at_5']}" if r["type"] == "constraint"
                  else f"n={r['n_results']}, top={r['top_score']}")
        lines.append(f"| {r['id']} | {r['type']} | {r['query']} | {'PASS' if r['passed'] else 'FAIL'} ({detail}) |")
    (RAG_EVAL_DIR / "EVAL_REPORT.md").write_text("\n".join(lines) + "\n")

    print(json.dumps(summary, indent=2))
    for r in results:
        if not r["passed"]:
            print("FAIL", r["id"], r["query"], {k: v for k, v in r.items() if k in ("rank", "violations", "relevance_at_5", "n_results", "top_score")})


if __name__ == "__main__":
    main()
