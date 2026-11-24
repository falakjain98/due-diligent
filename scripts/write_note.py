"""Smoke test: write one note per provider for one ticker.

Run from the repo root with your keys loaded:
    set -a; source .env; set +a
    python scripts/write_note.py AAPL
"""
from __future__ import annotations

import sys

from due_diligent.api import get_ticker
from due_diligent.data import YFinanceSource
from due_diligent.notes import ClaudeWriter, OpenAIWriter, advice_terms, sentence_count, user_message


def main() -> None:
    symbol = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    screen = get_ticker(symbol, YFinanceSource())
    print(f"What the model sees:\n{user_message(screen)}\n")

    for writer in [ClaudeWriter(), OpenAIWriter()]:
        note = writer.write(screen)
        print(f"=== {note.provider} ({note.model}) ===")
        print(f"{note.latency_s:.2f}s, in {note.input_tokens} / out {note.output_tokens} tokens")
        print(f"sentences: {sentence_count(note.text)}, advice terms: {advice_terms(note.text) or 'none'}")
        print(f"\n{note.text}\n\n{note.disclaimer}\n")


if __name__ == "__main__":
    main()