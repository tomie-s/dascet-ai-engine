"""Fails when the harness's mirrored retrieval settings drift from the engine."""

import re

from harness import settings

RECOMMENDER = (settings.REPO_ROOT / "src" / "lib" / "recommender.ts").read_text()


def _find(pattern: str) -> str:
    match = re.search(pattern, RECOMMENDER)
    assert match, f"Pattern not found in src/lib/recommender.ts: {pattern}"
    return match.group(1)


def test_match_threshold():
    assert float(_find(r"const MATCH_THRESHOLD = ([\d.]+);")) == settings.MATCH_THRESHOLD


def test_match_count():
    assert int(_find(r"const MATCH_COUNT = (\d+);")) == settings.MATCH_COUNT


def test_voyage_model():
    assert _find(r'model: "(voyage-[^"]+)"') == settings.VOYAGE_MODEL


def test_voyage_input_type():
    assert _find(r'inputType: "(\w+)"') == settings.VOYAGE_INPUT_TYPE


def test_query_prefix():
    assert _find(r"const retrievalQuery = `(.*)\$\{query\}`;") == settings.QUERY_PREFIX


def test_canada_only_filter():
    assert "canadianTools.length > 0 ? canadianTools : tools" in RECOMMENDER, (
        "The Canada-only filter in searchTools changed; update harness/retrieval.py search()"
    )
