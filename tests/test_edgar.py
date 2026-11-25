"""EDGAR client tests. No network: a fake get() returns canned SEC replies and counts calls."""
import json

import pytest

from due_diligent.edgar import (
    FACTS_URL, SUBMISSIONS_URL, TICKERS_URL, EdgarClient, EdgarError, Filing, read_filings,
)

TICKERS = {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}}
SUBMISSIONS = {
    "name": "Apple Inc.",
    "filings": {"recent": {  # newest first, like SEC's file
        "form": ["10-Q", "10-K/A", "10-K", "10-K"],
        "accessionNumber": ["0000320193-26-000001", "0000320193-25-000090",
                            "0000320193-25-000079", "0000320193-24-000123"],
        "filingDate": ["2026-01-30", "2025-12-01", "2025-10-31", "2024-11-01"],
        "reportDate": ["2025-12-27", "2025-09-27", "2025-09-27", "2024-09-28"],
        "primaryDocument": ["q.htm", "a.htm", "aapl-20250927.htm", "aapl-20240928.htm"],
    }},
}


class FakeSEC:
    def __init__(self, replies: dict[str, bytes]):
        self.replies = replies
        self.calls: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.calls.append(url)
        return self.replies[url]


@pytest.fixture
def sec():
    return FakeSEC({
        TICKERS_URL: json.dumps(TICKERS).encode(),
        SUBMISSIONS_URL.format(cik=320193): json.dumps(SUBMISSIONS).encode(),
    })


def make_client(tmp_path, sec):
    return EdgarClient(cache_dir=tmp_path, pause_seconds=0, get=sec)


def test_urls_pad_the_cik_to_ten_digits():
    assert SUBMISSIONS_URL.format(cik=320193) == "https://data.sec.gov/submissions/CIK0000320193.json"
    assert FACTS_URL.format(cik=320193).endswith("/CIK0000320193.json")


def test_cik_lookup_ignores_case(tmp_path, sec):
    assert make_client(tmp_path, sec).cik_for("aapl") == 320193


def test_unknown_ticker_raises(tmp_path, sec):
    with pytest.raises(EdgarError):
        make_client(tmp_path, sec).cik_for("NOPE")


def test_latest_10k_skips_10q_and_amendments(tmp_path, sec):
    filing = make_client(tmp_path, sec).latest_10k("AAPL")
    assert filing.accession == "0000320193-25-000079"
    assert filing.report_date == "2025-09-27"
    assert filing.url == ("https://www.sec.gov/Archives/edgar/data/320193/"
                          "000032019325000079/aapl-20250927.htm")


def test_second_client_reads_from_disk_not_sec(tmp_path, sec):
    make_client(tmp_path, sec).latest_10k("AAPL")
    calls_after_first = len(sec.calls)
    make_client(tmp_path, sec).latest_10k("AAPL")
    assert len(sec.calls) == calls_after_first == 2


def test_user_agent_is_required(monkeypatch):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    with pytest.raises(EdgarError, match="SEC_USER_AGENT"):
        EdgarClient()


def test_read_filings_round_trip(tmp_path):
    filing = Filing("AAPL", 320193, "Apple Inc.", "10-K", "0000320193-25-000079",
                    "2025-10-31", "2025-09-27", "aapl-20250927.htm")
    path = tmp_path / "filings.csv"
    path.write_text("ticker,cik,company,form,accession,filing_date,report_date,document,url\n"
                    "AAPL,320193,Apple Inc.,10-K,0000320193-25-000079,2025-10-31,2025-09-27,"
                    "aapl-20250927.htm,https://example\n")
    assert read_filings(path) == [filing]