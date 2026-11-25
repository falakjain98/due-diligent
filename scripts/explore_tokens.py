"""Experiment: how many tokens does one company's screener result cost?

Run from the repo root with your keys loaded:
    set -a; source .env; set +a
    python scripts/explore_tokens.py AAPL
"""
from __future__ import annotations

import json
import sys

import tiktoken
from anthropic import Anthropic

from due_diligent.api import get_ticker
from due_diligent.data import YFinanceSource

CLAUDE_MODEL = "claude-opus-5-5"
OPENAI_ENCODING = "o200k_base"  # the tokenizer OpenAI's current models use


def rounded(value, digits: int = 3):
    """Round every float inside nested dicts and lists. Everything else is left alone."""
    if isinstance(value, float):
        return round(value, digits)
    if isinstance(value, dict):
        return {key: rounded(item, digits) for key, item in value.items()}
    if isinstance(value, list):
        return [rounded(item, digits) for item in value]
    return value

def claude_tokens(client: Anthropic, text: str) -> int:
    """Ask Anthropic how many input tokens this text costs. Free, and it doesn't run the model."""
    response = client.messages.count_tokens(
        model=CLAUDE_MODEL,
        messages=[{"role": "user", "content": text}],
    )
    return response.input_tokens

def main() -> None:
    symbol = sys.argv[1] if len(sys.argv) > 1 else "AAPL"

    # Same code path as GET /tickers/{symbol}. Outside FastAPI, Depends() does nothing,
    # so we pass the data source in ourselves.
    screen = get_ticker(symbol, YFinanceSource())
    data = screen.model_dump()

    versions = {
        "pretty JSON": json.dumps(data, indent=2),
        "compact JSON": json.dumps(data, separators=(",", ":")),
        "compact + rounded": json.dumps(rounded(data), separators=(",", ":")),
    }

    claude = Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    openai_tokenizer = tiktoken.get_encoding(OPENAI_ENCODING)

    print(f"\nToken counts for {symbol}\n")
    print(f"{'format':<20}{'chars':>8}{'Claude':>9}{'OpenAI':>9}")
    for name, text in versions.items():
        print(
            f"{name:<20}{len(text):>8}"
            f"{claude_tokens(claude, text):>9}"
            f"{len(openai_tokenizer.encode(text)):>9}"
        )

    print("\nHow OpenAI's tokenizer splits a few strings:")
    for text in ["AAPL", "debt_to_equity", "0.4623451", "0.462", "Not investment advice."]:
        pieces = [openai_tokenizer.decode([token]) for token in openai_tokenizer.encode(text)]
        print(f"  {text!r:<26} {len(pieces)} tokens: {pieces}")

if __name__ == "__main__":
    main()