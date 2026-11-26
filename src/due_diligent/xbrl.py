"""Check extracted numbers against the XBRL facts the company filed with the same 10-K.

XBRL is the machine-readable copy of the financial statements. Each fact has a concept name
from the US-GAAP list (like "NetIncomeLoss"), a value, the period it covers, and the accession
number of the filing it came from. That makes it a good answer key, with one catch: companies
pick different concepts for the same idea, so we try a short list in order.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from due_diligent import config
from due_diligent.edgar import Filing
from due_diligent.extract import Extraction

# For each field: the concepts to try, in order. The first one found for this filing wins.
REVENUE_CONCEPTS = [
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
]
NET_INCOME_CONCEPTS = ["NetIncomeLoss", "ProfitLoss"]
# There is no single "total debt" concept, so debt is built from parts (see xbrl_total_debt).
LONG_TERM_DEBT_TOTAL = "LongTermDebt"  # current + non-current, when a company reports it
LONG_TERM_DEBT_CURRENT = ["LongTermDebtCurrent"]
# Broadcom, for one, tags its non-current debt only under the "...AndCapitalLeaseObligations" name
LONG_TERM_DEBT_NONCURRENT = ["LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations"]
SHORT_TERM_DEBT = ["CommercialPaper", "ShortTermBorrowings"]


@dataclass
class FieldCheck:
    ticker: str
    field: str
    extracted: float | str | None
    xbrl: float | str | None
    concept: str | None   # which XBRL concept (or parts) the answer key came from
    status: str           # match | mismatch | missing_extracted | missing_xbrl
    pct_diff: float | None = None


def _usd_facts(facts: dict, concept: str) -> list[dict]:
    return facts.get("facts", {}).get("us-gaap", {}).get(concept, {}).get("units", {}).get("USD", [])


def _is_full_year(fact: dict) -> bool:
    """Income statement facts cover a period; keep about a year, not a quarter."""
    if "start" not in fact:
        return False
    days = (date.fromisoformat(fact["end"]) - date.fromisoformat(fact["start"])).days
    return 350 <= days <= 380


def fact_value(facts: dict, concept: str, filing: Filing, full_year: bool) -> float | None:
    """The value of one concept from this exact filing, for its fiscal year (end = report_date).

    The same 10-K also reports last year's numbers, with the same accession number, so the
    period end has to match too.
    """
    for fact in _usd_facts(facts, concept):
        if fact.get("accn") != filing.accession or fact.get("end") != filing.report_date:
            continue
        if full_year and not _is_full_year(fact):
            continue
        return float(fact["val"])
    return None


def first_value(facts: dict, concepts: list[str], filing: Filing, full_year: bool) -> tuple[float | None, str | None]:
    for concept in concepts:
        value = fact_value(facts, concept, filing, full_year)
        if value is not None:
            return value, concept
    return None, None


def xbrl_total_debt(facts: dict, filing: Filing) -> tuple[float | None, str | None]:
    """Long-term debt (total, or current + non-current) plus any commercial paper or short-term borrowings.

    This is our own definition, close to the one in SYSTEM_PROMPT. Expect a lower match rate
    than revenue: companies define "total debt" differently, so look at every mismatch.
    """
    parts: dict[str, float] = {}
    total = fact_value(facts, LONG_TERM_DEBT_TOTAL, filing, full_year=False)
    if total is not None:
        parts[LONG_TERM_DEBT_TOTAL] = total
    else:
        for concepts in (LONG_TERM_DEBT_CURRENT, LONG_TERM_DEBT_NONCURRENT):
            value, concept = first_value(facts, concepts, filing, full_year=False)
            if value is not None:
                parts[concept] = value
    for concept in SHORT_TERM_DEBT:
        value = fact_value(facts, concept, filing, full_year=False)
        if value is not None:
            parts[concept] = value
    if not parts:
        return None, None
    return sum(parts.values()), "+".join(parts)


def filing_fiscal_year(facts: dict, filing: Filing) -> int | None:
    """The fiscal year SEC records for this filing (every fact from it carries the same 'fy')."""
    for concept in facts.get("facts", {}).get("us-gaap", {}).values():
        for unit_facts in concept.get("units", {}).values():
            for fact in unit_facts:
                if fact.get("accn") == filing.accession and fact.get("fy"):
                    return int(fact["fy"])
    return None


def compare_number(extracted: float | None, xbrl: float | None,
                   tolerance: float = config.XBRL_TOLERANCE) -> tuple[str, float | None]:
    """match if within tolerance (1% by default), else mismatch. Returns (status, % difference)."""
    if xbrl is None:
        return "missing_xbrl", None
    if extracted is None:
        return "missing_extracted", None
    if xbrl == 0:
        return ("match" if extracted == 0 else "mismatch"), None
    pct_diff = abs(extracted - xbrl) / abs(xbrl)
    return ("match" if pct_diff <= tolerance else "mismatch"), round(pct_diff * 100, 2)


def _compare_exact(extracted, xbrl) -> str:
    if xbrl is None:
        return "missing_xbrl"
    if extracted is None:
        return "missing_extracted"
    return "match" if extracted == xbrl else "mismatch"


def check_extraction(extraction: Extraction, facts: dict, filing: Filing) -> list[FieldCheck]:
    """One FieldCheck per checkable field: fiscal year, year end, revenue, net income, total debt."""
    data = extraction.data
    ticker = extraction.ticker
    checks = []

    fiscal_year = filing_fiscal_year(facts, filing)
    checks.append(FieldCheck(ticker, "fiscal_year", data.fiscal_year, fiscal_year, "fy",
                             _compare_exact(data.fiscal_year, fiscal_year)))
    checks.append(FieldCheck(ticker, "fiscal_year_end", data.fiscal_year_end, filing.report_date, "reportDate",
                             _compare_exact(data.fiscal_year_end, filing.report_date)))

    answers = {
        "revenue": first_value(facts, REVENUE_CONCEPTS, filing, full_year=True),
        "net_income": first_value(facts, NET_INCOME_CONCEPTS, filing, full_year=True),
        "total_debt": xbrl_total_debt(facts, filing),
    }
    for name, (xbrl, concept) in answers.items():
        amount = getattr(data, name)
        extracted = amount.dollars() if amount else None
        status, pct_diff = compare_number(extracted, xbrl)
        checks.append(FieldCheck(ticker, name, extracted, xbrl, concept, status, pct_diff))
    return checks


def match_rate(checks: list[FieldCheck]) -> float | None:
    """Share of checks that matched, out of those XBRL could answer (missing_xbrl is left out)."""
    scored = [check for check in checks if check.status != "missing_xbrl"]
    if not scored:
        return None
    return sum(check.status == "match" for check in scored) / len(scored)