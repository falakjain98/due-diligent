"""Run the full screen: load -> clean -> fetch -> metrics -> filters -> ranks -> save."""
from __future__ import annotations

import logging
import time
from datetime import date

from due_diligent import config, metrics, screen, storage
from due_diligent.data import CompanyData, DataSource, YFinanceSource

logger = logging.getLogger(__name__)


def fetch_all(source: DataSource, symbols: list[str]) -> list[CompanyData]:
    """Fetch every ticker, skipping (and logging) any that fail."""
    companies = []
    for i, symbol in enumerate(symbols, start=1):
        try:
            company = source.get_company(symbol)
            companies.append(company)
            logger.debug("Fetched %s", symbol)
        except Exception:
            logger.exception("Failed to fetch %s", symbol)
        time.sleep(config.PAUSE_BETWEEN_TICKERS)
        if i % 50 == 0:
            logger.info("Fetched %d/%d tickers", i, len(symbols))
    logger.info("Fetched %d of %d tickers (%d failed)", len(companies), len(symbols), len(symbols) - len(companies))
    return companies

def run(source: DataSource) -> str:
    """Run the pipeline once and return where the results were saved."""
    tickers = storage.load_tickers()
    universe = screen.clean_universe(tickers)
    logger.info("Cleaned universe: %d tickers remain", len(universe))
    symbols = universe["Symbol"].tolist()[: config.MAX_TICKERS]
    companies = fetch_all(source, symbols)
    if not companies: raise RuntimeError("No companies fetched; check the logs above")
    df = metrics.metrics_table(companies)
    df = universe.merge(df, left_on="Symbol", right_on="ticker").drop(columns="ticker")
    df = metrics.add_group_average(df, "price_to_book", "Sector", "sector_avg_pb")
    df = screen.add_filter_columns(df)
    df = screen.add_ranks(df)
    run_date = date.today().isoformat()
    df["run_date"] = run_date
    return storage.save_results(df, run_date)

def main() -> None:
    """Entry point: set up logging, time the run."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    start = time.perf_counter()
    where = run(YFinanceSource())
    logger.info("Saved %s in %.1f seconds", where, time.perf_counter() - start)

if __name__ == "__main__":
    main()