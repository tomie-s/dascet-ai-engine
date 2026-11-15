"""Collects per-case results during the run, then prints a summary and writes results JSON.
The summary functions take results as arguments so harness/compare.py can reuse them."""

import json
import subprocess
from datetime import UTC, datetime

from harness import settings
from harness.e2e import safety_ok

RESULTS: dict[str, dict[str, dict]] = {"retrieval": {}, "e2e": {}}
# Filled by the catalogue fixture, so the regression check can re-score reference runs.
CATALOGUE: dict[str, dict] = {}

RESULTS_DIR = settings.EVALS_DIR / "results"
LATEST_PATH = RESULTS_DIR / "latest.json"
BASELINE_PATH = RESULTS_DIR / "baseline.json"

USAGE_FIELDS = ("calls", "inputTokens", "outputTokens", "cacheReadTokens", "cacheWriteTokens")


def _mean(values) -> float | None:
    values = [float(v) for v in values if v is not None]
    return round(sum(values) / len(values), 3) if values else None


def retrieval_summary(results: dict[str, dict], cases_by_id: dict) -> dict:
    match = [r for cid, r in results.items() if cases_by_id[cid]["retrieval"] == "match"]
    no_match = [r for cid, r in results.items() if cases_by_id[cid]["retrieval"] == "no_match"]
    return {
        "cases": len(match),
        "hit_at_5": _mean(r["hit"] for r in match),
        "recall_at_5": _mean(r["recall"] for r in match),
        "mrr": _mean(r["mrr"] for r in match),
        "category_precision_at_5": _mean(r["category_precision"] for r in match),
        "empty_rate": _mean(r["empty"] for r in match),
        "forbidden_cases": sum(1 for r in match if r["forbidden_returned"]),
        "no_match_passed": f"{sum(r['no_match_ok'] for r in no_match)}/{len(no_match)}",
    }


def e2e_summary(results: dict[str, dict], cases_by_id: dict) -> dict:
    scored = [(cases_by_id[cid], r) for cid, r in results.items() if cases_by_id[cid]["scored"]]
    recs = [r for _, r in scored if r.get("outcome") == "recommendation"]
    expects_rec = [(c, r) for c, r in scored if c["expect"] == ["recommendation"] and c["ideal"]]
    needs_coverage = [(c, r) for c, r in scored if c["required_categories"]]
    return {
        "cases": len(scored),
        "outcome_accuracy": _mean(r["outcome_ok"] for _, r in scored),
        "schema_valid_rate": _mean(not r["schema_errors"] for _, r in scored),
        "grounded_rate": _mean(not r["ungrounded"] for r in recs),
        "hit_rate": _mean(r.get("hit", False) for _, r in expects_rec),
        "category_precision": _mean(r.get("category_precision") for r in recs),
        "coverage_rate": _mean(
            r.get("outcome") == "recommendation" and not r["missing_categories"]
            for _, r in needs_coverage
        ),
        "wording_clean_rate": _mean(
            not r["wording_violations"] for _, r in scored if "wording_violations" in r
        ),
        "safety_pass_rate": _mean(safety_ok(r) for r in recs),
    }


def _cost_usd(usage: dict) -> float | None:
    prices = settings.PRICES.get(usage["model"])
    if not prices:
        return None
    return (
        usage["inputTokens"] * prices["input"]
        + usage["outputTokens"] * prices["output"]
        + usage["cacheReadTokens"] * prices["cache_read"]
        + usage["cacheWriteTokens"] * prices["cache_write"]
    ) / 1_000_000


def cost_summary(results: dict[str, dict]) -> dict | None:
    """Token totals and estimated cost, when the API reported usage (EVAL_INCLUDE_USAGE=1)."""
    usages = [r["usage"] for r in results.values() if r.get("usage")]
    if not usages:
        return None
    costs = [_cost_usd(u) for u in usages]
    priced = [c for c in costs if c is not None]
    known = sum(priced) if len(priced) == len(costs) else None
    return {
        "requests": len(usages),
        "models": sorted({u["model"] for u in usages}),
        **{field: sum(u[field] for u in usages) for field in USAGE_FIELDS},
        "usd": round(known, 4) if known is not None else None,
        "usd_per_request": round(known / len(usages), 5) if known is not None else None,
    }


def by_intent(retrieval: dict, e2e: dict, cases: tuple[dict, ...]) -> dict:
    table: dict[str, dict] = {}
    for intent in sorted({c["intent"] for c in cases if c["scored"]}):
        ids = [c["id"] for c in cases if c["intent"] == intent and c["scored"]]
        r_rows = [retrieval[i] for i in ids if i in retrieval]
        e_rows = [e2e[i] for i in ids if i in e2e]
        table[intent] = {
            "cases": len(ids),
            "retrieval_hit_at_5": _mean(r.get("hit") for r in r_rows),
            "e2e_outcome_accuracy": _mean(r["outcome_ok"] for r in e_rows),
            "e2e_hit_rate": _mean(r.get("hit") for r in e_rows if r.get("outcome") == "recommendation"),
        }
    return table


def e2e_failures(case: dict, r: dict) -> list[str]:
    """Short labels for every check one end-to-end result failed."""
    if r["schema_errors"]:
        return [f"schema {r['schema_errors']}"]
    labels = []
    if not r["outcome_ok"]:
        labels.append(f"expected {case['expect']}, got {r['outcome']}")
    if r.get("ungrounded"):
        labels.append(f"ungrounded {r['ungrounded']}")
    if r.get("wording_violations"):
        labels.append(f"wording {r['wording_violations']}")
    if r.get("outcome") == "recommendation" and case["ideal"] and r.get("hit") is False:
        labels.append("no ideal product")
    if r.get("canada_only_ok") is False:
        labels.append("mixed Canadian and non-Canadian products")
    if r.get("forbidden_returned"):
        labels.append(f"forbidden {r['forbidden_returned']}")
    if r.get("missing_categories"):
        labels.append(f"missing categories {r['missing_categories']}")
    for flag, detail in r.get("flags", {}).items():
        if detail["pass"] is False:
            extra = {k: v for k, v in detail.items() if k != "pass"}
            labels.append(f"{flag} failed {extra or ''}".rstrip())
    return labels


def failures(retrieval: dict, e2e: dict, cases_by_id: dict) -> list[str]:
    lines = []
    for cid, r in retrieval.items():
        if cases_by_id[cid]["retrieval"] == "no_match" and not r["no_match_ok"]:
            lines.append(f"retrieval {cid}: expected no match, got {[p['name'] for p in r['returned']]}")
        elif cases_by_id[cid]["retrieval"] == "match":
            if not r["hit"]:
                lines.append(f"retrieval {cid}: no ideal product, got {[p['name'] for p in r['returned']]}")
            if r["forbidden_returned"]:
                lines.append(f"retrieval {cid}: forbidden {r['forbidden_returned']}")
    for cid, r in e2e.items():
        tag = "e2e" if cases_by_id[cid]["scored"] else "e2e (unscored)"
        lines.extend(f"{tag} {cid}: {label}" for label in e2e_failures(cases_by_id[cid], r))
    return lines


def _git_commit() -> str:
    def git(*args):
        return subprocess.run(["git", *args], cwd=settings.REPO_ROOT, capture_output=True, text=True).stdout.strip()

    commit = git("rev-parse", "--short", "HEAD")
    return f"{commit}-dirty" if git("status", "--porcelain") else commit


def _baseline_problem(cases: tuple[dict, ...]) -> str | None:
    """A baseline needs every case and a real response from each end-to-end request."""
    retrieval_ids = {c["id"] for c in cases if c["retrieval"] != "skip"}
    if not retrieval_ids <= RESULTS["retrieval"].keys() or len(RESULTS["e2e"]) != len(cases):
        return "it needs every case, including end-to-end (--paid, no -k filter)"
    errored = sorted(cid for cid, r in RESULTS["e2e"].items() if r["status"] != 200)
    if errored:
        return f"{len(errored)} end-to-end requests returned an HTTP error: {', '.join(errored)}"
    return None


def finish(terminal, config, cases: tuple[dict, ...]) -> None:
    retrieval, e2e = RESULTS["retrieval"], RESULTS["e2e"]
    if not retrieval and not e2e:
        return

    cases_by_id = {c["id"]: c for c in cases}
    cost = cost_summary(e2e) if e2e else None
    report = {
        "metadata": {
            "date": datetime.now(UTC).isoformat(timespec="seconds"),
            "commit": _git_commit(),
            "agent_model": ", ".join(cost["models"]) if cost else settings.engine_default_model(),
            "agent_model_source": "API usage" if cost else "default in src/lib/tools.ts",
            "voyage_model": settings.VOYAGE_MODEL,
            "query_prefix": settings.QUERY_PREFIX,
            "match_threshold": settings.MATCH_THRESHOLD,
            "match_count": settings.MATCH_COUNT,
            "paid": bool(e2e) and not config.getoption("--replay"),
            "replayed_from": config.getoption("--replay"),
            "base_url": config.getoption("--base-url") if e2e else None,
        },
        "retrieval": retrieval_summary(retrieval, cases_by_id) if retrieval else None,
        "e2e": e2e_summary(e2e, cases_by_id) if e2e else None,
        "cost": cost,
        "by_intent": by_intent(retrieval, e2e, cases),
        "failures": failures(retrieval, e2e, cases_by_id),
        "cases": {"retrieval": retrieval, "e2e": e2e},
    }

    terminal.section("Dascet evaluation report")
    for section in ("retrieval", "e2e", "cost"):
        if report[section]:
            terminal.write_line(f"{section}:")
            for name, value in report[section].items():
                terminal.write_line(f"  {name:<26} {value}")
    if e2e and not cost:
        terminal.write_line("cost: not reported (start the API with EVAL_INCLUDE_USAGE=1)")
    terminal.write_line("by intent:")
    for intent, row in report["by_intent"].items():
        cells = "  ".join(f"{k}={v}" for k, v in row.items())
        terminal.write_line(f"  {intent:<12} {cells}")
    terminal.write_line(f"failures ({len(report['failures'])}):")
    for line in report["failures"]:
        terminal.write_line(f"  {line}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    terminal.write_line(f"results written to {LATEST_PATH.relative_to(settings.REPO_ROOT)}")

    if config.getoption("--save-baseline"):
        problem = "a replayed run is not a new baseline" if config.getoption("--replay") else _baseline_problem(cases)
        if problem:
            terminal.write_line(f"baseline NOT written: {problem}")
        else:
            BASELINE_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
            terminal.write_line(f"baseline written to {BASELINE_PATH.relative_to(settings.REPO_ROOT)}")
