"""Retrieval eval: embed the query (cached), run match_financial_tools, apply the engine's
Canada-only filter, and score the result."""

import hashlib
import json
from pathlib import Path

import httpx

from harness.catalogue import check_response
from harness.checks import relevance
from harness.settings import (
    EVALS_DIR,
    MATCH_COUNT,
    MATCH_THRESHOLD,
    QUERY_PREFIX,
    VOYAGE_INPUT_TYPE,
    VOYAGE_MODEL,
)

CACHE_PATH = EVALS_DIR / "cache" / "embeddings.json"
VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"


class MissingEmbedding(LookupError):
    pass


class EmbeddingCache:
    """Embeddings keyed by model, input type ("query" or "document"), and the exact text sent
    to Voyage."""

    def __init__(self, path: Path = CACHE_PATH):
        self.path = path
        self.entries: dict[str, dict] = json.loads(path.read_text()) if path.exists() else {}
        self.changed = False

    @staticmethod
    def key(text: str, input_type: str = VOYAGE_INPUT_TYPE) -> str:
        return hashlib.sha256(f"{VOYAGE_MODEL}|{input_type}|{text}".encode()).hexdigest()

    def get(self, text: str, input_type: str = VOYAGE_INPUT_TYPE) -> list[float] | None:
        entry = self.entries.get(self.key(text, input_type))
        return entry["embedding"] if entry else None

    def put(self, text: str, embedding: list[float], input_type: str = VOYAGE_INPUT_TYPE) -> None:
        self.entries[self.key(text, input_type)] = {"text": text, "embedding": embedding}
        self.changed = True

    def save(self) -> None:
        """One entry per line keeps diffs readable."""
        if not self.changed:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"  {json.dumps(k)}: {json.dumps(v)}" for k, v in sorted(self.entries.items())]
        self.path.write_text("{\n" + ",\n".join(lines) + "\n}\n")
        self.changed = False


def voyage_embed(
    client: httpx.Client, texts: list[str], voyage_key: str | None, input_type: str = VOYAGE_INPUT_TYPE
) -> list[list[float]]:
    if not voyage_key:
        raise MissingEmbedding("VOYAGE_API_KEY is not set")
    response = client.post(
        VOYAGE_URL,
        json={"input": texts, "model": VOYAGE_MODEL, "input_type": input_type},
        headers={"Authorization": f"Bearer {voyage_key}"},
    )
    check_response(response, "Voyage AI")
    data = sorted(response.json()["data"], key=lambda item: item["index"])
    if len(data) != len(texts):
        raise MissingEmbedding(f"Voyage AI returned {len(data)} embeddings for {len(texts)} texts")
    return [item["embedding"] for item in data]


def embed_missing(
    client: httpx.Client, cache: EmbeddingCache, queries: list[str], voyage_key: str | None
) -> int:
    """Embeds every uncached query in one request (an unbilled Voyage account allows 3 requests
    per minute) and saves the cache. Returns the number of queries embedded."""
    missing = sorted({QUERY_PREFIX + q for q in queries if cache.get(QUERY_PREFIX + q) is None})
    if not missing:
        return 0
    for text, embedding in zip(missing, voyage_embed(client, missing, voyage_key), strict=True):
        cache.put(text, embedding)
    cache.save()
    return len(missing)


def embed_query(
    client: httpx.Client, cache: EmbeddingCache, query: str, voyage_key: str | None, allow_paid: bool
) -> list[float]:
    text = QUERY_PREFIX + query
    cached = cache.get(text)
    if cached is not None:
        return cached
    if not allow_paid:
        raise MissingEmbedding(f"No cached embedding for {query!r}. Re-run with --embed (paid Voyage call).")
    [embedding] = voyage_embed(client, [text], voyage_key)
    cache.put(text, embedding)
    return embedding


def search(
    client: httpx.Client,
    supabase_url: str,
    service_key: str,
    embedding: list[float],
    threshold: float = MATCH_THRESHOLD,
    count: int = MATCH_COUNT,
) -> list[dict]:
    """Same RPC and Canada-only filter as searchTools in src/lib/recommender.ts."""
    response = client.post(
        f"{supabase_url}/rest/v1/rpc/match_financial_tools",
        json={"query_embedding": embedding, "match_threshold": threshold, "match_count": count},
        headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
    )
    check_response(response, "Supabase match_financial_tools")
    rows = response.json()
    canadian = [row for row in rows if row["canadian_available"]]
    return canadian or rows


def score(case: dict, rows: list[dict], catalogue: dict[str, dict]) -> dict:
    ids = [row["id"] for row in rows]
    result = {
        "returned": [{"name": row["name"], "similarity": round(row["similarity"], 4)} for row in rows],
        "empty": not rows,
    }
    if case["retrieval"] == "no_match":
        result["no_match_ok"] = not rows
    else:
        result.update(relevance(case, ids, catalogue))
    return result
