"""Fails when cases.jsonl no longer matches the catalogue, so a renamed or removed
product shows up as a dataset error rather than a retrieval miss."""

import pytest

from harness.cases import load_cases
from harness.catalogue import COUNSELLING_NAME

CASES = load_cases()


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_labelled_products_exist(case, catalogue):
    for product in case["ideal"] + case["forbidden"]:
        row = catalogue.get(product["id"])
        assert row, f"{product['name']} ({product['id']}) is not in the catalogue"
        assert row["name"] == product["name"], f"{product['name']} was renamed to {row['name']}"
        assert row["status"] == "approved", f"{product['name']} is not approved"


def test_labelled_categories_exist(catalogue):
    known = set().union(*(row["category"] for row in catalogue.values()))
    for case in CASES:
        labels = set(case["categories"] + case["required_categories"] + case["forbidden_categories"])
        assert labels <= known, f"{case['id']}: unknown categories {sorted(labels - known)}"


def test_counselling_product_exists(catalogue):
    assert any(row["name"] == COUNSELLING_NAME for row in catalogue.values())
