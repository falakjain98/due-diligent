import pytest
from fastapi.testclient import TestClient

from due_diligent.api import app, get_source
from due_diligent.data import CompanyData
from test_pipeline import GOOD, FakeSource

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