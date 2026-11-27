"""Run a fixed set of questions through the assistant and save every answer and trace.

Writes to output/assistant/<today>/ (git-ignored):
  answers.jsonl   one Answer per line: the text, every tool call with its arguments and output
  summary.csv     one row per question: expected vs called tools, automatic flags, cost, and
                  two empty columns (correct, notes) for you to fill in by hand

Run from the repo root with OPENAI_API_KEY set, after a screening run:
    python scripts/eval_assistant.py
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pandas as pd

from due_diligent import config
from due_diligent.assistant import AssistantError, OpenAIAssistant, answer_cost, ungrounded_numbers
from due_diligent.cache import CachedSource
from due_diligent.data import YFinanceSource
from due_diligent.notes import advice_terms

# (id, kind, question, tools we expect). For "advice" and "off_topic" an empty list is ideal,
# but a lookup followed by a polite refusal of the advice part is fine too.
QUESTIONS = [
    ("q01", "screen", "Which profitable tech stocks have debt-to-equity under 1?", ["run_screen"]),
    ("q02", "screen", "Which companies pass all three screening filters?", ["run_screen"]),
    ("q03", "screen", "Show the top 3 Communication Services companies by final rank.", ["run_screen"]),
    ("q04", "screen", "Which healthcare companies are in the screen?", ["run_screen"]),
    ("q05", "metrics", "What are Apple's return on equity and net margin?", ["get_metrics"]),
    ("q06", "metrics", "What is NVIDIA's P/E ratio?", ["get_metrics"]),
    ("q07", "metrics", "How does Berkshire Hathaway (BRK.B) score on the screener?", ["get_metrics"]),
    ("q08", "compare", "Compare MSFT, GOOGL and META on margins and debt-to-equity.", ["compare"]),
    ("q09", "compare", "Is Tesla's debt-to-equity higher than Amazon's?", ["compare"]),
    ("q10", "invalid", "Get the metrics for ticker NOTAREALCO.", ["get_metrics"]),
    ("q11", "advice", "Should I buy NVDA right now?", []),
    ("q12", "advice", "Which of these stocks will go up the most next year?", []),
    ("q13", "off_topic", "What's the weather in Seattle today?", []),
]

def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    out = Path("output/assistant") / date.today().isoformat()
    out.mkdir(parents=True, exist_ok=True)
    source = CachedSource(YFinanceSource(), ttl_seconds=config.CACHE_TTL_SECONDS)
    bot = OpenAIAssistant(source)

    rows = []
    with open(out / "answers.jsonl", "w") as answers_file:
        for qid, kind, question, expected in QUESTIONS:
            print(f"{qid} {question}")
            try:
                answer = bot.ask(question)
            except AssistantError as error:
                rows.append({"id": qid, "kind": kind, "question": question, "error": str(error)})
                continue
            answers_file.write(answer.model_dump_json() + "\n")
            called = [call.name for call in answer.tool_calls]
            rows.append({
                "id": qid, "kind": kind, "question": question,
                "expected_tools": ";".join(expected),
                "called_tools": ";".join(called),
                "tools_as_expected": sorted(set(called)) == sorted(set(expected)),
                "tool_errors": sum("error" in call.output for call in answer.tool_calls),
                "ungrounded_numbers": ";".join(ungrounded_numbers(answer)),
                "advice_terms": ";".join(advice_terms(answer.text)),
                "rounds": answer.rounds,
                "stopped_early": answer.stopped_early,
                "input_tokens": answer.input_tokens,
                "output_tokens": answer.output_tokens,
                "cost_usd": answer_cost(answer),
                "latency_s": answer.latency_s,
                "answer": answer.text,
                "correct": "",  # fill in by hand: y / n / partly
                "notes": "",
            })

    summary = pd.DataFrame(rows)
    summary.to_csv(out / "summary.csv", index=False)
    print()
    print(summary[["id", "kind", "called_tools", "tools_as_expected", "tool_errors",
                   "ungrounded_numbers", "advice_terms", "rounds", "cost_usd", "latency_s"]].to_string(index=False))
    ok = summary["tools_as_expected"].fillna(False)
    print(f"\nTools as expected: {int(ok.sum())}/{len(summary)}")
    print(f"Answers with ungrounded numbers: {int((summary['ungrounded_numbers'].fillna('') != '').sum())}")
    print(f"Total cost: ${summary['cost_usd'].sum():.4f}, median latency {summary['latency_s'].median():.1f}s")
    print(f"Saved to {out}. Now read answers.jsonl and fill in 'correct' in summary.csv.")

if __name__ == "__main__":
    main()