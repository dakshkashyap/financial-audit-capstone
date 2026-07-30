"""
SEC EDGAR XBRL Company Facts client.

No API key required. Public data.sec.gov endpoints only need a declared
User-Agent (name + email) and ≤10 requests/second.
"""

from __future__ import annotations

import time
from typing import Any

import pandas as pd
import requests


# ── SEC identity header (required — not an API key) ───────────────────────────
HEADERS = {
    "User-Agent": "Irvin Cardoza irvin.cardoza@sfu.ca",
    "Accept-Encoding": "gzip, deflate",
    "Accept": "application/json",
}

TIMEOUT_SECONDS = 30
RATE_LIMIT_SLEEP = 0.15  # ~6–7 req/s, under SEC's 10/s limit


def sec_get_json(url: str) -> dict[str, Any]:
    """Download JSON from an SEC endpoint."""
    response = requests.get(url, headers=HEADERS, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    time.sleep(RATE_LIMIT_SLEEP)
    return response.json()


def find_company(ticker: str) -> dict[str, Any]:
    """Find a company in the SEC ticker → CIK list."""
    url = "https://www.sec.gov/files/company_tickers.json"
    companies = sec_get_json(url)

    normalized = ticker.strip().upper()
    for company in companies.values():
        if company["ticker"].upper() == normalized:
            return company

    raise ValueError(f"Ticker not found: {normalized}")


def get_company_facts(cik: int | str) -> dict[str, Any]:
    """Download all standardized XBRL facts for a company."""
    padded_cik = str(cik).zfill(10)
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{padded_cik}.json"
    return sec_get_json(url)


def list_concepts(
    company_facts: dict[str, Any],
    taxonomy: str = "us-gaap",
    search: str | None = None,
) -> list[str]:
    """List available XBRL concept names (optionally filtered by search term)."""
    taxonomy_facts = company_facts["facts"].get(taxonomy, {})
    names = sorted(taxonomy_facts.keys())
    if search:
        needle = search.lower()
        names = [n for n in names if needle in n.lower()]
    return names


def get_concept_dataframe(
    company_facts: dict[str, Any],
    concept_name: str,
    taxonomy: str = "us-gaap",
    unit: str = "USD",
) -> pd.DataFrame:
    """Convert one XBRL concept into a DataFrame."""
    taxonomy_facts = company_facts["facts"].get(taxonomy, {})

    if concept_name not in taxonomy_facts:
        available = [
            name for name in taxonomy_facts
            if concept_name.lower() in name.lower()
        ]
        raise KeyError(
            f"Concept '{concept_name}' was not found. "
            f"Possible matches: {available[:20]}"
        )

    concept = taxonomy_facts[concept_name]
    units = concept["units"]

    if unit not in units:
        raise KeyError(
            f"Unit '{unit}' was not found. "
            f"Available units: {list(units)}"
        )

    return pd.DataFrame(units[unit])


def filter_annual_10k(df: pd.DataFrame) -> pd.DataFrame:
    """Keep annual 10-K / 10-K/A fiscal-year rows, latest filing per period end."""
    annual = df[
        (df["form"].isin(["10-K", "10-K/A"])) &
        (df["fp"] == "FY")
    ].copy()

    annual = annual.sort_values("filed")
    annual = annual.drop_duplicates(subset=["end"], keep="last")
    return annual.sort_values("end")


def fetch_annual_concept(
    ticker: str,
    concept_name: str,
    unit: str = "USD",
) -> pd.DataFrame:
    """End-to-end: ticker → CIK → companyfacts → annual concept DataFrame."""
    company = find_company(ticker)
    facts = get_company_facts(company["cik_str"])
    df = get_concept_dataframe(facts, concept_name, unit=unit)
    annual = filter_annual_10k(df)

    if "val" in annual.columns:
        annual = annual.copy()
        annual["value_billions"] = annual["val"] / 1_000_000_000

    return annual, company, facts


def main() -> None:
    ticker = "AAPL"
    concept_name = "RevenueFromContractWithCustomerExcludingAssessedTax"

    print(f"Looking up ticker {ticker}…")
    company = find_company(ticker)
    print(f"Found: {company['title']}  CIK={company['cik_str']}")

    print("Downloading companyfacts…")
    company_facts = get_company_facts(company["cik_str"])
    print(f"Entity: {company_facts.get('entityName')}")

    # Show a few revenue-related concepts
    revenue_concepts = list_concepts(company_facts, search="Revenue")
    print(f"\nRevenue-related concepts ({len(revenue_concepts)}):")
    for name in revenue_concepts[:15]:
        print(f"  {name}")
    if len(revenue_concepts) > 15:
        print(f"  … and {len(revenue_concepts) - 15} more")

    print(f"\nExtracting annual 10-K values for:\n  {concept_name}")
    df = get_concept_dataframe(company_facts, concept_name, unit="USD")
    annual = filter_annual_10k(df)
    annual["value_billions"] = annual["val"] / 1_000_000_000

    result_columns = [
        c for c in ["end", "value_billions", "form", "filed", "accn"]
        if c in annual.columns
    ]
    print(annual[result_columns].tail(10).to_string(index=False))

    output_file = f"{ticker.lower()}_{concept_name}.csv"
    annual[result_columns].to_csv(output_file, index=False)
    print(f"\nSaved: {output_file}")


if __name__ == "__main__":
    main()
