"""Loads evals/cases.jsonl and rejects malformed cases before any test runs."""

import json
from functools import cache

from harness.settings import EVALS_DIR

CASES_PATH = EVALS_DIR / "cases.jsonl"

OUTCOMES = {"recommendation", "clarification"}
RETRIEVAL_MODES = {"match", "no_match", "skip"}
FLAGS = {"includes_counselling", "loan_framing", "no_monitoring_as_repayment", "no_pii_echo"}
FIELDS = {
    "id", "intent", "turns", "expect", "retrieval", "ideal", "categories",
    "required_categories", "forbidden", "forbidden_categories", "flags", "scored", "notes",
}


class CaseError(ValueError):
    pass


def _validate(case: dict, line_number: int) -> None:
    where = f"cases.jsonl line {line_number} ({case.get('id', '?')})"
    if set(case) != FIELDS:
        raise CaseError(f"{where}: fields must be exactly {sorted(FIELDS)}")
    if not case["turns"] or case["turns"][-1]["role"] != "user":
        raise CaseError(f"{where}: turns must end with a user turn")
    if not case["expect"] or not set(case["expect"]) <= OUTCOMES:
        raise CaseError(f"{where}: expect must be a non-empty subset of {sorted(OUTCOMES)}")
    if case["retrieval"] not in RETRIEVAL_MODES:
        raise CaseError(f"{where}: retrieval must be one of {sorted(RETRIEVAL_MODES)}")
    if case["retrieval"] == "match" and not case["ideal"]:
        raise CaseError(f"{where}: retrieval 'match' needs at least one ideal product")
    if not set(case["flags"]) <= FLAGS:
        raise CaseError(f"{where}: unknown flag in {case['flags']}")


@cache
def load_cases() -> tuple[dict, ...]:
    cases = []
    seen = set()
    for line_number, line in enumerate(CASES_PATH.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        case = json.loads(line)
        _validate(case, line_number)
        if case["id"] in seen:
            raise CaseError(f"cases.jsonl line {line_number}: duplicate id {case['id']}")
        seen.add(case["id"])
        cases.append(case)
    return tuple(cases)


def query_text(case: dict) -> str:
    """Retrieval uses the user's own last message, not the query the agent would write."""
    return case["turns"][-1]["content"]
