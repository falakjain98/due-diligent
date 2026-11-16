# due-diligent

Screens the S&P 500 on fundamentals so you know which companies deserve a closer look, and why.

> Research tool only. Nothing here is investment advice.

## What it does
The package loads S&P500 tickers along with industry and sector information. After some initial scrubbing, it fetches data for those tickers using the yfinance package. This financial data is used to determine metrics which indicate fundamentals similar to [Warren Buffett and the Interpretation of Financial Statements](https://www.youtube.com/watch?v=lBBXmim527A&t=685s). Stocks adhering to the thresholds are then screened, ranked and saved to a CSV.

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

## Run the API
The same screen is available over HTTP through a FastAPI app.
```
pip install -e .
uvicorn due_diligent.api:app --reload --port 8000
```
`--reload` restarts the server whenever you save a file; leave it off outside development. Then, from another terminal:
```
curl localhost:8000/health
curl -s localhost:8000/tickers/AAPL | python -m json.tool
```
Interactive docs (every endpoint, its parameters and response shape, with a "Try it out" button) are at `http://localhost:8000/docs`. On a remote machine, forward the port first: `ssh -L 8000:localhost:8000 <host>`.

| Endpoint | What it returns |
|---|---|
| `GET /health` | `{"status": "ok"}` if the server is up; touches no data |
| `GET /tickers/{symbol}` | One company scored live: `metrics` (the ratios), `filters` (pass/fail per rule), `ranks` (1 best to 3 worst, plus `final_rank`), and a disclaimer. Case-insensitive symbol |

Status codes: `200` success, `404` unknown ticker (the data source returned no price and no EPS), `502` the data source itself failed (network error or throttling; try again). Missing values come back as `null`, the matching filter fails, and the matching rank is 3.

Example response (numbers illustrative):
```json
{
  "ticker": "AAPL",
  "metrics": {"pe_ratio": 34.1, "price_to_book": 52.3, "gross_margin": 0.46, "net_margin": 0.24,
              "return_on_assets": 0.22, "return_on_equity": 1.5, "debt_to_equity": 1.4, "capex_to_income": 0.1},
  "filters": {"pe_filter": true, "margin_filter": true, "returns_filter": true},
  "ranks": {"roa_rank": 1, "roe_rank": 1, "debt_to_equity_rank": 2, "capex_to_income_rank": 1, "final_rank": 5},
  "disclaimer": "Research output from fixed screening rules. Not investment advice."
}
```

## Run the tests
```
pip install -e ".[dev]"
pytest -v
```
No test touches the network. `tests/test_metrics.py` and `tests/test_screen.py` check each ratio and rule on small hand-made numbers, `tests/test_pipeline.py` runs the whole CLI pipeline on a fake data source and a temporary folder, and `tests/test_api.py` calls the API in-process with FastAPI's `TestClient`, swapping yfinance for a fake source through `app.dependency_overrides`. GitHub Actions runs the same `pytest` on every push and pull request.

## Configuration
All settings live in `src/due_diligent/config.py`. Edit them there; no code changes needed.
 
| Setting | Default | What it does |
|---|---|---|
| `STORAGE_MODE` | `"local"` | Where to read the ticker list and write results: `"local"` or `"s3"`. Override without editing code: `DD_STORAGE=s3 python -m due_diligent.cli` |
| `LOCAL_INPUT_DIR` | `"sample_data"` | Folder holding the ticker CSV in local mode |
| `LOCAL_OUTPUT_DIR` | `"output"` | Folder results are written to in local mode |
| `TICKERS_FILENAME` | `"sp500_tickers.csv"` | Name of the input ticker file and the output results file |
| `S3_BUCKET`, `INPUT_PREFIX`, `OUTPUT_PREFIX` | `"fin-fj"`, `"input"`, `"output"` | S3 locations used in S3 mode |
| `MAX_TICKERS` | `10` | Limit the run to the first N tickers (e.g. `10` while testing); `None` runs all |
| `PAUSE_BETWEEN_TICKERS` | `0.3` | Seconds to wait between tickers so the data source doesn't throttle requests |
 
**Screening thresholds** are in the same file, grouped by rule:
 
- **Universe cleanup:** `EXCLUDED_INDUSTRIES`
- **Filters:** `PE_MIN` / `PE_MAX`, `GROSS_MARGIN_MIN`, `NET_MARGIN_MIN`, `ROA_MIN`, `ROE_MIN`
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
    ├── cli.py              # runs the pipeline end to end: python -m due_diligent.cli
    ├── api.py              # FastAPI app: uvicorn due_diligent.api:app
    └── models.py           # Pydantic response models for the API
tests/                      # pytest suite, no network needed
.github/workflows/tests.yml # CI: runs pytest on every push and pull request
```
 
**How data flows:**
- CLI: `storage` → `screen.clean_universe` → `data` → `metrics` → `screen.score` (filters, ranks) → `storage`
- API: request → `data` (one ticker) → `metrics` → `screen.score` → Pydantic model → JSON

## Design choices
- **Fetch each ticker once.** `YFinanceSource` creates one `yf.Ticker` per company and reads `.info` and each statement a single time. The original script downloaded the same company about 20 times; see issue #4 for the before/after runtime.
- **A `DataSource` interface between fetching and everything else.** The pipeline only depends on `get_company(ticker) -> CompanyData`, not on yfinance. That means the source can be swapped (SEC EDGAR is next) without touching the screening code, and tests can pass in a fake source with fixed numbers and no network.
- **Pure functions for the math and the rules.** `metrics.py` and `screen.py` never touch the network or the disk. They take numbers or DataFrames and return new ones, which makes every ratio and every rule testable in isolation.
- **Every threshold lives in `config.py`.** Tuning the screen means editing a number, not logic. Each filter is its own small function, so changing one rule touches exactly one place.
- **Missing data is expected, not fatal.** Banks have no R&D line, and some tickers lack EPS. Missing values become `None` with a logged warning. A ticker that fails to fetch is logged and skipped, so one bad symbol can't stop a 500-ticker run.
- **Fail loudly where it matters.** S3 errors and an unknown `STORAGE_MODE` raise instead of being swallowed. A run that silently saved nothing is worse than a crash.
- **Filters are columns, not deletions.** Every stock stays in the output with a True/False column per rule, so you can see *why* a company passed or failed instead of it quietly disappearing.
- **The API is a thin layer.** `api.py` does no math of its own: it calls the same `metrics` and `screen.score` as the CLI, so a rule changed once changes everywhere. The data source is injected with FastAPI's `Depends`, so tests run the real endpoints against a fake source.
- **One codebase, local or cloud.** The same pipeline runs from local CSVs (no AWS needed) or from S3, switched by one setting.

## Performance
~1.4 s/ticker vs >20 s/ticker

## Roadmap
- **[Done]** **Tests and bug fixes:** pytest coverage for `metrics` and `screen`, with each known bug (#1–#3) fixed test-first, and CI on every push
- **[In progress]** **API and container:** a FastAPI service (`/tickers/{symbol}`, `/screen`) with Pydantic models and caching, packaged in Docker
- **Read the filings:** pull 10-Ks from SEC EDGAR and extract structured, validated data with an LLM, checked against XBRL
- **Ask the filings:** retrieval over 10-K sections with citations, plus an evaluation set to measure answer accuracy
- **Research analyst agent:** screen, read the filings, and write a cited one-page memo per company, with guardrails against prompt injection and against anything resembling investment advice
- **Deploy:** cloud deployment with tracing of every LLM call (cost, latency, tokens)