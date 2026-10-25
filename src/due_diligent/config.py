"""Settings and screening thresholds. Edit numbers here, not in the code."""

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