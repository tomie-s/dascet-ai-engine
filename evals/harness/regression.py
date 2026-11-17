"""Regression check: compares a run with the accepted reference in evals/regression.json.

Retrieval is deterministic (cached embeddings), so any case that loses its ideal product,
any off-topic case that returns products, and any new forbidden product is a regression.
End to end, schema, grounding, outcome, safety, and no-leak must pass for every case; hit rate,
wording, and coverage may fall at most a set number of cases below the worst reference
run, and category precision a set amount. Reference runs are re-scored with the current
checks every time, so the reference cannot go stale when a check changes."""

import json
from pathlib import Path

from harness import compare, report
from harness.e2e import safety_ok
from harness.settings import EVALS_DIR, REPO_ROOT

CONFIG_PATH = EVALS_DIR / "regression.json"
SOFT_METRICS = ("hit", "wording", "coverage")
HARD_METRICS = ("schema", "grounded", "outcome", "safety", "no_leak")


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text())


def save_retrieval_snapshot(config: dict, retrieval: dict[str, dict]) -> None:
    config["retrieval"] = {
        cid: {
            "hit": r.get("hit"),
            "no_match_ok": r.get("no_match_ok"),
            "forbidden": r.get("forbidden_returned", []),
        }
        for cid, r in sorted(retrieval.items())
    }
    CONFIG_PATH.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n")


def retrieval_regressions(current: dict[str, dict], snapshot: dict[str, dict]) -> list[str]:
    lines = []
    for cid, ref in snapshot.items():
        cur = current.get(cid)
        if cur is None:
            lines.append(f"retrieval {cid}: missing from this run")
            continue
        names = [p["name"] for p in cur["returned"]]
        if ref["hit"] and not cur.get("hit"):
            lines.append(f"retrieval {cid}: lost its ideal product; now {names}")
        if ref["no_match_ok"] and not cur.get("no_match_ok"):
            lines.append(f"retrieval {cid}: off-topic request now returns {names}")
        if len(cur.get("forbidden_returned", [])) > len(ref["forbidden"]):
            lines.append(f"retrieval {cid}: now returns forbidden {cur['forbidden_returned']}")
    return lines


def case_checks(results: dict[str, dict], cases_by_id: dict) -> dict[str, dict[str, bool]]:
    """For each check, which scored cases it applies to and whether each passed."""
    checks: dict[str, dict[str, bool]] = {name: {} for name in (*HARD_METRICS, *SOFT_METRICS)}
    for cid, r in results.items():
        case = cases_by_id[cid]
        if not case["scored"]:
            continue
        is_rec = r.get("outcome") == "recommendation"
        checks["schema"][cid] = not r["schema_errors"]
        checks["outcome"][cid] = bool(r["outcome_ok"])
        if "ungrounded" in r:
            checks["grounded"][cid] = not r["ungrounded"]
        if "leaks" in r:
            checks["no_leak"][cid] = not r["leaks"]
        if is_rec:
            checks["safety"][cid] = bool(safety_ok(r))
        if "wording_violations" in r:
            checks["wording"][cid] = not r["wording_violations"]
        if case["expect"] == ["recommendation"] and case["ideal"]:
            checks["hit"][cid] = is_rec and bool(r.get("hit"))
        if case["required_categories"]:
            checks["coverage"][cid] = is_rec and not r["missing_categories"]
    return checks


def _passed(check: dict[str, bool]) -> int:
    return sum(check.values())


def _kinds(case: dict, r: dict) -> set[str]:
    """Failure labels reduced to their kind, so 'wording ["below"]' and 'wording ["great"]' match."""
    kinds = set()
    for label in report.e2e_failures(case, r):
        word = label.split(" ")[0]
        kinds.add(word if word in ("wording", "forbidden", "ungrounded", "schema", "missing", "expected", "leaked")
                  else label.split(" failed")[0])
    return kinds


def e2e_regressions(
    current: dict[str, dict], references: list[dict[str, dict]], cases_by_id: dict, tolerance: dict
) -> tuple[list[str], list[str]]:
    """Returns (regressions, new failures). New failures are cases failing a check in this run
    that passed it in every reference run; they name what changed even when no limit is crossed."""
    cur = case_checks(current, cases_by_id)
    refs = [case_checks(r, cases_by_id) for r in references]
    lines = []

    for name in HARD_METRICS:
        failing = sorted(cid for cid, ok in cur[name].items() if not ok)
        if failing:
            lines.append(f"e2e {name}: failed for {', '.join(failing)} (every case must pass)")

    allowed_drop = tolerance["cases_below_worst_reference"]
    for name in SOFT_METRICS:
        worst = min(_passed(ref[name]) for ref in refs)
        got, total = _passed(cur[name]), len(cur[name])
        if got < worst - allowed_drop:
            failing = sorted(cid for cid, ok in cur[name].items() if not ok)
            lines.append(
                f"e2e {name}: {got}/{total} passed, below the limit of {worst - allowed_drop} "
                f"(worst reference run {worst}, minus {allowed_drop}); failing: {', '.join(failing)}"
            )

    precision = report.e2e_summary(current, cases_by_id)["category_precision"]
    worst_precision = min(report.e2e_summary(r, cases_by_id)["category_precision"] or 0 for r in references)
    limit = round(worst_precision - tolerance["category_precision_below_worst_reference"], 3)
    if precision is not None and precision < limit:
        lines.append(f"e2e category precision: {precision}, below the limit of {limit}")

    new = []
    for cid, r in current.items():
        case = cases_by_id[cid]
        if not case["scored"]:
            continue
        seen = set().union(*(_kinds(case, ref[cid]) for ref in references if cid in ref))
        fresh = sorted(_kinds(case, r) - seen)
        if fresh:
            new.append(f"{cid}: {', '.join(fresh)}")
    return lines, new


def load_reference_runs(config: dict, cases_by_id: dict, catalogue: dict) -> list[dict[str, dict]]:
    return [compare.rescore(REPO_ROOT / Path(p), cases_by_id, catalogue) for p in config["reference_runs"]]
