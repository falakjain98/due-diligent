"""Fetch raw company data from external sources.

Nothing in this module calculates ratios or makes screening decisions.
"""

# imports
from __future__ import annotations

import logging
from typing import Protocol
from dataclasses import dataclass, field

import pandas as pd
import yfinance as yf

# logging
logger = logging.getLogger(__name__)

# Row labels in yfinance's statement tables (copied from old get_financials.py).
# Keeping them in one place means one edit if yfinance renames a row.
INCOME_ROWS = {
    "net_income": "Net Income",
    "revenue": "Total Revenue",
    "r_and_d": "Research And Development",
}
BALANCE_ROWS = {
    "debt": "Total Debt",
    "retained_earnings": "Retained Earnings",
    "equity": "Stockholders Equity",
}
CASHFLOW_ROWS = {
    "capex": "Capital Expenditure",
}

@dataclass
class CompanyData:
    """Raw company data fetched from external sources.

    Attributes:
        ticker: The stock ticker symbol.
        previous_close: The previous closing price of the stock.
        trailing_eps: The trailing earnings per share.
        price_to_book: The price-to-book ratio.
        gross_margin: The gross margin percentage.
        net_margin: The net margin percentage.
        return_on_assets: The return on assets percentage.
        return_on_equity: The return on equity percentage.
        quarterly: A dictionary containing quarterly financial data, with keys as row labels and values as lists of floats.
        annual: A dictionary containing annual financial data, with keys as row labels and values as lists
    """
    ticker: str
    # from .info: single values
    previous_close: float | None = None
    trailing_eps: float | None = None
    price_to_book: float | None = None
    gross_margin: float | None = None
    net_margin: float | None = None
    return_on_assets: float | None = None
    return_on_equity: float | None = None
    # from statements: most recent first, upto 4 periods each
    quarterly: dict[str, list[float]] = field(default_factory=dict)
    annual: dict[str, list[float]] = field(default_factory=dict)

class DataSource(Protocol):
    """Protocol for a data source that fetches company data."""

    def get_company(self, ticker: str) -> CompanyData:
        """Fetch raw company data for the given ticker.

        Args:
            ticker: The stock ticker symbol.

        Returns:
            A CompanyData object containing the fetched data.
        """

class YFinanceSource:
    def get_company(self, ticker: str) -> CompanyData:
        """Fetch raw company data for the given ticker using yfinance.

        Args:
            ticker: The stock ticker symbol.
        """
        company_data = CompanyData(ticker=ticker)
        data = yf.Ticker(ticker)
        info = data.info
        company_data.previous_close = _info_values(info, "previousClose", ticker)
        company_data.trailing_eps = _info_values(info, "trailingEps", ticker)
        company_data.price_to_book = _info_values(info, "priceToBook", ticker)
        company_data.gross_margin = _info_values(info, "grossMargins", ticker)
        company_data.net_margin = _info_values(info, "profitMargins", ticker)
        company_data.return_on_assets = _info_values(info, "returnOnAssets", ticker)
        company_data.return_on_equity = _info_values(info, "returnOnEquity", ticker)

        # quarterly statements        
        quarterly_financials = data.quarterly_financials
        quarterly_balance_sheet = data.quarterly_balance_sheet
        quarterly_cashflow = data.quarterly_cashflow

        # annual statements
        annual_financials = data.financials
        annual_balance_sheet = data.balance_sheet
        annual_cashflow = data.cashflow

        company_data.quarterly = {
            "net_income": _last_4(quarterly_financials, INCOME_ROWS["net_income"], ticker),
            "revenue": _last_4(quarterly_financials, INCOME_ROWS["revenue"], ticker),
            "r_and_d": _last_4(quarterly_financials, INCOME_ROWS["r_and_d"], ticker),
            "debt": _last_4(quarterly_balance_sheet, BALANCE_ROWS["debt"], ticker),
            "retained_earnings": _last_4(quarterly_balance_sheet, BALANCE_ROWS["retained_earnings"], ticker),
            "equity": _last_4(quarterly_balance_sheet, BALANCE_ROWS["equity"], ticker),
            "capex": _last_4(quarterly_cashflow, CASHFLOW_ROWS["capex"], ticker),
        }
        company_data.annual = {
            "net_income": _last_4(annual_financials, INCOME_ROWS["net_income"], ticker),
            "revenue": _last_4(annual_financials, INCOME_ROWS["revenue"], ticker),
            "r_and_d": _last_4(annual_financials, INCOME_ROWS["r_and_d"], ticker),
            "debt": _last_4(annual_balance_sheet, BALANCE_ROWS["debt"], ticker),
            "retained_earnings": _last_4(annual_balance_sheet, BALANCE_ROWS["retained_earnings"], ticker),
            "equity": _last_4(annual_balance_sheet, BALANCE_ROWS["equity"], ticker),
            "capex": _last_4(annual_cashflow, CASHFLOW_ROWS["capex"], ticker),
        }

        return company_data
        
# helpers
def _info_values(info: dict, key: str, ticker: str) -> float | None:
    """Get a single value from the yfinance info dict.

    Args:
        info: The yfinance info dictionary.
        key: The key to look up in the info dictionary.
        ticker: The stock ticker symbol (for logging).
    """
    value = info.get(key)
    if value is None:
        logger.warning("Missing %s for %s", key, ticker)
    return value

def _last_4(statement: pd.DataFrame, row: str, ticker: str) -> list[float]:
    """Get the last 4 values for a given row label from a financial statement.

    Args:
        statement: The financial statement DataFrame.
        row: The label of the row to fetch.
        ticker: The stock ticker symbol (for logging).

    Returns:
        A list of the last 4 values for the specified row or an empty list if the row is missing.
    """
    if row not in statement.index:
        logger.warning("Missing row %s for %s", row, ticker)
        return []
    values = statement.loc[row].tolist()
    if len(values) < 4:
        logger.warning("Insufficient data for %s for %s", row, ticker)
    return values[:4]

if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)
    source = YFinanceSource()
    company_data = source.get_company("JPM")
    print(company_data)
