import pandas as pd
import pytest
from fastapi.testclient import TestClient

from due_diligent import cli, config
from due_diligent.api import app, get_source
from due_diligent.data import CompanyData
from test_pipeline import BAD, GOOD, OKAY, FakeSource

# A bank-like company: no capex, no EPS, so several values are missing.
SPARSE = CompanyData(ticker="SPARSE", previous_close=50, return_on_assets=0.01, return_on_equity=0.12)
EMPTY = CompanyData(ticker="EMPTY")  # what yfinance hands back for a made-up symbol

class BrokenSource:
    def get_company(self, ticker: str) -> CompanyData:
        raise ConnectionError("network down")

@pytest.fixture
def client():
    """A test client whose endpoints use the fake source instead of yfinance."""
    app.dependency_overrides[get_source] = lambda: FakeSource({"GOOD": GOOD, "SPARSE": SPARSE, "EMPTY": EMPTY})
    yield TestClient(app)
    app.dependency_overrides.clear()

def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_ticker_good(client):
    response = client.get("/tickers/good")  # lowercase on purpose
    assert response.status_code == 200
    body = response.json()
    assert body["ticker"] == "GOOD"
    assert body["metrics"]["pe_ratio"] == pytest.approx(20)
    assert body["filters"] == {"pe_filter": True, "margin_filter": True, "returns_filter": True}
    assert body["ranks"]["final_rank"] == 4
    assert "not investment advice" in body["disclaimer"].lower()

def test_ticker_missing_values_become_null(client):
    response = client.get("/tickers/SPARSE")
    assert response.status_code == 200
    body = response.json()
    assert body["metrics"]["pe_ratio"] is None
    assert body["metrics"]["capex_to_income"] is None
    assert body["filters"]["pe_filter"] is False
    assert body["ranks"]["capex_to_income_rank"] == 3

def test_ticker_empty_is_404(client):
    assert client.get("/tickers/EMPTY").status_code == 404

def test_ticker_source_error_is_502():
    app.dependency_overrides[get_source] = lambda: BrokenSource()
    try:
        assert TestClient(app).get("/tickers/GOOD").status_code == 502
    finally:
        app.dependency_overrides.clear()

# --- /screen -----------------------------------------------------------------------

@pytest.fixture
def saved_run(tmp_path, monkeypatch):
    """Point storage at tmp_path, then save one real pipeline run there (3 companies, 2 sectors)."""
    pd.DataFrame({
        "Symbol": ["BAD", "OKAY", "GOOD"],
        "Longname": ["Bad Co", "Okay Co", "Good Co"],
        "Sector": ["Energy", "Technology", "Technology"],
        "Industry": ["Oil & Gas", "Software", "Software"],
    }).to_csv(tmp_path / config.TICKERS_FILENAME, index=False)
    monkeypatch.setattr(config, "STORAGE_MODE", "local")
    monkeypatch.setattr(config, "LOCAL_INPUT_DIR", str(tmp_path))
    monkeypatch.setattr(config, "LOCAL_OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr(config, "PAUSE_BETWEEN_TICKERS", 0)
    cli.run(FakeSource({"GOOD": GOOD, "OKAY": OKAY, "BAD": BAD}))
    return tmp_path / "output" / "sp500"

def test_screen_returns_latest_run_best_first(client, saved_run):
    # an older run with only one company: must be ignored
    old = saved_run / "2020-01-01"
    old.mkdir()
    pd.read_csv(next(saved_run.glob(f"*/{config.TICKERS_FILENAME}"))).head(1).to_csv(old / config.TICKERS_FILENAME, index=False)

    response = client.get("/screen")
    assert response.status_code == 200
    body = response.json()
    assert body["run_date"] != "2020-01-01"
    assert body["count"] == 3
    assert [r["ticker"] for r in body["results"]] == ["GOOD", "OKAY", "BAD"]
    assert body["results"][0]["name"] == "Good Co"
    assert body["results"][0]["ranks"]["final_rank"] == 4

def test_screen_sector_filter_is_case_insensitive(client, saved_run):
    body = client.get("/screen", params={"sector": "technology"}).json()
    assert [r["ticker"] for r in body["results"]] == ["GOOD", "OKAY"]
    assert all(r["sector"] == "Technology" for r in body["results"])

def test_screen_unknown_sector_is_empty_list(client, saved_run):
    response = client.get("/screen", params={"sector": "Astrology"})
    assert response.status_code == 200
    assert response.json()["count"] == 0

def test_screen_no_saved_run_is_404(client, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STORAGE_MODE", "local")
    monkeypatch.setattr(config, "LOCAL_OUTPUT_DIR", str(tmp_path / "nothing-here"))
    assert client.get("/screen").status_code == 404