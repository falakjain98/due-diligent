# due-diligent screener API: design

*Status: implemented (CLI, API, cache, Docker; 10-K extraction added). Research tool only; nothing here is investment advice.*

## Context and problem
Investors and analysts who want a first pass over the S&P 500 need to know which companies pass basic fundamentals checks, and *why* each one passed or failed. The original `stock-screener` script answered this once per run as a CSV, took over 20 seconds per ticker (it downloaded each company about 20 times), had three scoring bugs, and could only run on AWS. due-diligent rebuilds it as a tested Python package with a CLI for full runs and an HTTP API for single-company lookups.

## Goals and non-goals
**Goals**
- Score any one ticker on demand in about a second, and the full universe in a batch run.
- Explain every result: each rule's pass/fail and each rank, not just a final list.
- Run the same code locally or on AWS (S3, Docker), with tests that never touch the network.

**Non-goals**
- No buy, sell or valuation views: the output describes rule results only, and every reply carries a disclaimer.
- No real-time prices or intraday data.
- No trading, portfolios or user accounts.

## Design overview
- **CLI (batch):** load tickers → clean the universe → fetch each company once through a `DataSource` → compute ratios (`metrics`) → filters, then ranks (`screen.score`) → save a dated CSV (local or S3).
- **API (on demand):** `GET /tickers/{symbol}` fetches one company through a cached `DataSource` and runs the same `metrics` and `screen.score`, returning a Pydantic model. `GET /screen` serves the newest saved CLI run, optionally filtered by sector.

The API is a thin layer over the CLI's functions, so a rule changed once changes everywhere. Ratios and rules are pure functions with no network or disk access, which is why all 87 tests run offline.

## Key decisions

### Data source: yfinance now, SEC EDGAR next
| | yfinance | SEC EDGAR |
|---|---|---|
| Official | No (unofficial, reads Yahoo Finance) | Yes (SEC's own APIs) |
| Limits | Unpublished; throttles when called fast | Published: 10 requests/second, User-Agent required |
| Gives | Prices plus ready-made ratios | Filings and as-reported XBRL numbers; no prices |
| Effort | One call per company | Ratios computed by us; XBRL tags vary by company |

**Decision:** keep yfinance for the screen, because it returns prices and ratios in one call and was enough to rebuild the screen. Keep it behind the `DataSource` interface so an `EdgarSource` can replace or supplement it without touching `metrics` or `screen`. EDGAR is already used alongside it for filings: week 5 pulls 10-K text from EDGAR, extracts facts with an LLM, and checks them against XBRL (44 of 49 checks matched; see [10k-extraction.md](10k-extraction.md)).

### Screening rules
Three pass/fail filters (P/E between 0 and 50; gross margin above 20% and net margin above 10%; ROA and ROE above 5%) and four ranks from 1 (best) to 3 (ROA, ROE, debt-to-equity, capex-to-income), summed into `final_rank` (4 best, 12 worst). Every threshold lives in `config.py`. Missing data fails its filter and ranks 3, and filters are columns rather than deletions, so no company silently disappears. The original price-to-book rule was **removed on purpose** (issue #3): book value says little about asset-light companies. A useful side effect is that no rule depends on other companies, so one ticker can be scored on its own.

### Caching
`CachedSource` wraps any `DataSource` and is one itself, keeping each company in memory for one hour (`CACHE_TTL_SECONDS`). One hour fits the data: prices move daily and statements quarterly. Failed fetches are never cached. Measured on EC2: a cold `/tickers` call takes 1.11 s, a repeat without the cache about 0.34 s, and a cached repeat about 0.016 s.

## Alternatives considered
- **`functools.lru_cache`:** rejected; entries never expire, so data would go stale.
- **Running the screen inside `/screen`:** rejected; a full run takes minutes, so the API serves saved results instead.
- **Keeping P/B with a sector average:** rejected; it filtered poorly and made each score depend on every other company.
- **A full `python:3.13` Docker image:** rejected for size and attack surface; the image uses `python:3.13-slim`, pinned dependencies and a non-root user.

## Known limitations
- yfinance is unofficial: it can throttle, change without notice, or return empty data for unknown tickers (the API treats no price and no EPS as a 404, and a failed fetch as a 502).
- The cache is in memory and per process: it empties on restart, and two API containers would not share it.
- `/screen` is only as fresh as the last CLI run; nothing schedules runs yet.
- The API has no authentication.
- The rules are fixed rules of thumb and say nothing about valuation or future performance.
- LLM-written notes (week 4) and 10-K extraction (week 5) run from `scripts/`; neither is exposed through the API yet.

## What's next
Expose the screener as LLM tools (week 6), then add cited retrieval over 10-K sections with an evaluation set (weeks 7–8). See the README roadmap.
