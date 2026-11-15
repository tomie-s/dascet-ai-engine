"""Retrieval sweep over similarity thresholds and result counts. Free: uses cached query
embeddings only (run `npm run eval -- --embed` first if a query is missing).

    npm run eval:sweep -- --thresholds 0.35,0.40,0.45,0.50 --counts 5,8
"""

import argparse
import os

import httpx
from dotenv import load_dotenv

from harness import report, retrieval
from harness.cases import load_cases, query_text
from harness.catalogue import fetch_catalogue
from harness.checks import relevance
from harness.settings import MATCH_COUNT, MATCH_THRESHOLD, REPO_ROOT


def _score(case: dict, rows: list[dict], catalogue: dict, k: int) -> dict:
    ids = [row["id"] for row in rows]
    result = {"returned": [{"name": row["name"]} for row in rows], "empty": not rows}
    if case["retrieval"] == "no_match":
        result["no_match_ok"] = not rows
    else:
        result.update(relevance(case, ids, catalogue, k=k))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--thresholds", default="0.35,0.40,0.45,0.50")
    parser.add_argument("--counts", default="5,8")
    args = parser.parse_args()
    thresholds = [float(t) for t in args.thresholds.split(",")]
    counts = [int(c) for c in args.counts.split(",")]

    load_dotenv(REPO_ROOT / ".env")
    supabase = os.environ["SUPABASE_URL"].rstrip("/"), os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    cases = [c for c in load_cases() if c["retrieval"] != "skip"]
    cases_by_id = {c["id"]: c for c in cases}
    cache = retrieval.EmbeddingCache()

    columns = ["hit_at_5", "recall_at_5", "mrr", "category_precision_at_5", "empty_rate",
               "forbidden_cases", "no_match_passed"]
    print("hit/recall/precision are measured at k = count; the current setting is marked *")
    print(f"{'threshold':>9} {'count':>5}  " + "  ".join(f"{c.replace('_at_5', '@k'):>14}" for c in columns))
    with httpx.Client(timeout=30) as client:
        catalogue = fetch_catalogue(client, *supabase)
        embeddings = {
            c["id"]: retrieval.embed_query(client, cache, query_text(c), None, allow_paid=False) for c in cases
        }
        for threshold in thresholds:
            for count in counts:
                results = {
                    c["id"]: _score(
                        c, retrieval.search(client, *supabase, embeddings[c["id"]], threshold, count), catalogue, count
                    )
                    for c in cases
                }
                summary = report.retrieval_summary(results, cases_by_id)
                mark = "*" if (threshold, count) == (MATCH_THRESHOLD, MATCH_COUNT) else " "
                print(f"{threshold:>9.2f} {count:>5}{mark} " + "  ".join(f"{str(summary[c]):>14}" for c in columns))


if __name__ == "__main__":
    main()
