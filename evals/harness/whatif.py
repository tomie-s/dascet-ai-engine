"""What-if retrieval for catalogue rewrites, without changing the database.

Reads every approved product with its stored embedding, ranks products locally the way
match_financial_tools does (cosine similarity, threshold, top k, then the Canada-only
filter), and compares retrieval before and after the rewrites in evals/catalogue_rewrites.json.
tests/test_whatif.py checks that the local ranking matches the real search for every case.

    npm run eval:whatif                  # free once rewritten texts are cached
    npm run eval:whatif -- --embed       # embed new or changed rewrite texts (paid Voyage)
    npm run eval:whatif -- --check-template --embed
                                         # re-embed current text of rewritten products and
                                         # compare with the stored embeddings
"""

import argparse
import json
import math
import os

import httpx
from dotenv import load_dotenv

from harness import report, retrieval
from harness.cases import load_cases, query_text
from harness.catalogue import check_response
from harness.checks import relevance
from harness.settings import EVALS_DIR, MATCH_COUNT, MATCH_THRESHOLD, REPO_ROOT

REWRITES_PATH = EVALS_DIR / "catalogue_rewrites.json"
DOCUMENT = "document"
PRODUCT_FIELDS = (
    "id,name,tagline,description,category,target_situations,key_features,"
    "experience_level,pricing_model,pricing_plain,canadian_available,embedding"
)


def fetch_products(client: httpx.Client, supabase_url: str, service_key: str) -> dict[str, dict]:
    """Every approved, embedded product, with its embedding parsed into a list of floats."""
    response = client.get(
        f"{supabase_url}/rest/v1/financial_tools",
        params={"select": PRODUCT_FIELDS, "status": "eq.approved", "embedding": "not.is.null"},
        headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
    )
    check_response(response, "Supabase product read")
    products = {}
    for row in response.json():
        embedding = row["embedding"]
        row["embedding"] = json.loads(embedding) if isinstance(embedding, str) else embedding
        products[row["id"]] = row
    return products


def build_tool_text(tool: dict) -> str:
    """Python copy of buildToolText in experiments/02-embed-all-tools.ts."""
    lines = [f"Name: {tool['name']}", f"Tagline: {tool['tagline']}"]
    if tool.get("description"):
        lines.append(f"Description: {tool['description']}")
    if tool.get("category"):
        lines.append(f"Category: {', '.join(tool['category'])}")
    if tool.get("target_situations"):
        lines.append(f"Best for: {', '.join(tool['target_situations'])}")
    if tool.get("key_features"):
        lines.append(f"Key features: {', '.join(tool['key_features'])}")
    if tool.get("experience_level"):
        lines.append(f"Experience level: {tool['experience_level']}")
    if tool.get("pricing_plain"):
        lines.append(f"Pricing: {tool['pricing_plain']}")
    elif tool.get("pricing_model"):
        lines.append(f"Pricing model: {tool['pricing_model']}")
    lines.append(f"Available in Canada: {'Yes' if tool['canadian_available'] else 'No'}")
    return "\n".join(lines)


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def local_search(
    query_embedding: list[float],
    products: dict[str, dict],
    threshold: float = MATCH_THRESHOLD,
    count: int = MATCH_COUNT,
) -> list[dict]:
    """Same ranking as match_financial_tools, followed by the engine's Canada-only filter."""
    scored = [
        {"id": p["id"], "name": p["name"], "canadian_available": p["canadian_available"],
         "similarity": cosine(query_embedding, p["embedding"])}
        for p in products.values()
    ]
    rows = sorted((r for r in scored if r["similarity"] >= threshold), key=lambda r: -r["similarity"])[:count]
    canadian = [r for r in rows if r["canadian_available"]]
    return canadian or rows


def load_rewrites() -> list[dict]:
    """Rewrites still under consideration. Rejected and applied ones stay in the file as the record."""
    rewrites = [r for r in json.loads(REWRITES_PATH.read_text()) if r.get("status") == "proposed"]
    for rewrite in rewrites:
        if rewrite["field"] != "tagline":
            raise SystemExit(f"{rewrite['name']}: only tagline rewrites are supported")
        if not rewrite["targets"]:
            raise SystemExit(f"{rewrite['name']}: every rewrite must name the case it targets")
    return rewrites


def _embed_documents(
    client: httpx.Client, cache: retrieval.EmbeddingCache, texts: list[str], allow_paid: bool
) -> list[list[float]]:
    missing = sorted({t for t in texts if cache.get(t, DOCUMENT) is None})
    if missing:
        if not allow_paid:
            raise SystemExit(f"{len(missing)} product texts are not cached. Re-run with --embed (paid Voyage).")
        vectors = retrieval.voyage_embed(client, missing, os.environ.get("VOYAGE_API_KEY"), DOCUMENT)
        for text, vector in zip(missing, vectors, strict=True):
            cache.put(text, vector, DOCUMENT)
        cache.save()
    return [cache.get(t, DOCUMENT) or [] for t in texts]


def apply_rewrites(
    client: httpx.Client,
    cache: retrieval.EmbeddingCache,
    products: dict[str, dict],
    rewrites: list[dict],
    allow_paid: bool,
) -> dict[str, dict]:
    """A copy of the catalogue with each rewritten product's text and embedding replaced."""
    changed = {p_id: dict(p) for p_id, p in products.items()}
    for rewrite in rewrites:
        product = changed[rewrite["product_id"]]
        if product[rewrite["field"]] != rewrite["before"]:
            raise SystemExit(f"{rewrite['name']}: 'before' no longer matches the database")
        product[rewrite["field"]] = rewrite["after"]
    texts = [build_tool_text(changed[r["product_id"]]) for r in rewrites]
    for rewrite, vector in zip(rewrites, _embed_documents(client, cache, texts, allow_paid), strict=True):
        changed[rewrite["product_id"]]["embedding"] = vector
    return changed


def score_all(cases: list[dict], query_embeddings: dict, products: dict, catalogue: dict) -> dict[str, dict]:
    results = {}
    for case in cases:
        rows = local_search(query_embeddings[case["id"]], products)
        result = {"returned": [r["name"] for r in rows], "empty": not rows}
        if case["retrieval"] == "no_match":
            result["no_match_ok"] = not rows
        else:
            result.update(relevance(case, [r["id"] for r in rows], catalogue))
        results[case["id"]] = result
    return results


def _first_ideal_rank(case: dict, result: dict) -> int | None:
    ideal = {p["name"] for p in case["ideal"]}
    return next((i for i, name in enumerate(result["returned"], 1) if name in ideal), None)


def _regressions(cases_by_id: dict, before: dict, after: dict) -> list[str]:
    lines = []
    for cid, b in before.items():
        a, case = after[cid], cases_by_id[cid]
        if case["retrieval"] == "no_match":
            if b["no_match_ok"] and not a["no_match_ok"]:
                lines.append(f"{cid}: off-topic request now returns {a['returned']}")
            continue
        if b["hit"] and not a["hit"]:
            lines.append(f"{cid}: lost its ideal product; now {a['returned']}")
        if len(a["forbidden_returned"]) > len(b["forbidden_returned"]):
            lines.append(f"{cid}: now returns forbidden {a['forbidden_returned']}")
        rank_b, rank_a = _first_ideal_rank(case, b), _first_ideal_rank(case, a)
        if rank_b and rank_a and rank_a > rank_b:
            lines.append(f"{cid}: first ideal product dropped from rank {rank_b} to {rank_a}")
    return lines


def _print_summary(label: str, results: dict, cases_by_id: dict) -> None:
    s = report.retrieval_summary(results, cases_by_id)
    print(f"  {label:<34} hit@5 {s['hit_at_5']}  recall@5 {s['recall_at_5']}  mrr {s['mrr']}  "
          f"precision {s['category_precision_at_5']}  empty {s['empty_rate']}  "
          f"forbidden {s['forbidden_cases']}  no-match {s['no_match_passed']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--embed", action="store_true", help="Allow paid Voyage calls for uncached texts.")
    parser.add_argument("--check-template", action="store_true",
                        help="Compare re-embedded current text of rewritten products with stored embeddings.")
    args = parser.parse_args()

    load_dotenv(REPO_ROOT / ".env")
    supabase = os.environ["SUPABASE_URL"].rstrip("/"), os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    cases = [c for c in load_cases() if c["retrieval"] != "skip"]
    cases_by_id = {c["id"]: c for c in cases}
    rewrites = load_rewrites()
    cache = retrieval.EmbeddingCache()

    with httpx.Client(timeout=60) as client:
        products = fetch_products(client, *supabase)

        if args.check_template:
            texts = [build_tool_text(products[r["product_id"]]) for r in rewrites]
            for rewrite, vector in zip(rewrites, _embed_documents(client, cache, texts, args.embed), strict=True):
                stored = products[rewrite["product_id"]]["embedding"]
                print(f"  {rewrite['name']:<34} cosine(re-embedded current text, stored) = {cosine(vector, stored):.5f}")
            return

        queries = {c["id"]: retrieval.embed_query(client, cache, query_text(c), None, allow_paid=False) for c in cases}
        rewritten = apply_rewrites(client, cache, products, rewrites, args.embed)
        each_alone = {r["name"]: apply_rewrites(client, cache, products, [r], False) for r in rewrites}

    before = score_all(cases, queries, products, products)
    after = score_all(cases, queries, rewritten, products)

    print("Retrieval before and after all rewrites (local ranking, same settings as the engine):")
    _print_summary("before", before, cases_by_id)
    _print_summary("after (all rewrites)", after, cases_by_id)
    for name, alone in each_alone.items():
        _print_summary(f"only {name[:28]}", score_all(cases, queries, alone, products), cases_by_id)

    print("\nTarget cases:")
    for rewrite in rewrites:
        for cid in rewrite["targets"]:
            case, b, a = cases_by_id[cid], before[cid], after[cid]
            print(f"  {cid} ({rewrite['name']}): hit {b['hit']} -> {a['hit']}, first ideal rank "
                  f"{_first_ideal_rank(case, b)} -> {_first_ideal_rank(case, a)}")
            print(f"      before {b['returned']}")
            print(f"      after  {a['returned']}")

    changed = [cid for cid in before if before[cid]["returned"] != after[cid]["returned"]]
    print(f"\nCases whose results changed: {len(changed)} ({', '.join(changed) or 'none'})")
    regressions = _regressions(cases_by_id, before, after)
    print(f"Regressions ({len(regressions)}):")
    for line in regressions:
        print(f"  {line}")


if __name__ == "__main__":
    main()
