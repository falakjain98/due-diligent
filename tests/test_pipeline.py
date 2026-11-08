import pandas as pd

from due_diligent import cli, config
from due_diligent.data import CompanyData

class FakeSource:
    def __init__(self, companies: dict[str, CompanyData]):
        self.companies = companies

    def get_company(self, ticker: str) -> CompanyData:
        return self.companies[ticker]

GOOD = CompanyData(
    ticker="GOOD",
    previous_close=100, trailing_eps=5,            # P/E 20
    price_to_book=3, gross_margin=0.5, net_margin=0.2,
    return_on_assets=0.25, return_on_equity=0.25,  # both > 0.2 -> rank 1
    quarterly={"debt": [50], "equity": [100],      # D/E 0.5 -> rank 1
               "capex": [-10], "net_income": [100]},  # capex/income 0.1 -> rank 1
)

OKAY = CompanyData(
    ticker="OKAY",
    previous_close=100, trailing_eps=4,            # P/E 25
    price_to_book=3, gross_margin=0.3, net_margin=0.12,
    return_on_assets=0.15, return_on_equity=0.15,  # between 0.1 and 0.2 -> rank 2
    quarterly={"debt": [150], "equity": [100],     # D/E 1.5 -> rank 2
               "capex": [-40], "net_income": [100]},  # 0.4 -> rank 2
)

BAD = CompanyData(
    ticker="BAD",
    previous_close=100, trailing_eps=1,            # P/E 100, fails pe_filter
    price_to_book=3, gross_margin=0.1, net_margin=0.02,
    return_on_assets=0.02, return_on_equity=0.02,  # below 0.1 -> rank 3
    quarterly={"debt": [300], "equity": [100],     # D/E 3 -> rank 3
               "capex": [-80], "net_income": [100]},  # 0.8 -> rank 3
)


def test_pipeline_ranks_good_first(tmp_path, monkeypatch):
    # input file the pipeline will read
    pd.DataFrame({
        "Symbol": ["BAD", "OKAY", "GOOD"],
        "Sector": ["Technology"] * 3,
        "Industry": ["Software"] * 3,
    }).to_csv(tmp_path / config.TICKERS_FILENAME, index=False)

    monkeypatch.setattr(config, "STORAGE_MODE", "local")
    monkeypatch.setattr(config, "LOCAL_INPUT_DIR", str(tmp_path))
    monkeypatch.setattr(config, "LOCAL_OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr(config, "PAUSE_BETWEEN_TICKERS", 0)

    saved_path = cli.run(FakeSource({"GOOD": GOOD, "OKAY": OKAY, "BAD": BAD}))
    result = pd.read_csv(saved_path)

    assert len(result) == 3
    assert result["Symbol"].tolist() == ["GOOD", "OKAY", "BAD"]
    assert result["final_rank"].tolist() == [4, 8, 12]