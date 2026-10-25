"""Decide pass/fail and rank. Takes and returns DataFrames; no network, no files."""
from __future__ import annotations

import pandas as pd

from due_diligent import config


# --- before fetching: which tickers are worth fetching at all ----------------------

def clean_universe(tickers: pd.DataFrame) -> pd.DataFrame:
    """Drop tickers with no sector/industry and excluded industries (blank checks)."""
    tickers = tickers.dropna(subset=["Sector", "Industry"])
    tickers = tickers[~tickers["Industry"].isin(config.EXCLUDED_INDUSTRIES)]
    return tickers

# --- filters: each returns a True/False Series, one value per row ------------------

def pe_filter(df: pd.DataFrame) -> pd.Series:
    """P/E strictly between PE_MIN and PE_MAX (main.py line 36)."""
    return (df["pe_ratio"] > config.PE_MIN) & (df["pe_ratio"] < config.PE_MAX)

def pb_filter(df: pd.DataFrame) -> pd.Series:
    """P/B under PB_MAX, or under its sector average (main.py line 46)."""
    # BUG (issue #3): OR lets almost everything pass. Copy as is; decide in week 2.
    return (df["price_to_book"] < config.PB_MAX) | (df["price_to_book"] < df["sector_avg_pb"])

def margin_filter(df: pd.DataFrame) -> pd.Series:
    """Gross and net margin both above their minimums (main.py line 54)."""
    return (df["gross_margin"] > config.GROSS_MARGIN_MIN) & (df["net_margin"] > config.NET_MARGIN_MIN)

def returns_filter(df: pd.DataFrame) -> pd.Series:
    """ROA and ROE both above their minimums (main.py line 62)."""
    return (df["return_on_assets"] > config.ROA_MIN) & (df["return_on_equity"] > config.ROE_MIN)

def add_filter_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add one True/False column per filter. Does not drop any rows (matches old behavior)."""
    df = df.copy()
    df["pe_filter"] = pe_filter(df)
    df["pb_filter"] = pb_filter(df)
    df["margin_filter"] = margin_filter(df)
    df["returns_filter"] = returns_filter(df)
    return df

# --- ranking -----------------------------------------------------------------

def _bucket(values: pd.Series, cutoffs: tuple[float, float], higher_is_better: bool) -> pd.Series:
    """Score each value 1 (best), 2 or 3 using two cutoffs."""
    if higher_is_better:
        return pd.cut(values, bins=[-float("inf"), cutoffs[1], cutoffs[0], float("inf")], labels=[3, 2, 1], right=higher_is_better).astype(float).fillna(3).astype(int)
    else:
        return pd.cut(values, bins=[-float("inf"), cutoffs[0], cutoffs[1], float("inf")], labels=[1, 2, 3], right=higher_is_better).astype(float).fillna(3).astype(int)

def add_ranks(df: pd.DataFrame) -> pd.DataFrame:
    """Add the four rank columns and final_rank (their sum), sorted best first."""
    df = df.copy()
    df["roa_rank"] = _bucket(df["return_on_assets"], config.ROA_RANK_CUTOFFS, higher_is_better=True)
    df["roe_rank"] = _bucket(df["return_on_equity"], config.ROE_RANK_CUTOFFS, higher_is_better=True)
    df["debt_to_equity_rank"] = _bucket(df["debt_to_equity"], config.DEBT_TO_EQUITY_RANK_CUTOFFS, higher_is_better=False)
    df["capex_to_income_rank"] = _bucket(df["capex_to_income"], config.CAPEX_TO_INCOME_RANK_CUTOFFS, higher_is_better=False)
    df["final_rank"] = df[["roa_rank", "roe_rank", "debt_to_equity_rank", "capex_to_income_rank"]].sum(axis=1)
    return df.sort_values("final_rank")