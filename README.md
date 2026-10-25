# due-diligent

Screens the S&P 500 on fundamentals so you know which companies deserve a closer look, and why.

> Research tool only. Nothing here is investment advice.

## What it does
The package loads S&P500 tickers along with industry and sector information. After some initial scrubbing, it fetches data for those stickers using the yfinance package. This financial data is used to determine metrics which indicate fundamentals similar to [Warren Buffet and the Interpretation of Finanical Statements](https://www.youtube.com/watch?v=lBBXmim527A&t=685s). Stocks adhering to the thresholds are then screened, ranked and saved to a CSV.

## Quickstart
Run the following commands to get started:
```
git clone https://github.com/falakjain98/due-diligent
python -m venv .venv
source .venv/bin/activate
pip install -e .
python -m due_diligent.cli
```
The output can then be found in `output/sp500/` within the current_date subdirectory 

## Configuration
All settings live in `src/due_diligent/config.py`. Edit them there; no code changes needed.
 
| Setting | Default | What it does |
|---|---|---|
| `STORAGE_MODE` | `"local"` | Where to read the ticker list and write results: `"local"` or `"s3"`. Override without editing code: `DD_STORAGE=s3 python -m due_diligent.cli` |
| `LOCAL_INPUT_DIR` | `"sample_data"` | Folder holding the ticker CSV in local mode |
| `LOCAL_OUTPUT_DIR` | `"output"` | Folder results are written to in local mode |
| `TICKERS_FILENAME` | `"sp500_tickers.csv"` | Name of the input ticker file and the output results file |
| `S3_BUCKET`, `INPUT_PREFIX`, `OUTPUT_PREFIX` | `"fin-fj"`, `"input"`, `"output"` | S3 locations used in S3 mode |
| `MAX_TICKERS` | `None` | Limit the run to the first N tickers (e.g. `10` while testing); `None` runs all |
| `PAUSE_BETWEEN_TICKERS` | `0.3` | Seconds to wait between tickers so the data source doesn't throttle requests |
 
**Screening thresholds** are in the same file, grouped by rule:
 
- **Universe cleanup:** `EXCLUDED_INDUSTRIES`
- **Filters:** `PE_MIN` / `PE_MAX`, `PB_MAX`, `GROSS_MARGIN_MIN`, `NET_MARGIN_MIN`, `ROA_MIN`, `ROE_MIN`
- **Rank cutoffs** (rank 1 / rank 2 boundaries): `ROA_RANK_CUTOFFS`, `ROE_RANK_CUTOFFS`, `DEBT_TO_EQUITY_RANK_CUTOFFS`, `CAPEX_TO_INCOME_RANK_CUTOFFS`

S3 mode uses your standard AWS credentials (an instance role on EC2, or `~/.aws/credentials`).

## Project layout
```
due-diligent/
├── pyproject.toml          # project metadata and pinned dependencies
├── sample_data/
│   └── sp500_tickers.csv   # 10-ticker sample for fast local runs
├── output/                 # local results (git-ignored)
└── src/due_diligent/
    ├── config.py           # all settings and screening thresholds
    ├── data.py             # fetches raw company data (DataSource interface + yfinance)
    ├── metrics.py          # pure functions: ratios and per-period values, no network
    ├── screen.py           # universe cleanup, pass/fail filters, ranking
    ├── storage.py          # loads tickers and saves results, locally or on S3
    └── cli.py              # runs the pipeline end to end: python -m due_diligent.cli
```
 
**How data flows:** `storage` → `screen.clean_universe` → `data` → `metrics` → `screen` (filters, ranks) → `storage`

## Design choices
- **Fetch each ticker once.** `YFinanceSource` creates one `yf.Ticker` per company and reads `.info` and each statement a single time. The original script downloaded the same company about 20 times; see issue #4 for the before/after runtime.
- **A `DataSource` interface between fetching and everything else.** The pipeline only depends on `get_company(ticker) -> CompanyData`, not on yfinance. That means the source can be swapped (SEC EDGAR is next) without touching the screening code, and tests can pass in a fake source with fixed numbers and no network.
- **Pure functions for the math and the rules.** `metrics.py` and `screen.py` never touch the network or the disk. They take numbers or DataFrames and return new ones, which makes every ratio and every rule testable in isolation.
- **Every threshold lives in `config.py`.** Tuning the screen means editing a number, not logic. Each filter is its own small function, so changing one rule touches exactly one place.
- **Missing data is expected, not fatal.** Banks have no R&D line, and some tickers lack EPS. Missing values become `None` with a logged warning. A ticker that fails to fetch is logged and skipped, so one bad symbol can't stop a 500-ticker run.
- **Fail loudly where it matters.** S3 errors and an unknown `STORAGE_MODE` raise instead of being swallowed. A run that silently saved nothing is worse than a crash.
- **Filters are columns, not deletions.** Every stock stays in the output with a True/False column per rule, so you can see *why* a company passed or failed instead of it quietly disappearing.
- **One codebase, local or cloud.** The same pipeline runs from local CSVs (no AWS needed) or from S3, switched by one setting.

## Performance
~1.4 s/ticker vs >20 s/ticker

## Known issues
- [Issue 1: debt_to_equity is inverted](https://github.com/falakjain98/due-diligent/issues/1)
- [Issue 2: capex_to_income always ranks 1 because capex is negative](https://github.com/falakjain98/due-diligent/issues/2)
- [Issue 3: P/B filter uses OR, so it barely filters](https://github.com/falakjain98/due-diligent/issues/3)

## Roadmap
- **Tests and bug fixes:** pytest coverage for `metrics` and `screen`, with each known bug (#1–#3) fixed test-first, and CI on every push
- **API and container:** a FastAPI service (`/tickers/{symbol}`, `/screen`) with Pydantic models and caching, packaged in Docker
- **Read the filings:** pull 10-Ks from SEC EDGAR and extract structured, validated data with an LLM, checked against XBRL
- **Ask the filings:** retrieval over 10-K sections with citations, plus an evaluation set to measure answer accuracy
- **Research analyst agent:** screen, read the filings, and write a cited one-page memo per company, with guardrails against prompt injection and against anything resembling investment advice
- **Deploy:** cloud deployment with tracing of every LLM call (cost, latency, tokens)