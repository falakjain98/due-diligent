"""How big is each 10-K for a model, and what would sending it cost? (Session 2)

Counts tokens with tiktoken's o200k_base (OpenAI's tokenizer, a good estimate for any model),
for the whole text and for the extraction sections only. Needs the llm and edgar extras.
Reads output/edgar/filings.csv from download_10ks.py; downloads nothing new.
"""
from __future__ import annotations

import pandas as pd
import tiktoken

from due_diligent import config
from due_diligent.edgar import EdgarClient, read_filings
from due_diligent.filings import extraction_text, filing_text

def input_cost(tokens: int, model: str) -> float | None:
    input_price, _ = config.PRICES_PER_MILLION.get(model, (None, None))
    return None if input_price is None else tokens * input_price / 1_000_000

def main() -> None:
    encoding = tiktoken.get_encoding("o200k_base")
    client = EdgarClient()
    rows = []
    for filing in read_filings("output/edgar/filings.csv"):
        text = filing_text(client.filing_html(filing))
        sections, found = extraction_text(text)
        full_tokens, section_tokens = len(encoding.encode(text)), len(encoding.encode(sections))
        rows.append({
            "ticker": filing.ticker,
            "full_tokens": full_tokens,
            "section_tokens": section_tokens,
            "sections_found": found,
            "kept_pct": round(100 * section_tokens / full_tokens),
            f"cost_{config.CLAUDE_MODEL}": input_cost(section_tokens, config.CLAUDE_MODEL),
            f"cost_{config.OPENAI_MODEL}": input_cost(section_tokens, config.OPENAI_MODEL),
        })
    table = pd.DataFrame(rows)
    print(table.to_string(index=False))
    print("\nTotal section tokens:", table["section_tokens"].sum())

if __name__ == "__main__":
    main()