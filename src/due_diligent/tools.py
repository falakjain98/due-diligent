"""The screener as tools an LLM can call: get_metrics, run_screen, compare.

Each tool is a plain Python function with a Pydantic model for its inputs. The model only
*asks* for a tool; this module checks the request, runs the function and returns JSON.
Nothing here imports an LLM SDK, so every tool is tested without calling a model.
Outputs describe how companies score on fixed rules. They are not investment advice.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from due_diligent import metrics, screen, storage
from due_diligent.data import CompanyData, DataSource
from due_diligent.models import DISCLAIMER, ScreenRow, TickerScreen
from due_diligent.notes import prompt_input

logger = logging.getLogger(__name__)

# The sector names yfinance uses (the "Sector" column of the ticker list).
SECTORS = (
    "Basic Materials", "Communication Services", "Consumer Cyclical", "Consumer Defensive",
    "Energy", "Financial Services", "Healthcare", "Industrials", "Real Estate",
    "Technology", "Utilities",
)
Sector = Literal[SECTORS]

# 1-5 letters, optionally a class suffix: AAPL, BRK-B, BF.B
TICKER_PATTERN = r"^[A-Z]{1,5}([.-][A-Z]{1,2})?$"

class ToolError(Exception):
    """A tool ran but has no answer (unknown ticker, no saved run). The message goes to the model."""

def _clean_ticker(value: Any) -> Any:
    """' brk.b ' -> 'BRK-B' (yfinance writes class shares with a dash)."""
    return value.strip().upper().replace(".", "-") if isinstance(value, str) else value

# --- inputs: one Pydantic model per tool --------------------------------------------
# extra="forbid" rejects arguments we never asked for (a typo like "tiker"), and the
# Field descriptions become the JSON schema the model reads, so write them for the model.

class GetMetricsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticker: str = Field(description="Stock ticker symbol, for example AAPL or BRK-B.", pattern=TICKER_PATTERN)

    @field_validator("ticker", mode="before")
    @classmethod
    def clean(cls, value: Any) -> Any:
        return _clean_ticker(value)

class RunScreenInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sector: Sector | None = Field(default=None, description="Only companies in this sector. Leave out for all sectors.")
    passes_all_filters: bool = Field(default=False, description="Only companies that pass all three screening filters (P/E, margins, returns).")
    min_net_margin_pct: float | None = Field(default=None, ge=-100, le=100, description="Keep companies whose net margin is above this percentage. 0 means profitable.")
    min_return_on_equity_pct: float | None = Field(default=None, ge=-100, le=1000, description="Keep companies whose return on equity is above this percentage.")
    max_debt_to_equity: float | None = Field(default=None, ge=0, description="Keep companies whose debt-to-equity ratio is below this number.")
    max_pe_ratio: float | None = Field(default=None, gt=0, description="Keep companies whose P/E ratio is below this number.")
    limit: int = Field(default=10, ge=1, le=25, description="How many companies to return, best final rank first.")

    @field_validator("sector", mode="before")
    @classmethod
    def match_sector(cls, value: Any) -> Any:
        """'technology' -> 'Technology'. Anything else is left for the Literal check to reject."""
        if isinstance(value, str):
            for name in SECTORS:
                if value.strip().lower() == name.lower():
                    return name
        return value

class CompareInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tickers: list[str] = Field(min_length=2, max_length=5, description="2 to 5 different ticker symbols.")

    @field_validator("tickers", mode="before")
    @classmethod
    def clean_and_check(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return value
        cleaned = [_clean_ticker(t) for t in value]
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("tickers must all be different")
        return cleaned

    @field_validator("tickers")
    @classmethod
    def each_looks_like_a_ticker(cls, value: list[str]) -> list[str]:
        bad = [t for t in value if not re.fullmatch(TICKER_PATTERN, t)]
        if bad:
            raise ValueError(f"not ticker symbols: {bad}")
        return value


# --- the tools themselves --------------------------------------------------------------

def _score(company: CompanyData) -> TickerScreen:
    """Same scoring as GET /tickers/{symbol}: one company through metrics -> filters -> ranks."""
    df = screen.score(metrics.metrics_table([company]))
    return TickerScreen.from_row(json.loads(df.to_json(orient="records"))[0])


def _fetch(source: DataSource, ticker: str) -> TickerScreen:
    try:
        company = source.get_company(ticker)
    except Exception as error:
        logger.exception("Data source failed for %s", ticker)
        raise ToolError(f"The data source failed for {ticker}; try again later.") from error
    if company.previous_close is None and company.trailing_eps is None:  # yfinance's answer for a made-up symbol
        raise ToolError(f"No data found for ticker {ticker}.")
    return _score(company)


def _summary(scored: TickerScreen | ScreenRow) -> dict:
    """The compact, pre-rounded view the model sees (percentages end in _pct), from week 4's prompt_input."""
    return prompt_input(scored)  # works for ScreenRow too: it only reads ticker, metrics, filters and ranks


def get_metrics(args: GetMetricsInput, source: DataSource) -> dict:
    """Live data for one company: its ratios, which filters it passes, and its ranks."""
    return {**_summary(_fetch(source, args.ticker)), "data": "live from yfinance (cached up to 1 hour)"}


def run_screen(args: RunScreenInput, source: DataSource) -> dict:
    """Filter the latest saved screening run. Reads saved results; never runs the full screen."""
    latest = storage.load_latest_results()
    if latest is None:
        raise ToolError("No saved screening run yet. Ask the user to run the screener first.")
    run_date, df = latest
    companies_in_run = len(df)
    if args.sector is not None:
        df = df[df["Sector"] == args.sector]
    if args.passes_all_filters:
        df = df[df["pe_filter"] & df["margin_filter"] & df["returns_filter"]]
    # Missing values (NaN) fail every comparison, so a company with no data never "passes" a threshold.
    if args.min_net_margin_pct is not None:
        df = df[df["net_margin"] > args.min_net_margin_pct / 100]
    if args.min_return_on_equity_pct is not None:
        df = df[df["return_on_equity"] > args.min_return_on_equity_pct / 100]
    if args.max_debt_to_equity is not None:
        df = df[df["debt_to_equity"] < args.max_debt_to_equity]
    if args.max_pe_ratio is not None:
        df = df[df["pe_ratio"] < args.max_pe_ratio]
    df = df.sort_values("final_rank", kind="stable")
    rows = [ScreenRow.from_row(row) for row in json.loads(df.head(args.limit).to_json(orient="records"))]
    return {
        "run_date": run_date,
        "companies_in_run": companies_in_run,
        "filters_used": args.model_dump(exclude_defaults=True),
        "matches": len(df),
        "results": [{"name": row.name, "sector": row.sector, **_summary(row)} for row in rows],
    }


def compare(args: CompareInput, source: DataSource) -> dict:
    """Live data for 2-5 companies side by side. A ticker that fails is listed, not fatal."""
    companies, failed = [], []
    for ticker in args.tickers:
        try:
            companies.append(_summary(_fetch(source, ticker)))
        except ToolError as error:
            failed.append(str(error))
    if not companies:
        raise ToolError(" ".join(failed))
    return {"companies": companies, "failed": failed, "data": "live from yfinance (cached up to 1 hour)"}


# --- the registry: what the model is told, and how a request is run ----------------------

@dataclass(frozen=True)
class Tool:
    name: str
    description: str  # the model decides when to call a tool from this, so say when to use it
    input_model: type[BaseModel]
    run: Callable[[Any, DataSource], dict]


TOOLS = {tool.name: tool for tool in [
    Tool("get_metrics",
         "Look up ONE company's live screening result: P/E, margins, returns, debt-to-equity, "
         "capex-to-income, which filters it passes, and its ranks. Use only when the question is about "
         "a single company. For two or more companies, use compare.",
         GetMetricsInput, get_metrics),
    Tool("run_screen",
         "Filter the latest saved screening run by sector and thresholds, best final rank first. "
         "Use for 'which companies...' questions. Covers only the companies in that saved run.",
         RunScreenInput, run_screen),
    Tool("compare",
         "Look up 2 to 5 companies' live screening results side by side in one call. "
         "Use this whenever the question names more than one company.",
         CompareInput, compare),
]}


def openai_tools() -> list[dict]:
    """The tool list in OpenAI's Responses API format. The JSON schema comes from each Pydantic model."""
    return [
        {"type": "function", "name": tool.name, "description": tool.description,
         "parameters": tool.input_model.model_json_schema(),
         # strict=True would need every field required; we validate with Pydantic instead (see the guide).
         "strict": False}
        for tool in TOOLS.values()
    ]


def _short(error: ValidationError) -> str:
    """Pydantic's error list as one line the model can act on: 'ticker: String should match pattern ...'."""
    return "; ".join(f"{'.'.join(str(p) for p in e['loc']) or 'arguments'}: {e['msg']}" for e in error.errors())


def call_tool(name: str, arguments: str, source: DataSource) -> dict:
    """Run one tool request from the model. Never raises: problems come back as {"error": ...}.

    Returning the error (instead of crashing) lets the model fix its arguments and try again,
    or tell the user what went wrong.
    """
    tool = TOOLS.get(name)
    if tool is None:
        return {"error": f"Unknown tool {name!r}. Available tools: {', '.join(TOOLS)}."}
    try:
        args = tool.input_model.model_validate_json(arguments or "{}")
    except ValidationError as error:
        return {"error": f"Invalid arguments for {name}: {_short(error)}"}
    try:
        result = tool.run(args, source)
    except ToolError as error:
        return {"error": str(error)}
    except Exception:
        logger.exception("Tool %s failed", name)
        return {"error": f"{name} failed unexpectedly; try again later."}
    return {**result, "disclaimer": DISCLAIMER}