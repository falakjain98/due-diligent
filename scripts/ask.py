"""Ask the screener assistant one question and print every tool call it made.

Run from the repo root with OPENAI_API_KEY set, after at least one screening run
(python -m due_diligent.cli), because run_screen reads the latest saved run:
    python scripts/ask.py "Which profitable tech stocks have debt-to-equity under 1?"
"""
from __future__ import annotations

import json
import logging
import sys

from due_diligent import config
from due_diligent.assistant import OpenAIAssistant, answer_cost, ungrounded_numbers
from due_diligent.cache import CachedSource
from due_diligent.data import YFinanceSource
from due_diligent.notes import advice_terms


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    question = " ".join(sys.argv[1:]) or "Which profitable tech stocks have debt-to-equity under 1?"
    source = CachedSource(YFinanceSource(), ttl_seconds=config.CACHE_TTL_SECONDS)
    answer = OpenAIAssistant(source).ask(question)

    print(f"Q: {answer.question}\n")
    for call in answer.tool_calls:
        output = json.dumps(call.output)
        print(f"[round {call.round}] {call.name}({call.arguments})")
        print(f"    -> {output[:300]}{'...' if len(output) > 300 else ''}\n")
    print(f"A: {answer.text}\n\n{answer.disclaimer}\n")
    cost = answer_cost(answer)
    print(f"{answer.rounds} rounds, in {answer.input_tokens} / out {answer.output_tokens} tokens, "
          f"{'unknown cost' if cost is None else f'${cost:.5f}'}, {answer.latency_s:.2f}s")
    print(f"ungrounded numbers: {ungrounded_numbers(answer) or 'none'}, advice terms: {advice_terms(answer.text) or 'none'}")


if __name__ == "__main__":
    main()