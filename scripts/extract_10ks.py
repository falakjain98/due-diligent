"""Extract facts from each downloaded 10-K with the LLM, then check them against XBRL.

Writes to output/extractions/<today>/ (git-ignored):
  <TICKER>.json   the full extraction (reused on a rerun the same day, so you only pay once)
  checks.csv      one row per checked field: extracted vs XBRL, status, % difference
  summary.csv     one row per company: match rate, ungrounded fields, tokens, cost, latency

Run from the repo root after download_10ks.py, with SEC_USER_AGENT and OPENAI_API_KEY set:
    python scripts/extract_10ks.py            # every filing in output/edgar/filings.csv
    python scripts/extract_10ks.py AAPL       # just these (try one first)
    python scripts/extract_10ks.py --fresh    # ignore today's saved extractions and pay again
"""
from __future__ import annotations

import logging
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

import pandas as pd

from due_diligent.edgar import EdgarClient, read_filings
from due_diligent.extract import Extraction, ExtractError, OpenAIExtractor, extraction_cost, ungrounded
from due_diligent.filings import extraction_text, filing_text
from due_diligent.xbrl import check_extraction, match_rate

logger = logging.getLogger("extract_10ks")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    args = sys.argv[1:]
    fresh = "--fresh" in args
    only = [arg.upper() for arg in args if not arg.startswith("--")]

    out = Path("output/extractions") / date.today().isoformat()
    out.mkdir(parents=True, exist_ok=True)
    client = EdgarClient()
    extractor = OpenAIExtractor()

    all_checks, summary = [], []
    filings = [f for f in read_filings("output/edgar/filings.csv") if not only or f.ticker in only]
    for filing in filings:
        text = filing_text(client.filing_html(filing))
        saved = out / f"{filing.ticker}.json"
        if saved.exists() and not fresh:
            extraction = Extraction.model_validate_json(saved.read_text())
        else:
            model_text, used_sections = extraction_text(text)
            try:
                extraction = extractor.extract(filing, model_text, used_sections)
            except ExtractError as error:
                logger.warning("Extraction failed: %s", error)
                summary.append({"ticker": filing.ticker, "error": str(error)[:200]})
                continue
            saved.write_text(extraction.model_dump_json(indent=2))

        checks = check_extraction(extraction, client.company_facts(filing.cik), filing)
        all_checks += checks
        rate = match_rate(checks)
        summary.append({
            "ticker": filing.ticker,
            "match_rate": None if rate is None else round(rate, 2),
            "ungrounded": ";".join(ungrounded(extraction, text)),
            "used_sections": extraction.used_sections,
            "input_tokens": extraction.input_tokens,
            "output_tokens": extraction.output_tokens,
            "cost_usd": extraction_cost(extraction),
            "latency_s": extraction.latency_s,
        })

    checks_table = pd.DataFrame([asdict(check) for check in all_checks])
    summary_table = pd.DataFrame(summary)
    checks_table.to_csv(out / "checks.csv", index=False)
    summary_table.to_csv(out / "summary.csv", index=False)

    print(summary_table.to_string(index=False))
    if not checks_table.empty:
        scored = checks_table[checks_table["status"] != "missing_xbrl"]
        by_field = scored.groupby("field")["status"].apply(lambda s: f"{(s == 'match').sum()}/{len(s)}")
        print("\nMatches by field (XBRL had an answer):\n" + by_field.to_string())
        print(f"\nOverall match rate: {(scored['status'] == 'match').mean():.0%} of {len(scored)} checks")
    print(f"Saved to {out}")


if __name__ == "__main__":
    main()