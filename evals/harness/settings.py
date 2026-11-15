"""Engine settings the harness mirrors. tests/test_parity.py fails if these drift
from src/lib/recommender.ts, so change both together."""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EVALS_DIR = REPO_ROOT / "evals"

VOYAGE_MODEL = "voyage-3-lite"
VOYAGE_INPUT_TYPE = "query"
QUERY_PREFIX = "Canadian financial product discovery request: "
MATCH_THRESHOLD = 0.45
MATCH_COUNT = 5

DEFAULT_BASE_URL = "http://localhost:3000"

# US$ per million tokens, from the Claude API model table (cached 2026-11-03). Cache read
# and write prices for Haiku 5.5, and the Sonnet 5.5 cache write price, are not listed
# there; 0.1x and 1.25x the input price are assumed.
PRICES = {
    "claude-haiku-5-5": {"input": 0.10, "output": 0.50, "cache_read": 0.01, "cache_write": 0.125},
    "claude-sonnet-5-5": {"input": 2.00, "output": 10.00, "cache_read": 0.10, "cache_write": 2.50},
}


def engine_default_model() -> str | None:
    """The default agent model in src/lib/tools.ts (AGENT_MODEL may override it at runtime)."""
    source = (REPO_ROOT / "src" / "lib" / "tools.ts").read_text()
    match = re.search(r'export const AGENT_MODEL = [^;]*"([^"]+)";', source)
    return match.group(1) if match else None
