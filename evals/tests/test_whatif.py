"""The what-if tool's local ranking must match the real search, or its before-and-after
results mean nothing. Free: one product read and cached query embeddings."""

import re

import pytest

from harness import retrieval, settings, whatif
from harness.cases import load_cases, query_text

CASES = [c for c in load_cases() if c["retrieval"] != "skip"]
EMBED_SCRIPT = (settings.REPO_ROOT / "experiments" / "02-embed-all-tools.ts").read_text()


@pytest.fixture(scope="module")
def products(http, supabase):
    supabase_url, service_key = supabase
    return whatif.fetch_products(http, supabase_url, service_key)


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_local_ranking_matches_real_search(case, http, supabase, products, embedding_cache):
    embedding = embedding_cache.get(settings.QUERY_PREFIX + query_text(case))
    if embedding is None:
        pytest.skip("query embedding not cached; run npm run eval -- --embed")
    supabase_url, service_key = supabase
    real = [row["id"] for row in retrieval.search(http, supabase_url, service_key, embedding)]
    local = [row["id"] for row in whatif.local_search(embedding, products)]
    assert local == real


def test_embed_script_uses_the_template_the_tool_copies():
    """Fails if experiments/02-embed-all-tools.ts changes how product text is built."""
    template = EMBED_SCRIPT.split("function buildToolText", 1)[1].split("\n}\n", 1)[0]
    labels = re.findall(r"`([A-Z][A-Za-z ]+): \$\{", template)
    assert labels == [
        "Name", "Tagline", "Description", "Category", "Best for", "Key features",
        "Experience level", "Pricing", "Pricing model", "Available in Canada",
    ]
    assert 'inputType: "document"' in EMBED_SCRIPT
    assert f'model: "{settings.VOYAGE_MODEL}"' in EMBED_SCRIPT
