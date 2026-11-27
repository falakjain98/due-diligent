# 10-K extraction: LLM vs XBRL

*Experiment, run on 2026-11-25. Extracts facts that companies state in their 10-K filings and checks
them against the XBRL data filed with them. It describes what filings say; nothing here is investment advice.*

## Result
On 10 companies' latest 10-Ks, gpt-6-luna matched XBRL on 44 of 49 checked fields (90%). Revenue
matched 10/10, net income 10/10, fiscal year 10/10. Total debt matched 4/9, because companies report debt in different ways: principal vs carrying amount, and often with no single printed total. Of the 5 misses, 2 were extraction errors and 3 were definition differences. The whole run cost $0.07 and took 6s per filing at the median.

## Setup
- **Filings:** latest 10-K for AAPL, NVDA, MSFT, AMZN, GOOGL, META, TSLA, AVGO, BRK-B, JNJ, from SEC
  EDGAR's submissions API (User-Agent set, at most 5 requests a second, cached on disk).
- **Input:** Items 1, 1A, 7 and 8 only, cut at their headings (plus Item 15 when Item 8 only points to it). All 10 filings split cleanly after two fixes (see Input size).
- **Model:** gpt-6-luna, low reasoning effort, structured outputs with a Pydantic schema, prompt `v1`
  (`src/due_diligent/extract.py`).
- **Answer key:** XBRL company facts from the same filing (same accession number and period end; a full year for revenue and net income). Match = within 1%.

## Input size
| Ticker | Full text tokens | Sections tokens | Kept | Input cost, gpt-6-luna | Input cost, claude-opus-5-5 |
|---|---:|---:|---:|---:|---:|
| AAPL | 48,525 | 37,840 | 78% | $0.0038 | $0.151 |
| NVDA | 67,981 | 60,332 | 89% | $0.0060 | $0.241 |
| MSFT | 67,150 | 56,381 | 84% | $0.0056 | $0.226 |
| AMZN | 58,788 | 49,719 | 85% | $0.0050 | $0.199 |
| GOOGL | 71,133 | 58,924 | 83% | $0.0059 | $0.236 |
| META | 101,393 | 82,399 | 81% | $0.0082 | $0.330 |
| TSLA | 78,523 | 69,808 | 89% | $0.0070 | $0.279 |
| AVGO | 74,000 | 62,287 | 84% | $0.0062 | $0.249 |
| BRK-B | 106,155 | 95,702 | 90% | $0.0096 | $0.383 |
| JNJ | 91,361 | 79,776 | 87% | $0.0080 | $0.319 |
| **Total** | **765,009** | **653,168** | **85%** | **$0.065** | **$2.61** |

Token counts from tiktoken's o200k_base; costs are input only, at the prices in `config.py`.

Sending Items 1, 1A, 7 and 8 kept about 85% of the text, so most of a 10-K's length is in the sections we need. The input for all 10 filings costs about 7 cents with gpt-6-luna and about $2.60 with claude-opus-5-5. At this size, the price per token matters much more than trimming. The largest input (BRK-B, about 96,000 tokens) fits easily in a 1M-token context window.

Two filings needed fixes to the section split. Microsoft repeats "Item N" at the top of every page, which split each section into single pages (6% kept at first), so a heading that repeats the item before it is now skipped. NVIDIA's Item 8 only points to Item 15, where its statements are, so Item 15 is sent when Item 8 is under 2,000 characters. `sections_found` was True both times; the `Kept` column is what showed something was wrong.

## Match rate
| Field | Matched | Checked | Not in XBRL |
|---|---|---|---|
| fiscal_year | 10 | 10 | 0 |
| fiscal_year_end | 10 | 10 | 0 |
| revenue | 10 | 10 | 0 |
| net_income | 10 | 10 | 0 |
| total_debt | 4 | 9 | 1 |
| **All** | **44** | **49** | **1** |

"Checked" counts only fields where XBRL had an answer. A match is within 1% of the XBRL value from the same filing.

## What the misses were
| Ticker | Field | Extracted | XBRL | Label | Why |
|---|---|---|---|---|---|
| AAPL | total_debt | null | 80,111M | definition | No single debt total is printed and the prompt forbids adding lines up. The model returned null in this run and 78,114M in an earlier one. |
| GOOGL | total_debt | 48,500M | 49,085M | extraction_error | Rounded figure from the MD&A text; the exact total in the debt table matches XBRL. |
| TSLA | total_debt | 8,177M | 6,584M | definition | Model took unpaid principal; XBRL `LongTermDebt` is the carrying amount. |
| AVGO | total_debt | 67,120M | 65,136M | definition | Model took total principal (67,120M, the sum of yearly repayments). XBRL is the carrying amount (3,152M current + 61,984M non-current), net of 1,984M of discounts and fees. |
| JNJ | total_debt | 47,900M | 49,933M | extraction_error | Rounded figure from the MD&A text, not the balance-sheet total. |

Not in XBRL: BRK-B total_debt (the model gave 129,081M; Berkshire has no fact under any of our debt concepts).

Every revenue, net income and fiscal-year field matched. All five misses are total debt, and only two are model errors: both took a rounded number from the text instead of the table. The other three come from how "total debt" is defined: principal vs carrying amount, and a prompt rule that rules out adding lines up. META's 59,000M is probably a rounded text figure too; it counts as a match only because it falls within 1%.

## Grounding
Numbers and quotes not found in the filing text: TSLA risk 5 (quote) and BRK-B guidance (quote). Every number appears in its filing. Both are near-copies (the model changed a few words), which the strict check counts as not found; no quote was invented outright. The number misses above are about picking the wrong line, not inventing figures.

## What the check can't see
By eye on AAPL: segments right (Apple's five geographic segments, which add up exactly to total revenue), top 5 risks plausible and quoted word for word, guidance weak.
Apple's "guidance" was "The Company expects these trends to intensify for memory and storage components", a real sentence, but a comment on supply costs, not an outlook for next year. Apple gives no yearly outlook in its 10-K, so null would have been the better answer. The quote check passes it because the sentence is real; only reading it shows it answers the wrong question.

## Cost and speed
| | Median | Slowest | Total |
|---|---|---|---|
| Input tokens | 62,086 | 96,485 | 660,940 |
| Output tokens | 842 | 1,315 | 8,477 |
| Latency (s) | 6.4 | 9.5 | 65.3 |
| Cost ($) | 0.0063 | 0.0099 | 0.068 |

All 10 filings cost about 7 cents with gpt-6-luna. Input tokens are 99% of the total, so input price decides the cost. At the same token counts, claude-opus-5-5 would cost about $2.81.

## Example: Apple
From the first run (Session 3); prompt v1, 38,616 input and 695 output tokens, $0.004, 6.6 s.
```json
{
  "fiscal_year": 2026,
  "fiscal_year_end": "2026-09-26",
  "revenue": {"as_written": "478,834", "scale": "millions"},
  "net_income": {"as_written": "132,175", "scale": "millions"},
  "total_debt": {"as_written": "78,114", "scale": "millions"},
  "top_risks": [
    {"title": "Macroeconomic conditions",
     "quote": "Adverse macroeconomic conditions, including slow growth or recession, high unemployment, inflation, tighter credit, higher interest rates, and currency fluctuations, can adversely impact consumer confidence and spending and materially adversely affect demand for the Company’s products and services."},
    {"title": "Component and computing resource availability",
     "quote": "The Company currently obtains certain components from single or limited sources, which exposes it to significant supply and pricing risks."}
  ],
  "guidance": "The Company expects supply constraints and rising costs for key components to intensify for memory and storage components.",
  "guidance_quote": "The Company expects these trends to intensify for memory and storage components."
}
```

## Limits
- 10 companies, one run each. AAPL's debt changed between two runs, so results can vary from run to run.
- "Total debt" uses our own definition (carrying amount of long-term debt + commercial paper or short-term borrowings); companies' own totals differ, notably principal vs carrying amount.
- XBRL can't check segments, risks or guidance; those were checked by eye on AAPL only.
- Section splitting relies on "Item N." headings. Two layouts needed fixes (Microsoft's repeated page headers, NVIDIA's statements under Item 15); other filings may need more.
- The 10 filings cover different fiscal years (Nov 2025 to Sep 2026), so the companies can't be compared side by side.
- Prices from 2026-11-25.

## What I'd test next
- **Debt as parts:** extract each debt line from the balance sheet as its own `Amount`, add them up in Python, and say whether each is principal or carrying amount. This should fix all five debt misses without asking the model to do arithmetic.
- **Repeat runs:** 3 runs per filing, to see how often fields change between runs (AAPL's debt was 78,114M in one run and null in the next).
- **Guidance:** a stricter rule ("only an explicit outlook for the next fiscal year, else null"), checked by eye on the same companies.
- **Looser quote matching:** count near-copies (for example, 95% of words the same) as found, so the grounding check separates small wording changes from invented sentences.
- **Segment revenue against XBRL:** segment numbers are tagged with dimensions, which company facts leaves out, so this needs the full XBRL file from each filing.