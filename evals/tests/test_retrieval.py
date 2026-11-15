"""Retrieval eval. Scores are recorded for the report; they never fail the run."""

import os

import pytest

from harness import report, retrieval
from harness.cases import load_cases, query_text

CASES = [c for c in load_cases() if c["retrieval"] != "skip"]


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_retrieval(case, request, http, supabase, catalogue, embedding_cache):
    try:
        embedding = retrieval.embed_query(
            http,
            embedding_cache,
            query_text(case),
            os.environ.get("VOYAGE_API_KEY"),
            allow_paid=request.config.getoption("--embed"),
        )
    except retrieval.MissingEmbedding as error:
        pytest.fail(str(error))

    supabase_url, service_key = supabase
    rows = retrieval.search(http, supabase_url, service_key, embedding)
    report.RESULTS["retrieval"][case["id"]] = retrieval.score(case, rows, catalogue)
