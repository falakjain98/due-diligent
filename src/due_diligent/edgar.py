"""Download 10-K filings and XBRL facts from SEC EDGAR (official and free).

SEC's rules for scripts: say who you are in a User-Agent header ("Name email"), and stay
under 10 requests a second. Every download is saved under config.EDGAR_CACHE_DIR, so a
rerun reads from disk and doesn't ask SEC again. Delete that folder to fetch fresh copies.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import pandas as pd

from due_diligent import config

logger = logging.getLogger(__name__)

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{folder}/{document}"


class EdgarError(Exception):
    """EDGAR could not give us what we asked for."""

@dataclass(frozen=True)
class Filing:
    """One filing, as listed in a company's EDGAR submissions."""
    ticker: str
    cik: int
    company: str
    form: str
    accession: str     # e.g. "0000320193-25-000079": the filing's ID
    filing_date: str   # when it was filed
    report_date: str   # the last day of the period it covers (the fiscal year end for a 10-K)
    document: str      # the main file's name, e.g. "aapl-20250927.htm"

    @property
    def url(self) -> str:
        """Where the main document lives. The folder is the accession number without dashes."""
        return ARCHIVE_URL.format(cik=self.cik, folder=self.accession.replace("-", ""), document=self.document)

def read_filings(path: str | Path) -> list[Filing]:
    """The filings list that scripts/download_10ks.py saved (extra columns like url are ignored)."""
    names = [field.name for field in fields(Filing)]
    records = pd.read_csv(path, dtype=str).to_dict("records")
    return [Filing(**{name: record[name] for name in names} | {"cik": int(record["cik"])}) for record in records]

class EdgarClient:
    """Small EDGAR client: polite (User-Agent, pause), cached on disk, testable (get= can be faked)."""

    def __init__(self, user_agent: str | None = None, cache_dir: str | Path = config.EDGAR_CACHE_DIR,
                 pause_seconds: float = config.EDGAR_PAUSE_SECONDS,
                 get: Callable[[str], bytes] | None = None):
        self.user_agent = user_agent or os.environ.get("SEC_USER_AGENT", "")
        if get is None and not self.user_agent:
            raise EdgarError('Set SEC_USER_AGENT, for example: export SEC_USER_AGENT="Your Name you@example.com"')
        self.cache_dir = Path(cache_dir)
        self.pause_seconds = pause_seconds
        self._get = get or self._http_get
        self._ciks: dict[str, int] | None = None

    # --- downloading -----------------------------------------------------------------

    def _http_get(self, url: str) -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            # 403 usually means a missing User-Agent or too many requests; 404 a wrong URL
            raise EdgarError(f"SEC returned {error.code} for {url}") from error
        except urllib.error.URLError as error:
            raise EdgarError(f"Could not reach SEC for {url}: {error.reason}") from error

    def _cache_path(self, url: str) -> Path:
        """https://data.sec.gov/submissions/CIK1.json -> <cache>/data.sec.gov/submissions/CIK1.json"""
        parts = urlparse(url)
        return self.cache_dir / parts.netloc / parts.path.lstrip("/")

    def fetch(self, url: str) -> bytes:
        """The bytes at url: from the cache if we have them, otherwise from SEC (then cached)."""
        path = self._cache_path(url)
        if path.exists():
            return path.read_bytes()
        time.sleep(self.pause_seconds)  # rate limit: only real requests wait
        logger.info("Downloading %s", url)
        body = self._get(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        return body

    def fetch_json(self, url: str) -> dict:
        return json.loads(self.fetch(url))

    # --- what we ask for ---------------------------------------------------------------

    def cik_for(self, ticker: str) -> int:
        """SEC's company ID (CIK) for a ticker. One download covers every listed company."""
        if self._ciks is None:
            rows = self.fetch_json(TICKERS_URL).values()
            self._ciks = {row["ticker"].upper(): int(row["cik_str"]) for row in rows}
        try:
            return self._ciks[ticker.upper()]
        except KeyError:
            raise EdgarError(f"{ticker} is not in SEC's ticker list") from None

    def latest_10k(self, ticker: str) -> Filing:
        """The company's most recent 10-K (amendments, 10-K/A, are skipped)."""
        cik = self.cik_for(ticker)
        submissions = self.fetch_json(SUBMISSIONS_URL.format(cik=cik))
        recent = submissions["filings"]["recent"]  # parallel lists, newest first
        for i, form in enumerate(recent["form"]):
            if form == "10-K":
                return Filing(
                    ticker=ticker.upper(), cik=cik, company=submissions["name"], form=form,
                    accession=recent["accessionNumber"][i], filing_date=recent["filingDate"][i],
                    report_date=recent["reportDate"][i], document=recent["primaryDocument"][i],
                )
        raise EdgarError(f"No 10-K in {ticker}'s recent filings")

    def filing_html(self, filing: Filing) -> str:
        return self.fetch(filing.url).decode("utf-8", errors="replace")

    def company_facts(self, cik: int) -> dict:
        """Every XBRL fact the company has reported, all filings (the 'answer key' for Session 4)."""
        return self.fetch_json(FACTS_URL.format(cik=cik))