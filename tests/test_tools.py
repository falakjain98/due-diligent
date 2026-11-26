import json

import pandas as pd
import pytest

from due_diligent import cli, config, tools
from due_diligent.data import CompanyData
from test_api import BrokenSource
from test_pipeline import BAD, GOOD, OKAY, FakeSource

EMPTY = CompanyData(ticker="EMPTY")  # what yfinance hands back for a made-up symbol
SOURCE = FakeSource({"GOOD": GOOD, "OKAY": OKAY, "BAD": BAD, "EMPTY": EMPTY})


def call(name: str, **arguments) -> dict:
    return tools.call_tool(name, json.dumps(arguments), SOURCE)


@pytest.fixture
def saved_run(tmp_path, monkeypatch):
    """A saved screening run of GOOD (Technology), OKAY (Technology) and BAD (Healthcare)."""
    pd.DataFrame({
        "Symbol": ["GOOD", "OKAY", "BAD"],
        "Longname": ["Good Co", "Okay Co", "Bad Co"],
        "Sector": ["Technology", "Technology", "Healthcare"],
        "Industry": ["Software"] * 3,
    }).to_csv(tmp_path / config.TICKERS_FILENAME, index=False)
    monkeypatch.setattr(config, "STORAGE_MODE", "local")
    monkeypatch.setattr(config, "LOCAL_INPUT_DIR", str(tmp_path))
    monkeypatch.setattr(config, "LOCAL_OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr(config, "PAUSE_BETWEEN_TICKERS", 0)
    cli.run(SOURCE)


# --- the schemas the model sees -----------------------------------------------------

def test_openai_tools_lists_every_tool_with_a_schema():
    specs = tools.openai_tools()
    assert [s["name"] for s in specs] == ["get_metrics", "run_screen", "compare"]
    for spec in specs:
        assert spec["type"] == "function"
        assert spec["description"]
        assert spec["parameters"]["additionalProperties"] is False
    sector = specs[1]["parameters"]["properties"]["sector"]
    assert "Technology" in json.dumps(sector)  # the model is told the allowed sector names


# --- get_metrics ---------------------------------------------------------------------

def test_get_metrics_returns_rounded_percentages_and_disclaimer():
    result = call("get_metrics", ticker="good")  # lowercase on purpose
    assert result["ticker"] == "GOOD"
    assert result["metrics"]["pe_ratio"] == 20
    assert result["metrics"]["net_margin_pct"] == 20.0
    assert result["ranks"]["final_rank"] == 4
    assert "not investment advice" in result["disclaimer"].lower()


def test_get_metrics_unknown_ticker_is_an_error_not_a_crash():
    assert call("get_metrics", ticker="EMPTY") == {"error": "No data found for ticker EMPTY."}


def test_get_metrics_source_failure_is_an_error():
    result = tools.call_tool("get_metrics", '{"ticker": "GOOD"}', BrokenSource())
    assert "data source failed" in result["error"]


@pytest.mark.parametrize("arguments", [
    '{"ticker": "NOT A TICKER"}',          # fails the pattern
    '{"symbol": "AAPL"}',                  # wrong field name
    '{"ticker": "AAPL", "period": "1y"}',  # extra field
    '{"ticker": ',                         # broken JSON
])
def test_bad_arguments_come_back_as_errors(arguments):
    result = tools.call_tool("get_metrics", arguments, SOURCE)
    assert result["error"].startswith("Invalid arguments for get_metrics")


def test_unknown_tool_is_an_error():
    assert "Unknown tool" in tools.call_tool("buy_stock", "{}", SOURCE)["error"]


def test_class_share_tickers_are_cleaned():
    assert tools.GetMetricsInput(ticker=" brk.b ").ticker == "BRK-B"


# --- run_screen ------------------------------------------------------------------------

def test_run_screen_sector_and_debt_filter(saved_run):
    # "Which profitable tech stocks have debt-to-equity under 1?"
    result = call("run_screen", sector="technology", min_net_margin_pct=0, max_debt_to_equity=1)
    assert result["companies_in_run"] == 3
    assert result["matches"] == 1
    assert [r["ticker"] for r in result["results"]] == ["GOOD"]
    assert result["filters_used"] == {"sector": "Technology", "min_net_margin_pct": 0, "max_debt_to_equity": 1}


def test_run_screen_passes_all_filters_and_limit(saved_run):
    assert [r["ticker"] for r in call("run_screen", passes_all_filters=True)["results"]] == ["GOOD", "OKAY"]
    limited = call("run_screen", limit=1)
    assert limited["matches"] == 3 and len(limited["results"]) == 1


def test_run_screen_empty_sector_is_zero_matches_not_an_error(saved_run):
    result = call("run_screen", sector="Utilities")
    assert result["matches"] == 0 and result["results"] == []


def test_run_screen_rejects_unknown_sector(saved_run):
    assert "sector" in call("run_screen", sector="Crypto")["error"]


def test_run_screen_without_a_saved_run(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STORAGE_MODE", "local")
    monkeypatch.setattr(config, "LOCAL_OUTPUT_DIR", str(tmp_path))
    assert "No saved screening run" in call("run_screen")["error"]


# --- compare -------------------------------------------------------------------------

def test_compare_two_companies():
    result = call("compare", tickers=["GOOD", "BAD"])
    assert [c["ticker"] for c in result["companies"]] == ["GOOD", "BAD"]
    assert result["failed"] == []


def test_compare_lists_a_failed_ticker_and_keeps_the_rest():
    result = call("compare", tickers=["GOOD", "EMPTY"])
    assert [c["ticker"] for c in result["companies"]] == ["GOOD"]
    assert result["failed"] == ["No data found for ticker EMPTY."]


@pytest.mark.parametrize("tickers", [["GOOD"], ["GOOD", "good"], ["A", "B", "C", "D", "E", "F"]])
def test_compare_needs_2_to_5_different_tickers(tickers):
    assert "error" in call("compare", tickers=tickers)