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
PB_MAX = 10
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
MAX_TICKERS = None            # e.g. 10 while testing; None = all
PAUSE_BETWEEN_TICKERS = 0.3   # seconds, so yfinance doesn't throttle you