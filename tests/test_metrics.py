import pytest
import pandas as pd

from due_diligent.metrics import pe_ratio, _safe_div, _latest, _period_columns, company_metrics, add_group_average
from due_diligent.data import CompanyData

def test_safe_div():
    assert _safe_div(10, 2) == 5
    assert _safe_div(10, 0) is None
    assert _safe_div(10, None) is None
    assert _safe_div(None, 2) is None
    assert _safe_div(None, None) is None
    assert _safe_div(10, 3) == pytest.approx(3.3333333333333335)
    assert _safe_div(-10, 2) == -5

def test_latest():
    assert _latest([1, 2, 3]) == 1
    assert _latest([float('nan'), 2, 3]) is None
    assert _latest([]) is None
    assert _latest([float('nan')]) is None

def test_period_columns():
    company = CompanyData(
        ticker="TEST",
        quarterly={"revenue": [100, 200, 300, 400], "net_income": [10, 20, 30, 40]},
        annual={"revenue": [1000, 2000], "net_income": [100, 200]}
    )
    columns = _period_columns(company)
    assert columns["quarterly_revenue_1"] == 100
    assert columns["quarterly_revenue_4"] == 400
    assert columns["annual_net_income_2"] == 200
    assert columns["annual_net_income_3"] is None

def test_pe_ratio():
    assert pe_ratio(100, 5) == 20
    assert pe_ratio(100, 0) is None
    assert pe_ratio(100, None) is None
    assert pe_ratio(None, 5) is None
    assert pe_ratio(None, None) is None
    assert pe_ratio(100, -5) == -20

def test_add_group_average():
    data = [
        {"group": "A", "value": 10},
        {"group": "A", "value": 20},
        {"group": "B", "value": 30},
        {"group": "B", "value": 40},
    ]
    df = pd.DataFrame(data)
    result = add_group_average(df, group_col="group", value_col="value", new_col="average")
    assert result.loc[result["group"] == "A", "average"].iloc[0] == 15
    assert result.loc[result["group"] == "B", "average"].iloc[0] == 35

def test_company_metrics():
    company = CompanyData(
        ticker="TEST",
        previous_close=100,
        trailing_eps=5,
        price_to_book=3,
        gross_margin=0.5,
        net_margin=0.2,
        return_on_assets=0.1,
        return_on_equity=0.15,
        quarterly={"debt": [50, 60, 70, 80], "equity": [100, 110, 120, 130], "capex": [-10, -20, -30, -40], "net_income": [10, 20, 30, 40]},
        annual={"debt": [200, 250], "equity": [300, 350], "capex": [-50, -60], "net_income": [50, 60]}
    )
    metrics = company_metrics(company)
    assert metrics["ticker"] == "TEST"
    assert metrics["pe_ratio"] == 20
    # include after bug fix
    assert metrics["debt_to_equity"] == pytest.approx(0.5)
    # assert metrics["capex_to_income"] == pytest.approx(-1)