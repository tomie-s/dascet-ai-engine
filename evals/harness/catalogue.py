"""One free read of the catalogue fields the checks need."""

import httpx

COUNSELLING_NAME = "Credit Counselling Society"
CREDIT_MONITORING_NAMES = {"Borrowell", "Credit Karma"}
LENDER_CATEGORY = "Credit & Loans"


class ServiceError(RuntimeError):
    """An HTTP failure reported without request headers, so keys never reach the output."""


def check_response(response: httpx.Response, service: str) -> None:
    if response.is_success:
        return
    detail = response.text[:300].replace("\n", " ")
    raise ServiceError(f"{service} returned HTTP {response.status_code}: {detail}")


def fetch_catalogue(client: httpx.Client, supabase_url: str, service_key: str) -> dict[str, dict]:
    response = client.get(
        f"{supabase_url}/rest/v1/financial_tools",
        params={"select": "id,name,category,canadian_available,status,tagline,description,key_features"},
        headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
    )
    check_response(response, "Supabase catalogue read")
    return {row["id"]: row for row in response.json()}


def is_lender(product: dict) -> bool:
    """Products that extend credit: everything in Credit & Loans except counselling and monitoring."""
    return (
        LENDER_CATEGORY in product["category"]
        and product["name"] != COUNSELLING_NAME
        and product["name"] not in CREDIT_MONITORING_NAMES
    )
