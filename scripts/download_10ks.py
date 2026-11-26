"""Download the latest 10-K for each ticker and list them in output/edgar/filings.csv.

Run from the repo root (SEC_USER_AGENT must be set):
    python scripts/download_10ks.py                       # the sample tickers
    python scripts/download_10ks.py AAPL NVDA MSFT ...    # or your own list
"""
from __future__ import annotations

import logging
import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from due_diligent import storage
from due_diligent.edgar import EdgarClient, EdgarError

logger = logging.getLogger("download_10ks")


def tickers_from_args() -> list[str]:
    return sys.argv[1:] or storage.load_tickers()["Symbol"].tolist()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    client = EdgarClient()
    rows, seen_ciks = [], set()
    for ticker in tickers_from_args():
        try:
            filing = client.latest_10k(ticker)
        except EdgarError as error:
            logger.warning("Skipping %s: %s", ticker, error)
            continue
        if filing.cik in seen_ciks:  # GOOG and GOOGL are one company with one 10-K
            logger.info("Skipping %s: same company as an earlier ticker", ticker)
            continue
        seen_ciks.add(filing.cik)
        html = client.filing_html(filing)
        rows.append({**asdict(filing), "url": filing.url, "html_mb": round(len(html) / 1e6, 2)})

    out = Path("output/edgar")
    out.mkdir(parents=True, exist_ok=True)
    table = pd.DataFrame(rows)
    table.to_csv(out / "filings.csv", index=False)
    print(table[["ticker", "company", "filing_date", "report_date", "html_mb"]].to_string(index=False))


if __name__ == "__main__":
    main()