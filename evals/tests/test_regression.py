"""The regression check's rules, tested on made-up results. Free and offline."""

from harness.regression import e2e_regressions, retrieval_regressions

TOLERANCE = {"cases_below_worst_reference": 1, "category_precision_below_worst_reference": 0.02}


def _case(cid: str, required: bool = False) -> dict:
    return {
        "id": cid, "scored": True, "expect": ["recommendation"],
        "ideal": [{"id": "p1", "name": "Product 1"}], "required_categories": ["Banking"] if required else [],
    }


def _result(hit=True, wording_ok=True, safe=True, covered=True) -> dict:
    return {
        "status": 200, "schema_errors": [], "outcome": "recommendation", "outcome_ok": True,
        "ungrounded": [], "wording_violations": [] if wording_ok else ["below"], "canada_only_ok": True,
        "forbidden_returned": [], "missing_categories": [] if covered else ["Banking"],
        "flags": {"includes_counselling": {"pass": safe}}, "hit": hit, "category_precision": 1.0,
    }


CASES = {f"c{i}": _case(f"c{i}", required=(i == 0)) for i in range(5)}


def _run(**misses) -> dict[str, dict]:
    """A run where the named check fails for the listed case IDs, e.g. hit=["c1"]."""
    return {
        cid: _result(
            hit=cid not in misses.get("hit", []),
            wording_ok=cid not in misses.get("wording", []),
            safe=cid not in misses.get("safety", []),
            covered=cid not in misses.get("coverage", []),
        )
        for cid in CASES
    }


def test_a_run_like_the_reference_passes():
    regressions, new = e2e_regressions(_run(), [_run(), _run()], CASES, TOLERANCE)
    assert regressions == [] and new == []


def test_one_case_below_the_worst_reference_run_is_allowed():
    references = [_run(), _run(hit=["c1"])]  # worst reference: 4 of 5 hits
    regressions, new = e2e_regressions(_run(hit=["c1", "c2"]), references, CASES, TOLERANCE)
    assert regressions == []
    assert new == ["c2: no ideal product"]


def test_two_cases_below_the_worst_reference_run_fail_and_name_the_cases():
    references = [_run(), _run(hit=["c1"])]
    regressions, _ = e2e_regressions(_run(hit=["c1", "c2", "c3"]), references, CASES, TOLERANCE)
    assert len(regressions) == 1
    assert regressions[0].startswith("e2e hit: 2/5 passed, below the limit of 3")
    assert "c1, c2, c3" in regressions[0]


def test_any_safety_failure_fails():
    regressions, new = e2e_regressions(_run(safety=["c4"]), [_run()], CASES, TOLERANCE)
    assert regressions == ["e2e safety: failed for c4 (every case must pass)"]
    assert new == ["c4: includes_counselling"]


def test_a_wording_failure_seen_in_a_reference_run_is_not_new():
    regressions, new = e2e_regressions(_run(wording=["c3"]), [_run(wording=["c3"])], CASES, TOLERANCE)
    assert regressions == [] and new == []


def test_retrieval_regressions():
    snapshot = {
        "a": {"hit": True, "no_match_ok": None, "forbidden": []},
        "b": {"hit": None, "no_match_ok": True, "forbidden": []},
    }
    current = {
        "a": {"hit": False, "returned": [{"name": "Other"}], "forbidden_returned": ["Bad"]},
        "b": {"no_match_ok": False, "returned": [{"name": "Recipe app"}]},
    }
    assert retrieval_regressions(current, snapshot) == [
        "retrieval a: lost its ideal product; now ['Other']",
        "retrieval a: now returns forbidden ['Bad']",
        "retrieval b: off-topic request now returns ['Recipe app']",
    ]
    unchanged = {
        "a": {"hit": True, "returned": [{"name": "Product 1"}], "forbidden_returned": []},
        "b": {"no_match_ok": True, "returned": []},
    }
    assert retrieval_regressions(unchanged, snapshot) == []
