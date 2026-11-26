"""XBRL check tests, on a tiny hand-written company facts file."""
from due_diligent.edgar import Filing
from due_diligent.extract import Extraction, FilingExtract
from due_diligent.xbrl import (
    check_extraction, compare_number, fact_value, match_rate, xbrl_total_debt,
)

FILING = Filing("AAPL", 320193, "Apple Inc.", "10-K", "0000320193-25-000079",
                "2025-10-31", "2025-09-27", "aapl-20250927.htm")
ACCN = FILING.accession


def fact(val, end="2025-09-27", start=None, accn=ACCN, fy=2025):
    item = {"end": end, "val": val, "accn": accn, "fy": fy, "fp": "FY", "form": "10-K"}
    return item | ({"start": start} if start else {})


FACTS = {"facts": {"us-gaap": {
    "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
        fact(391_035e6, end="2024-09-28", start="2023-10-01"),        # last year, same filing
        fact(102_466e6, start="2025-06-29"),                            # just Q4
        fact(416_161e6, start="2024-09-29"),                            # the full year we want
        fact(416_161e6, start="2024-09-29", accn="0000320193-26-000001"),  # repeated in a later filing
    ]}},
    "NetIncomeLoss": {"units": {"USD": [fact(112_010e6, start="2024-09-29")]}},
    "CommercialPaper": {"units": {"USD": [fact(8_000e6)]}},
    "LongTermDebtCurrent": {"units": {"USD": [fact(12_000e6)]}},
    "LongTermDebtNoncurrent": {"units": {"USD": [fact(80_000e6)]}},
}}}


def test_picks_full_year_from_this_filing():
    value = fact_value(FACTS, "RevenueFromContractWithCustomerExcludingAssessedTax", FILING, full_year=True)
    assert value == 416_161e6


def test_total_debt_adds_the_parts():
    assert xbrl_total_debt(FACTS, FILING) == (
        100_000e6, "LongTermDebtCurrent+LongTermDebtNoncurrent+CommercialPaper")


def test_compare_number_tolerance():
    assert compare_number(100.5, 100) == ("match", 0.5)
    assert compare_number(103, 100) == ("mismatch", 3.0)
    assert compare_number(None, 100) == ("missing_extracted", None)
    assert compare_number(100, None) == ("missing_xbrl", None)


def test_check_extraction_end_to_end():
    risk = {"title": "t", "quote": "q"}
    data = FilingExtract(
        company_name="Apple Inc.", fiscal_year=2025, fiscal_year_end="2025-09-27",
        revenue={"as_written": "416,161", "scale": "millions"},
        net_income={"as_written": "112,010", "scale": "millions"},
        total_debt={"as_written": "92,000", "scale": "millions"},  # left out commercial paper
        segments=[], top_risks=[risk] * 5, guidance=None, guidance_quote=None,
    )
    extraction = Extraction(ticker="AAPL", accession=ACCN, provider="openai", model="m", prompt_version="v1",
                            used_sections=True, data=data, input_tokens=1, output_tokens=1, latency_s=1)
    checks = {check.field: check.status for check in check_extraction(extraction, FACTS, FILING)}
    assert checks == {"fiscal_year": "match", "fiscal_year_end": "match", "revenue": "match",
                      "net_income": "match", "total_debt": "mismatch"}
    assert match_rate(check_extraction(extraction, FACTS, FILING)) == 0.8

def test_non_current_debt_falls_back_to_the_capital_lease_name():
    facts = {"facts": {"us-gaap": {
        "LongTermDebtCurrent": {"units": {"USD": [fact(3_152e6)]}},
        "LongTermDebtAndCapitalLeaseObligations": {"units": {"USD": [fact(61_984e6)]}},
    }}}
    assert xbrl_total_debt(facts, FILING) == (
        65_136e6, "LongTermDebtCurrent+LongTermDebtAndCapitalLeaseObligations")