"""The wording and loan-framing checks, pinned to sentences seen in real runs."""

from harness.catalogue import LENDER_CATEGORY
from harness.checks import banned_phrases, flag_results


def test_negated_phrases_are_not_violations():
    assert banned_phrases(["I can't call any app the best, but I can help you explore options."]) == []
    assert banned_phrases(["These are starting points, not a recommendation of what you should do."]) == []


def test_phrases_after_a_clause_break_still_count():
    assert banned_phrases(["No fees, and it's the best option."]) == ["best"]
    assert banned_phrases(["The options below are ones to explore."]) == ["below"]


def test_a_reminder_to_confirm_terms_is_not_advice():
    assert banned_phrases(["It uses tiered fees that you should confirm with the provider."]) == []
    assert banned_phrases(["You should put your savings in this account."]) == ["you should"]


def test_word_boundaries():
    assert banned_phrases(["A key benefit is the fixed rate."]) == []


def _monitoring(why: str) -> bool | None:
    case = {"flags": ["no_monitoring_as_repayment"]}
    tools = [{"id": "b", "name": "Borrowell", "why": why}]
    return flag_results(case, tools, "", {})["no_monitoring_as_repayment"]["pass"]


def test_monitoring_check_allows_saying_it_does_not_repay_debt():
    assert _monitoring("Monitoring shows changes over time, but it does not repay or reduce any debt.") is True
    assert _monitoring("Borrowell helps you pay down your debt faster.") is False


def _loan_case():
    return {"flags": ["loan_framing"]}


def _catalogue():
    return {"loan": {"name": "Fig Financial Personal Loan", "category": [LENDER_CATEGORY]}}


def test_loan_framing_accepts_new_borrowing_wording():
    tools = [{
        "id": "loan",
        "name": "Fig Financial Personal Loan",
        "why": "It adds new debt that you repay over time, and terms, rates, and eligibility vary.",
    }]
    result = flag_results(_loan_case(), tools, "Please confirm all rates.", _catalogue())
    assert result["loan_framing"]["pass"] is True


def test_loan_framing_accepts_new_borrowing_and_repaid():
    tools = [{
        "id": "loan",
        "name": "Fig Financial Personal Loan",
        "why": "It adds new borrowing rather than removing debt, and costs, fees, and eligibility vary.",
    }]
    result = flag_results(_loan_case(), tools, "", _catalogue())
    assert result["loan_framing"]["pass"] is True


def test_loan_framing_accepts_depend_on_and_differ():
    tools = [{
        "id": "loan",
        "name": "Fig Financial Personal Loan",
        "why": "It replaces your existing debts with a new loan rather than eliminating them, and the "
        "rate, fees, and total borrowing cost depend on eligibility and the approved terms.",
    }]
    result = flag_results(_loan_case(), tools, "", _catalogue())
    assert result["loan_framing"]["pass"] is True


def test_loan_framing_needs_cost_variation():
    tools = [{"id": "loan", "name": "Fig Financial Personal Loan", "why": "It consolidates your debts."}]
    result = flag_results(_loan_case(), tools, "", _catalogue())
    assert result["loan_framing"]["pass"] is False
