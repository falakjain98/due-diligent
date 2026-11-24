"""Settings and screening thresholds. Edit numbers here, not in the code."""
import os

# storage
S3_BUCKET = "fin-fj"
INPUT_PREFIX = "input"
OUTPUT_PREFIX = "output"

# universe cleanup (main.py lines 27-28)
EXCLUDED_INDUSTRIES = ["Blank Checks"]

# filters (main.py lines 36, 46, 54, 62)
PE_MIN = 0
PE_MAX = 50
GROSS_MARGIN_MIN = 0.2
NET_MARGIN_MIN = 0.1
ROA_MIN = 0.05
ROE_MIN = 0.05

# rank buckets (main.py lines 126-129): (rank-1 cutoff, rank-2 cutoff)
ROA_RANK_CUTOFFS = (0.2, 0.1)              # higher is better
ROE_RANK_CUTOFFS = (0.2, 0.1)              # higher is better
DEBT_TO_EQUITY_RANK_CUTOFFS = (1, 2)       # lower is better
CAPEX_TO_INCOME_RANK_CUTOFFS = (0.25, 0.5) # lower is better

# where to read and write: "local" or "s3"
# An environment variable lets you switch without editing code: DD_STORAGE=s3 python -m due_diligent.cli
STORAGE_MODE = os.environ.get("DD_STORAGE", "local")

TICKERS_FILENAME = "sp500_tickers.csv"

# local mode
LOCAL_INPUT_DIR = "sample_data"
LOCAL_OUTPUT_DIR = "output"

# run controls
MAX_TICKERS = 10            # e.g. 10 while testing; None = all
PAUSE_BETWEEN_TICKERS = 0.3   # seconds, so yfinance doesn't throttle you

# API cache: how long a fetched company is reused before asking yfinance again
CACHE_TTL_SECONDS = 60 * 60   # 1 hour; prices move daily, statements quarterly

# LLM notes (week 4): which model each provider uses, and how much it thinks first
CLAUDE_MODEL = "claude-opus-5-5"
CLAUDE_EFFORT = "low"            # low | medium | high | xhigh | max
OPENAI_MODEL = "gpt-6-luna"
OPENAI_REASONING_EFFORT = "low"  # set to None if the model rejects a reasoning setting

# Dollars per 1M tokens as (input, output). Copied from each provider's pricing page on 11/24/2026.
PRICES_PER_MILLION = {
    "claude-opus-5-5": (4.00, 20.00),
    "gpt-6-luna": (0.1, 0.2),  # fill in from OpenAI's pricing page
}