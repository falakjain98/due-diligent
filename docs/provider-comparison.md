# Provider comparison: 5-sentence screening notes

*Week 4 experiment, run on 2026-11-25. Compares how two LLMs describe screening results. Nothing here is
investment advice; the notes describe how companies score against fixed rules.*

## Recommendation
For short screening notes, I'd use gpt-6-luna. On 10 tickers it matched claude-opus-5-5 on accuracy (3.0 vs 2.9) and clarity (2.0 vs 2.0), was faster (median 2.0s vs 2.8s), and cost about $0.00007 per note against $0.01, roughly 140 times less. Claude followed the format better (exactly 5 sentences in 10 of 10 notes, against 7 of 10), but a format slip is easy to catch in code and isn't worth a 140-times price.

## Setup
- **Task:** turn one company's screener result (`TickerScreen`) into a 5-sentence plain-English note.
- **Data:** the 10 tickers in `sample_data/` (10 notes per provider).
- **Same input for both:** each company fetched once; identical system prompt and message (prompt `v1`,
  `src/due_diligent/notes.py`); both models at low thinking effort.
- **Models and prices:** claude-opus-5-5 ($4 / $20 per 1M tokens), gpt-6-luna ($0.10 / $0.20), prices from
  each provider's pricing page on 2026-11-25.
- **Grading:** automatic checks (5 sentences, advice words, numbers not in the input) plus blind hand grades
  for accuracy and clarity (1–3), with notes shuffled and provider names hidden until grading was done.

## Results
| Metric | anthropic (claude-opus-5-5) | openai (gpt-6-luna) |
|---|---|---|
| Notes (failed) | 10 (0) | 10 (0) |
| Median input tokens | 618 | 419 |
| Median output tokens | 276 | 127 |
| Median latency (s) | 2.82 | 1.97 |
| Slowest (s) | 6.61 | 2.79 |
| Cost per note ($) | 0.01001 | 0.00007 |
| Cost for 500 ($) | 5.01 | 0.03 |
| Exactly 5 sentences | 10/10 | 7/10 |
| Notes with made-up numbers | 0 | 0 |
| Notes with advice words | 0 | 0 |
| Accuracy (1-3) | 2.9 | 3.0 |
| Clarity (1-3) | 2.0 | 2.0 |

## What the numbers say
- **Correctness:** Both models are highly accurate, claude-opus-5-5 successfully returns 5 sentences 10/10 times whereas gpt-6-luna only succeeds in doing that 7/10 times.
- **Clarity:** the clarity scores remain at a 2 throughout all notes, both models read like a checklist and rarely explain what P/E or ROE means
- **Cost:** $0.01 vs $0.00007 per note, $5 vs $0.03 for 500 tickers; a 140x gap
- **Speed:** Claude was about 0.9s slower at the median, but its slowest call took 6.6s against 2.8s, and that slow tail is what an API user notices.
- **Thinking tokens:** claude-opus-5-5 consistently uses more tokens across input, output and thinking which increase the cost as well compared to gpt-6-luna

## Example: the same company, both models
What the model sees:
```
Screening result:
{"ticker":"AAPL","metrics":{"pe_ratio":38.32,"gross_margin_pct":48.8,"net_margin_pct":27.6,"return_on_assets_pct":25.9,"return_on_equity_pct":142.3,"debt_to_equity":0.71,"capex_to_income":0.07},"filters":{"pe_filter":true,"margin_filter":true,"returns_filter":true},"ranks":{"roa_rank":1,"roe_rank":1,"debt_to_equity_rank":1,"capex_to_income_rank":1,"final_rank":4}}
```

### claude-opus-5-5
```
6.69s, in 618 / out 663 tokens
sentences: 5, advice terms: none

AAPL passes the P/E filter with a P/E ratio of 38.32, which falls inside the range the screener accepts. It also passes the margin filter, with a gross margin of 48.8% and a net margin of 27.6%, both above the screener's minimums. The returns filter is a pass as well, with a return on assets of 25.9% and a return on equity of 142.3%. Return on assets, return on equity, debt-to-equity(0.71) and capex-to-income (0.07) each earned a rank of 1, the best possible score in every ranked category. That gives AAPL a final_rank of 4, the best combined score the screener can assign, and none of its values are missing.
```

### gpt-6-luna
```
3.14s, in 419 / out 130 tokens
sentences: 5, advice terms: none

AAPL passes the P/E filter with a P/E ratio of 38.32, which is above 0 and below 50. It passes the margin filter with a gross margin of 48.8% and a net margin of 27.6%. It passes the returns filter with return on assets of 25.9% and return on equity of 142.3%. Its debt-to-equity ratio is 0.71 and its capex-to-income value is 0.07, and both receive rank 1. All four ranks are 1, giving AAPL a final rank of 4.
```

## Limits of this test
- 10 tickers, one run each: enough to see big differences, not small ones (week 8 adds error bars).
- One grader (me), so the hand grades carry my judgement.
- Prompt v1 only. Both models followed it; the prompt itself produces checklist-style notes.
- A flagship model against a much cheaper one, so part of the gap is price tier, not provider.
- Prices change; these are from 2026-11-25.

## What I'd test next
- **Prompt v2:** explain each measure in a few plain words and never use field names; rerun both models.
- **Price-matched models:** a cheaper Claude tier against gpt-6-luna.
- **Repeat runs:** 3 runs per ticker, to see how much the grades move between runs.