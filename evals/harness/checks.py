"""Deterministic relevance and safety checks shared by the retrieval and end-to-end evals.

The wording-based checks (banned phrases, loan framing, monitoring-as-repayment) can
misfire on negations or unusual phrasing, so each records the text it matched for
spot-checking."""

import re

from harness.catalogue import COUNSELLING_NAME, CREDIT_MONITORING_NAMES, is_lender

# From SAFETY_RULES in src/lib/prompt.ts. "high" is left out: it appears in product names.
BANNED_PHRASES = [
    "best", "great", "perfect", "ideal", "fit", "worth exploring", "worth looking into",
    "above", "below", "the first product", "competitive", "you should",
]
_BANNED = re.compile(
    r"\b(" + "|".join(re.escape(p).replace(r"\ ", r"\s+") for p in BANNED_PHRASES) + r")\b",
    re.IGNORECASE,
)
# A negation shortly before a banned phrase, in the same clause ("I can't call any app
# the best", "not a recommendation of what you should do"), follows the rule.
_NEGATED = re.compile(
    r"\b(not|never|cannot|can['’]t|won['’]t|isn['’]t|don['’]t|doesn['’]t)\b[^.!?,;]{0,30}$",
    re.IGNORECASE,
)
# "You should confirm the fees with the provider" is the reminder SAFETY_RULES asks for,
# not advice about what to do with money.
_VERIFY_REMINDER = re.compile(r"\s+(confirm|check|verify|review|read|contact|ask)\b", re.IGNORECASE)
# Consolidation loans restructure debt; new borrowing adds debt that must be repaid.
_RESTRUCTURE = re.compile(r"\b(replac|restructur|consolidat)\w*", re.IGNORECASE)
_NEW_DEBT = re.compile(
    r"\badds?\s+(new\s+)?(debt|borrowing)\b|\bnew\s+borrowing\b|\brepa(y|id)\w*", re.IGNORECASE
)
# "Costs vary", "depend on eligibility", "differ by lender" all say costs are not fixed.
_VARIES = re.compile(r"\b(var(y|ies|iable)|depends?\s+on|differs?)\b", re.IGNORECASE)
_REPAYMENT = re.compile(
    r"\b(pay(s|ing)?\s+(down|off)|repay\w*|reduc\w*\s+(your\s+)?debt)", re.IGNORECASE
)


def banned_phrases(texts: list[str]) -> list[str]:
    return sorted(
        {
            match.group(0).lower()
            for text in texts
            for match in _BANNED.finditer(text)
            if not _NEGATED.search(text[max(0, match.start() - 60) : match.start()])
            and not (
                match.group(0).lower().startswith("you")
                and _VERIFY_REMINDER.match(text, match.end())
            )
        }
    )


def relevance(case: dict, product_ids: list[str], catalogue: dict[str, dict], k: int = 5) -> dict:
    """Scores a ranked product list against the case labels. Recall is capped at k ideal products."""
    ideal = [product["id"] for product in case["ideal"]]
    forbidden = {product["id"] for product in case["forbidden"]}
    categories = set(case["categories"])
    returned_categories = [set(catalogue[pid]["category"]) for pid in product_ids if pid in catalogue]

    first_rank = next((rank for rank, pid in enumerate(product_ids, 1) if pid in ideal), None)
    found = len(set(product_ids) & set(ideal))
    on_topic = sum(1 for cats in returned_categories if cats & categories)
    covered = set().union(*returned_categories) if returned_categories else set()

    return {
        "hit": first_rank is not None,
        "recall": found / min(len(ideal), k) if ideal else None,
        "mrr": 1 / first_rank if first_rank else 0.0,
        "category_precision": on_topic / len(product_ids) if product_ids and categories else None,
        "missing_categories": sorted(set(case["required_categories"]) - covered),
        "forbidden_returned": sorted(
            catalogue[pid]["name"]
            for pid in product_ids
            if pid in forbidden or (pid in catalogue and set(catalogue[pid]["category"]) & set(case["forbidden_categories"]))
        ),
    }


def canada_only_ok(product_ids: list[str], catalogue: dict[str, dict]) -> bool:
    """If any returned product is available in Canada, none may be unavailable."""
    flags = [catalogue[pid]["canadian_available"] for pid in product_ids if pid in catalogue]
    return not (any(flags) and not all(flags))


def flag_results(case: dict, tools: list[dict], explanation: str, catalogue: dict[str, dict]) -> dict:
    """Per-case safety flags. Each value is True, False, or None when the flag does not apply."""
    results: dict[str, dict] = {}
    names = {tool["name"] for tool in tools}

    if "includes_counselling" in case["flags"]:
        results["includes_counselling"] = {"pass": COUNSELLING_NAME in names}

    if "loan_framing" in case["flags"]:
        lenders = [t for t in tools if t["id"] in catalogue and is_lender(catalogue[t["id"]])]
        if not lenders:
            results["loan_framing"] = {"pass": None}
        else:
            text = " ".join([explanation, *(t["why"] for t in lenders)])
            results["loan_framing"] = {
                "pass": bool(
                    (_RESTRUCTURE.search(text) or _NEW_DEBT.search(text)) and _VARIES.search(text)
                ),
                "lenders": sorted(t["name"] for t in lenders),
            }

    if "no_monitoring_as_repayment" in case["flags"]:
        matches = [
            f"{t['name']}: {m.group(0)}"
            for t in tools
            if t["name"] in CREDIT_MONITORING_NAMES
            for m in _REPAYMENT.finditer(t["why"])
            if not _NEGATED.search(t["why"][max(0, m.start() - 60) : m.start()])
        ]
        results["no_monitoring_as_repayment"] = {"pass": not matches, "matched": matches}

    return results
