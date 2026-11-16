"""HTTP API over the screener. Run with: uvicorn due_diligent.api:app --reload"""
from __future__ import annotations

import json
import logging

from fastapi import Depends, FastAPI, HTTPException

from due_diligent import metrics, screen
from due_diligent.data import CompanyData, DataSource, YFinanceSource
from due_diligent.models import TickerScreen

logger = logging.getLogger(__name__)

app = FastAPI(
    title="due-diligent",
    description="Screens companies on fundamentals. Research output only, not investment advice.",
    version="0.1.0",
)

_source = YFinanceSource()


def get_source() -> DataSource:
    """Which data source the endpoints use. Tests swap this for a fake one."""
    return _source


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check: answers if the server is up. Touches no data."""
    return {"status": "ok"}


@app.get("/tickers/{symbol}")
def get_ticker(symbol: str, source: DataSource = Depends(get_source)) -> TickerScreen:
    """Fetch one company, score it against the screening rules, and return the result."""
    symbol = symbol.upper()
    try:
        company = source.get_company(symbol)
    except Exception:
        logger.exception("Data source failed for %s", symbol)
        raise HTTPException(status_code=502, detail=f"Data source failed for {symbol}; try again later")
    if _looks_empty(company):
        raise HTTPException(status_code=404, detail=f"No data found for ticker {symbol}")

    df = screen.score(metrics.metrics_table([company]))
    # to_json turns pandas NaN into null and numpy numbers into plain ones;
    # json.loads gives back a dict that Pydantic accepts.
    row = json.loads(df.to_json(orient="records"))[0]
    return TickerScreen.from_row(row)


def _looks_empty(company: CompanyData) -> bool:
    """yfinance returns mostly empty data for a made-up symbol instead of raising."""
    return company.previous_close is None and company.trailing_eps is None