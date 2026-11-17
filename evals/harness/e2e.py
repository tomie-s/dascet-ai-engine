"""End-to-end eval: send the case's turns to POST /recommend and check the response.
Each call is one paid agent run."""

import httpx

from harness.checks import (
    banned_phrases,
    canada_only_ok,
    echoed_numbers,
    flag_results,
    prompt_leaks,
    relevance,
    unreturned_mentions,
)

REQUEST_TIMEOUT_S = 120


def call_recommend(client: httpx.Client, base_url: str, case: dict) -> tuple[int, object]:
    response = client.post(
        f"{base_url}/recommend", json={"turns": case["turns"]}, timeout=REQUEST_TIMEOUT_S
    )
    try:
        body = response.json()
    except ValueError:
        body = response.text
    return response.status_code, body


def _schema_errors(body: object) -> list[str]:
    if not isinstance(body, dict):
        return ["response is not a JSON object"]
    kind = body.get("type")
    if kind == "recommendation":
        tools = body.get("tools")
        if not isinstance(tools, list) or not tools:
            return ["recommendation has no tools"]
        errors = [
            f"tool {i} is missing a non-empty {field}"
            for i, tool in enumerate(tools)
            for field in ("id", "name", "why")
            if not (isinstance(tool, dict) and isinstance(tool.get(field), str) and tool[field].strip())
        ]
        if not (isinstance(body.get("explanation"), str) and body["explanation"].strip()):
            errors.append("recommendation has no explanation")
        return errors
    if kind == "clarification":
        errors = []
        question = body.get("question")
        if not (isinstance(question, str) and question.strip().endswith("?")):
            errors.append("question must end with '?'")
        choices = body.get("choices")
        if choices is not None and not (isinstance(choices, list) and 2 <= len(choices) <= 5):
            errors.append("choices must have 2 to 5 items")
        return errors
    return [f"unknown response type {kind!r}"]


def _leaks(case: dict, texts: list[str]) -> list[str]:
    """System-prompt markers, and for no_pii_echo cases any long number the user sent."""
    leaks = [f"prompt: {marker}" for marker in prompt_leaks(texts)]
    if "no_pii_echo" in case["flags"]:
        leaks += [f"echoed number ending {number[-3:]}" for number in echoed_numbers(case, texts)]
    return leaks


def score(case: dict, status: int, body: object, catalogue: dict[str, dict]) -> dict:
    result: dict = {"status": status, "response": body}
    # Present only when the API runs with EVAL_INCLUDE_USAGE=1.
    result["usage"] = body.get("usage") if isinstance(body, dict) else None
    if status != 200:
        result.update(schema_errors=[f"HTTP {status}"], outcome_ok=False)
        return result

    result["schema_errors"] = _schema_errors(body)
    if result["schema_errors"]:
        result["outcome_ok"] = False
        return result

    assert isinstance(body, dict)  # _schema_errors rejects anything else
    kind = body["type"]
    result["outcome"] = kind
    result["outcome_ok"] = kind in case["expect"]

    if kind == "clarification":
        texts = [body["question"], *body.get("choices", [])]
        result["wording_violations"] = banned_phrases([body["question"]])
        result["ungrounded"] = [
            f"{name} (named in text)" for name in unreturned_mentions(texts, set(), catalogue)
        ]
        result["leaks"] = _leaks(case, texts)
        return result

    tools = body["tools"]
    ids = [tool["id"] for tool in tools]
    texts = [body["explanation"], *(t["why"] for t in tools)]
    result["ungrounded"] = [
        tool["name"]
        for tool in tools
        if tool["id"] not in catalogue or catalogue[tool["id"]]["name"] != tool["name"]
    ] + [
        f"{name} (named in text)"
        for name in unreturned_mentions(texts, {t["name"] for t in tools}, catalogue)
    ]
    result["leaks"] = _leaks(case, texts)
    result["wording_violations"] = banned_phrases(texts)
    result["canada_only_ok"] = canada_only_ok(ids, catalogue)
    result["flags"] = flag_results(case, tools, body["explanation"], catalogue)
    if case["ideal"] or case["categories"] or case["forbidden"] or case["forbidden_categories"]:
        result.update(relevance(case, ids, catalogue))
    return result


def safety_ok(result: dict) -> bool | None:
    """Canada-only, no forbidden products, and every applicable flag passes."""
    if result.get("outcome") != "recommendation":
        return None
    flags = [flag["pass"] for flag in result.get("flags", {}).values() if flag["pass"] is not None]
    return bool(result["canada_only_ok"] and not result.get("forbidden_returned") and all(flags))
