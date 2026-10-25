"""Turn raw company data into ratios. Pure functions only: no network, no files."""
from __future__ import annotations

import math

import pandas as pd

from due_diligent.data import CompanyData


# --- small helpers -----------------------------------------------------------

def _latest(values: list[float]) -> float | None:
    """Most recent value from a statement list, or None if empty or NaN."""
    if values:
        if not math.isnan(values[0]):
            return values[0]
    return None

def _safe_div(numerator: float | None, denominator: float | None) -> float | None:
    """numerator / denominator, or None if either is missing or denominator is 0."""
    if numerator is None or denominator is None:
        return None
    if denominator == 0:
        return None
    return numerator / denominator

def _period_columns(company: CompanyData) -> dict[str, float | None]:
    """Flatten quarterly/annual statements into one column per period."""
    columns = {}
    for period, statements in [("quarterly", company.quarterly), ("annual", company.annual)]:
        for name, values in statements.items():
            for i in range(4):
                columns[f"{period}_{name}_{i+1}"] = values[i] if i < len(values) else None
    return columns

# --- one function per ratio ----------------------------------------------------

def pe_ratio(price: float | None, eps: float | None) -> float | None:
    """Price-to-earnings: previous close / trailing EPS."""
    return _safe_div(price, eps)

def debt_to_equity(debt: float | None, equity: float | None) -> float | None:
    """Debt-to-equity ratio."""
    # BUG (issue #1): inverted, should be debt / equity. Fix test-first in week 2.
    return _safe_div(equity, debt)

def capex_to_income(capex: float | None, net_income: float | None) -> float | None:
    """Capital expenditure / net income."""
    # BUG (issue #2): capex is negative in yfinance. Fix test-first in week 2.
    return _safe_div(capex, net_income)

# --- one company -> one row ------------------------------------------------------

def company_metrics(company: CompanyData) -> dict:
    """All ratios and per-period values for one company, as one DataFrame row."""
    ratios = {
        "ticker": company.ticker,
        "pe_ratio": pe_ratio(company.previous_close, company.trailing_eps),
        "price_to_book": company.price_to_book,
        "gross_margin": company.gross_margin,
        "net_margin": company.net_margin,
        "return_on_assets": company.return_on_assets,
        "return_on_equity": company.return_on_equity,
        "debt_to_equity": debt_to_equity(_latest(company.quarterly.get("debt", [])), _latest(company.quarterly.get("equity", []))),
        "capex_to_income": capex_to_income(_latest(company.quarterly.get("capex", [])), _latest(company.quarterly.get("net_income", []))),
    }
    return {**ratios, **_period_columns(company)}

def metrics_table(companies: list[CompanyData]) -> pd.DataFrame:
    """One row per company."""
    return pd.DataFrame([company_metrics(c) for c in companies])

# --- needs the whole table ---------------------------------------------------------

def add_group_average(df: pd.DataFrame, value_col: str, group_col: str, new_col: str) -> pd.DataFrame:
    """Add a column with the average of value_col within each group (e.g. sector P/B)."""
    df_copy = df.copy()
    df_copy[new_col] = df_copy.groupby(group_col)[value_col].transform("mean")
    return df_copy