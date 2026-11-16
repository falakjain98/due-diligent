"""Shapes of the JSON the API returns. Pydantic checks every reply against these."""
from __future__ import annotations

from pydantic import BaseModel, Field

DISCLAIMER = "Research output from fixed screening rules. Not investment advice."

class Metrics(BaseModel):
    """The ratios the screen is based on. None means the data source had no value."""
    pe_ratio: float | None
    price_to_book: float | None
    gross_margin: float | None
    net_margin: float | None
    return_on_assets: float | None
    return_on_equity: float | None
    debt_to_equity: float | None
    capex_to_income: float | None

class Filters(BaseModel):
    """Pass (True) or fail (False) for each rule. Missing data counts as a fail."""
    pe_filter: bool
    margin_filter: bool
    returns_filter: bool

class Ranks(BaseModel):
    """1 = best, 3 = worst (or missing). final_rank is the sum, so 4 is the best possible."""
    roa_rank: int
    roe_rank: int
    debt_to_equity_rank: int
    capex_to_income_rank: int
    final_rank: int

def _groups(row: dict) -> dict:
    """Split one flat row of the scored table into the three nested groups."""
    return {
        "metrics": Metrics(**{name: row[name] for name in Metrics.model_fields}),
        "filters": Filters(**{name: row[name] for name in Filters.model_fields}),
        "ranks": Ranks(**{name: row[name] for name in Ranks.model_fields}),
    }

class TickerScreen(BaseModel):
    """How one company scores against the screening rules."""
    ticker: str
    metrics: Metrics
    filters: Filters
    ranks: Ranks
    disclaimer: str = Field(default=DISCLAIMER)

    @classmethod
    def from_row(cls, row: dict) -> TickerScreen:
        """Build the nested reply from one flat row of the scored table."""
        return cls(ticker=row["ticker"], **_groups(row))

class ScreenRow(BaseModel):
    """One company in a saved screening run. Same groups as TickerScreen, plus who the company is."""
    ticker: str
    name: str | None
    sector: str | None
    industry: str | None
    metrics: Metrics
    filters: Filters
    ranks: Ranks

    @classmethod
    def from_row(cls, row: dict) -> ScreenRow:
        """Build from one row of the saved results CSV (its columns are Symbol, Longname, Sector, Industry, ...)."""
        return cls(
            ticker=row["Symbol"],
            name=row.get("Longname"),
            sector=row.get("Sector"),
            industry=row.get("Industry"),
            **_groups(row),
        )

class ScreenResponse(BaseModel):
    """The latest saved run, best final_rank first."""
    run_date: str
    sector: str | None
    count: int
    results: list[ScreenRow]
    disclaimer: str = Field(default=DISCLAIMER)