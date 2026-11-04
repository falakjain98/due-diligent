import pytest
import pandas as pd

from due_diligent.screen import clean_universe, pe_filter, pb_filter, margin_filter, returns_filter, add_filter_columns, add_ranks, _bucket

def test_clean_universe():
    data = [
        {"ticker": "A", "Sector": None, "Industry": "Banks", "pe_ratio": 10, "price_to_book": 1.5, "gross_margin": 0.4, "net_margin": 0.1, "returns_1y": 0.2},
        {"ticker": "B", "Sector": "Healthcare", "Industry": "Blank Checks", "pe_ratio": None, "price_to_book": 2.0, "gross_margin": 0.5, "net_margin": 0.2, "returns_1y": 0.3},
        {"ticker": "C", "Sector": "Financial", "Industry": "Banks", "pe_ratio": 15, "price_to_book": None, "gross_margin": 0.6, "net_margin": 0.3, "returns_1y": None},
    ]
    df = pd.DataFrame(data)
    cleaned_df = clean_universe(df)
    assert len(cleaned_df) == 1
    assert cleaned_df.iloc[0]["ticker"] == "C"

def test_pe_filter():
    data = [
        {"ticker": "A", "pe_ratio": 0},
        {"ticker": "B", "pe_ratio": 20},
        {"ticker": "C", "pe_ratio": 50},
    ]
    df = pd.DataFrame(data)
    results = pe_filter(df)
    assert len(results) == 3
    assert results.iloc[0] == False
    assert results.iloc[1] == True
    assert results.iloc[2] == False

# def test_pb_filter():
#     data = [
#         {"ticker": "A", "price_to_book": 1.5, "sector_avg_pb": 2.0},
#         {"ticker": "B", "price_to_book": 2.0, "sector_avg_pb": 2.0},
#         {"ticker": "C", "price_to_book": 10.0, "sector_avg_pb": 2.0},
#     ]
#     df = pd.DataFrame(data)
#     results = pb_filter(df)
#     assert len(results) == 3
#     assert results[0] == True
#     assert results[1] == True
#     assert results[2] == False

def test_margin_filter():
    data = [
        {"ticker": "A", "gross_margin": 0.4, "net_margin": 0.1},
        {"ticker": "B", "gross_margin": 0.5, "net_margin": 0.2},
        {"ticker": "C", "gross_margin": 0.6, "net_margin": 0.3},
    ]
    df = pd.DataFrame(data)
    results = margin_filter(df)
    assert len(results) == 3
    assert results.iloc[0] == False
    assert results.iloc[1] == True
    assert results.iloc[2] == True

def test_returns_filter():
    data = [
        {"ticker": "A", "return_on_assets": 0.2, "return_on_equity": 0.1},
        {"ticker": "B", "return_on_assets": 0.3, "return_on_equity": 0.05},
        {"ticker": "C", "return_on_assets": 0.05, "return_on_equity": 0.3},
    ]
    df = pd.DataFrame(data)
    results = returns_filter(df)
    assert len(results) == 3
    assert results.iloc[0] == True
    assert results.iloc[1] == False
    assert results.iloc[2] == False

def test_add_filter_columns():
    data = [
        {"ticker": "A", "pe_ratio": 10, "price_to_book": 1.5, "sector_avg_pb": 2.0, "gross_margin": 0.4, "net_margin": 0.1, "return_on_assets": 0.2, "return_on_equity": 0.1},
        {"ticker": "B", "pe_ratio": 20, "price_to_book": 2.0, "sector_avg_pb": 2.0, "gross_margin": 0.5, "net_margin": 0.2, "return_on_assets": 0.3, "return_on_equity": 0.2},
    ]
    df = pd.DataFrame(data)
    df_with_filters = add_filter_columns(df)
    assert "pe_filter" in df_with_filters.columns
    assert "pb_filter" in df_with_filters.columns
    assert "margin_filter" in df_with_filters.columns
    assert "returns_filter" in df_with_filters.columns

def test_bucket():
    values = pd.Series([0.3, 0.15, 0.05, float("nan")])
    cutoffs = (0.2, 0.1)
    result = _bucket(values, cutoffs, higher_is_better=True)
    assert result.tolist() == [1, 2, 3, 3]