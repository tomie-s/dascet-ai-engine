import json
import os
from pathlib import Path

import httpx
import pytest
from dotenv import load_dotenv

from harness import regression, report
from harness.cases import load_cases, query_text
from harness.catalogue import fetch_catalogue
from harness.retrieval import EmbeddingCache, embed_missing
from harness.settings import DEFAULT_BASE_URL, REPO_ROOT

load_dotenv(REPO_ROOT / ".env")

CHECK_RESULT = pytest.StashKey[dict]()


def pytest_addoption(parser):
    group = parser.getgroup("dascet evals")
    group.addoption(
        "--paid", action="store_true",
        help="Run end-to-end evals against the API (paid Claude and Voyage calls).",
    )
    group.addoption(
        "--embed", action="store_true",
        help="Allow paid Voyage calls for queries missing from the embedding cache.",
    )
    group.addoption("--base-url", default=DEFAULT_BASE_URL, help="API base URL for --paid runs.")
    group.addoption(
        "--save-baseline", action="store_true",
        help="Write evals/results/baseline.json (needs a complete --paid run).",
    )
    group.addoption(
        "--check", action="store_true",
        help="Compare with the reference in evals/regression.json and fail on regressions.",
    )
    group.addoption(
        "--replay", metavar="RUN_JSON",
        help="Score the responses saved in a results file instead of calling the API (free).",
    )
    group.addoption(
        "--update-reference", action="store_true",
        help="Rewrite the retrieval snapshot in evals/regression.json from this run.",
    )


def pytest_configure(config):
    if config.getoption("--paid") and config.getoption("--replay"):
        raise pytest.UsageError("--paid and --replay cannot be combined")
    partial = config.getoption("keyword") or config.getoption("markexpr")
    if partial and (config.getoption("--check") or config.getoption("--update-reference")):
        raise pytest.UsageError("--check and --update-reference need the full suite; remove -k/-m")


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.exit(f"{name} is not set in .env", returncode=2)
    return value


@pytest.fixture(scope="session")
def http():
    with httpx.Client(timeout=30) as client:
        yield client


@pytest.fixture(scope="session")
def supabase() -> tuple[str, str]:
    return _require_env("SUPABASE_URL").rstrip("/"), _require_env("SUPABASE_SERVICE_ROLE_KEY")


@pytest.fixture(scope="session")
def catalogue(http, supabase):
    catalogue = fetch_catalogue(http, *supabase)
    report.CATALOGUE.update(catalogue)
    return catalogue


@pytest.fixture(scope="session")
def embedding_cache(request, http):
    cache = EmbeddingCache()
    if request.config.getoption("--embed"):
        queries = [query_text(c) for c in load_cases() if c["retrieval"] != "skip"]
        embed_missing(http, cache, queries, os.environ.get("VOYAGE_API_KEY"))
    yield cache
    cache.save()


@pytest.fixture(scope="session")
def replayed(request) -> dict[str, dict] | None:
    """Saved end-to-end results from --replay, keyed by case ID."""
    path = request.config.getoption("--replay")
    if not path:
        return None
    return json.loads((REPO_ROOT / Path(path)).read_text())["cases"]["e2e"]


def _run_check(config) -> dict:
    cases = load_cases()
    cases_by_id = {c["id"]: c for c in cases}
    reg_config = regression.load_config()
    retrieval_ids = {c["id"] for c in cases if c["retrieval"] != "skip"}
    result: dict = {"regressions": [], "new_failures": [], "notes": []}

    if not retrieval_ids <= report.RESULTS["retrieval"].keys():
        result["regressions"].append("retrieval: not every case ran")
    else:
        result["regressions"] += regression.retrieval_regressions(
            report.RESULTS["retrieval"], reg_config["retrieval"]
        )

    e2e = report.RESULTS["e2e"]
    if not e2e:
        result["notes"].append("end to end not checked; add --paid (paid) or --replay <run.json> (free)")
    elif len(e2e) != len(cases):
        result["regressions"].append("e2e: not every case ran")
    else:
        references = regression.load_reference_runs(reg_config, cases_by_id, report.CATALOGUE)
        lines, new = regression.e2e_regressions(e2e, references, cases_by_id, reg_config["tolerance"])
        result["regressions"] += lines
        result["new_failures"] = new
    return result


def pytest_sessionfinish(session, exitstatus):
    config = session.config
    if config.getoption("--update-reference") and report.RESULTS["retrieval"]:
        regression.save_retrieval_snapshot(regression.load_config(), report.RESULTS["retrieval"])
    if config.getoption("--check") and exitstatus == pytest.ExitCode.OK:
        result = _run_check(config)
        config.stash[CHECK_RESULT] = result
        if result["regressions"]:
            session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    report.finish(terminalreporter, config, load_cases())
    if config.getoption("--update-reference"):
        terminalreporter.write_line("retrieval snapshot written to evals/regression.json")
    if not config.getoption("--check"):
        return
    result = config.stash.get(CHECK_RESULT, None)
    terminalreporter.section("Regression check")
    if result is None:
        terminalreporter.write_line("FAILED: tests failed before the comparison could run")
        return
    for note in result["notes"]:
        terminalreporter.write_line(f"note: {note}")
    for line in result["regressions"]:
        terminalreporter.write_line(f"REGRESSION {line}")
    if result["new_failures"]:
        terminalreporter.write_line("cases failing a check that passed it in every reference run:")
        for line in result["new_failures"]:
            terminalreporter.write_line(f"  {line}")
    verdict = "FAILED" if result["regressions"] else "PASSED"
    terminalreporter.write_line(
        f"{verdict}: {len(result['regressions'])} regressions, {len(result['new_failures'])} new case failures"
    )
