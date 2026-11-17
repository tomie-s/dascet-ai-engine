"""End-to-end eval against a running API (--paid), or against responses saved in a results
file (--replay, free). Skipped otherwise. Only schema and grounding fail the run; every
other check is recorded for the report and the regression check."""

import httpx
import pytest

from harness import e2e, report
from harness.cases import load_cases

CASES = load_cases()


@pytest.fixture(scope="module")
def base_url(request, replayed) -> str | None:
    if replayed is not None:
        return None
    if not request.config.getoption("--paid"):
        pytest.skip("end-to-end evals make paid calls; run with --paid, or --replay <run.json>")
    url = request.config.getoption("--base-url").rstrip("/")
    try:
        httpx.get(f"{url}/health", timeout=10).raise_for_status()
    except httpx.HTTPError as error:
        pytest.exit(f"API not reachable at {url} ({error}). Start it with: npm run dev", returncode=2)
    return url


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_e2e(case, base_url, replayed, http, catalogue):
    if replayed is not None:
        if case["id"] not in replayed:
            # Older runs predate cases added later (the Phase 7 adversarial cases).
            pytest.skip(f"{case['id']} is not in the replayed results file")
        status, body = replayed[case["id"]]["status"], replayed[case["id"]]["response"]
    else:
        assert base_url is not None
        status, body = e2e.call_recommend(http, base_url, case)
    result = e2e.score(case, status, body, catalogue)
    report.RESULTS["e2e"][case["id"]] = result

    assert not result["schema_errors"], f"invalid response: {result['schema_errors']}"
    assert not result.get("ungrounded"), f"products outside the search results: {result['ungrounded']}"
    assert not result.get("leaks"), f"leaked: {result['leaks']}"
