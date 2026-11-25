"""Join your blind grades with the notes and print the comparison table in Markdown.

Run after you've filled in the accuracy and clarity columns of grading.csv:
    python scripts/summarize_comparison.py output/notes/<date>
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

TICKERS_AT_SCALE = 500  # "what would the whole S&P 500 cost?"

def summarize(notes: pd.DataFrame, grades: pd.DataFrame, key: pd.DataFrame) -> pd.DataFrame:
    """One row per provider/model with the numbers that go in the comparison table."""
    graded = grades[["note_id", "accuracy", "clarity"]].merge(key, on="note_id")
    ok = notes[notes["error"].fillna("") == ""].copy()
    for column in ["advice_terms", "made_up_numbers"]:
        ok[column] = ok[column].fillna("")

    rows = []
    for (provider, model), group in ok.groupby(["provider", "model"]):
        mine = graded[graded["provider"] == provider]
        failed = notes[(notes["provider"] == provider) & (notes["error"].fillna("") != "")]
        cost = pd.to_numeric(group["cost_usd"], errors="coerce")
        rows.append({
            "Provider (model)": f"{provider} ({model})",
            "Notes (failed)": f"{len(group)} ({len(failed)})",
            "Median input tokens": int(group["input_tokens"].median()),
            "Median output tokens": int(group["output_tokens"].median()),
            "Median latency (s)": round(group["latency_s"].median(), 2),
            "Slowest (s)": round(group["latency_s"].max(), 2),
            "Cost per note ($)": round(cost.mean(), 5) if cost.notna().any() else None,
            f"Cost for {TICKERS_AT_SCALE} ($)": round(cost.mean() * TICKERS_AT_SCALE, 2) if cost.notna().any() else None,
            "Exactly 5 sentences": f"{(group['sentences'] == 5).sum()}/{len(group)}",
            "Notes with made-up numbers": int((group["made_up_numbers"] != "").sum()),
            "Notes with advice words": int((group["advice_terms"] != "").sum()),
            "Accuracy (1-3)": round(pd.to_numeric(mine["accuracy"]).mean(), 2),
            "Clarity (1-3)": round(pd.to_numeric(mine["clarity"]).mean(), 2),
        })
    return pd.DataFrame(rows)


def to_markdown(table: pd.DataFrame) -> str:
    """A Markdown table with providers as columns (easier to read with this many metrics)."""
    flipped = table.set_index("Provider (model)").T
    header = "| Metric | " + " | ".join(flipped.columns) + " |"
    divider = "|---|" + "---|" * len(flipped.columns)
    lines = [header, divider]
    for metric, values in flipped.iterrows():
        lines.append(f"| {metric} | " + " | ".join("n/a" if pd.isna(v) else str(v) for v in values) + " |")
    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/summarize_comparison.py output/notes/<date>")
    folder = Path(sys.argv[1])
    notes = pd.read_csv(folder / "notes.csv")
    grades = pd.read_csv(folder / "grading.csv")
    key = pd.read_csv(folder / "grading_key.csv")
    if grades[["accuracy", "clarity"]].isna().any().any():
        raise SystemExit("Some notes in grading.csv have no accuracy or clarity grade yet.")
    print(to_markdown(summarize(notes, grades, key)))


if __name__ == "__main__":
    main()