"""Run both note writers on the sample tickers and save everything for comparison.

Writes three files to output/notes/<today>/ (git-ignored):
  notes.csv        one row per note: text, tokens, latency, cost, automatic checks
  grading.csv      the same notes shuffled, provider hidden, with empty columns for your grades
  grading_key.csv  which provider wrote each graded note (don't open it until you've graded)

Run from the repo root with your keys loaded:
    set -a; source .env; set +a
    python scripts/compare_providers.py
"""
from __future__ import annotations

import logging
import random
import time
from datetime import date
from pathlib import Path

import pandas as pd
from fastapi import HTTPException

from due_diligent import config, screen, storage
from due_diligent.api import get_ticker
from due_diligent.cache import CachedSource
from due_diligent.data import YFinanceSource
from due_diligent.notes import (
    ClaudeWriter, NoteError, OpenAIWriter, advice_terms, made_up_numbers, note_cost,
    sentence_count, user_message,
)

logger = logging.getLogger("compare_providers")
SHUFFLE_SEED = 42  # fixed, so the blind order is the same if you re-create the sheet


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    symbols = screen.clean_universe(storage.load_tickers())["Symbol"].tolist()[: config.MAX_TICKERS]
    source = CachedSource(YFinanceSource(), ttl_seconds=config.CACHE_TTL_SECONDS)
    writers = [ClaudeWriter(), OpenAIWriter()]

    rows = []
    for symbol in symbols:
        try:
            result = get_ticker(symbol, source)  # fetched once; both writers get the same input
        except HTTPException as error:
            logger.warning("Skipping %s: %s", symbol, error.detail)
            continue
        for writer in writers:
            try:
                note = writer.write(result)
            except NoteError as error:
                logger.warning("No note from %s for %s: %s", writer.provider, symbol, error)
                rows.append({"ticker": symbol, "provider": writer.provider, "model": writer.model,
                             "error": str(error)})
                continue
            rows.append({
                **note.model_dump(),
                "cost_usd": note_cost(note),
                "sentences": sentence_count(note.text),
                "advice_terms": ", ".join(advice_terms(note.text)),
                "made_up_numbers": ", ".join(made_up_numbers(note.text, result)),
                "input": user_message(result),
                "error": "",
            })
            logger.info("%s / %s: %.2fs, %d out tokens", symbol, writer.provider, note.latency_s, note.output_tokens)
        time.sleep(config.PAUSE_BETWEEN_TICKERS)

    out_dir = Path(config.LOCAL_OUTPUT_DIR) / "notes" / date.today().isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    notes = pd.DataFrame(rows)
    notes.to_csv(out_dir / "notes.csv", index=False)

    # Blind grading sheet: shuffle, give each note a neutral id, hide who wrote it.
    good = notes[notes["error"] == ""].sample(frac=1, random_state=SHUFFLE_SEED).reset_index(drop=True)
    good["note_id"] = [f"N{i + 1:02d}" for i in range(len(good))]
    sheet = good[["note_id", "ticker", "input", "text"]].assign(accuracy="", clarity="", comment="")
    sheet.to_csv(out_dir / "grading.csv", index=False)
    good[["note_id", "ticker", "provider", "model"]].to_csv(out_dir / "grading_key.csv", index=False)

    failed = (notes["error"] != "").sum()
    total_cost = pd.to_numeric(notes.get("cost_usd"), errors="coerce").sum()
    print(f"\n{len(good)} notes written, {failed} failed, total cost ${total_cost:.4f} (priced models only)")
    print(f"Saved to {out_dir}/. Grade grading.csv next; don't open grading_key.csv yet.")


if __name__ == "__main__":
    main()