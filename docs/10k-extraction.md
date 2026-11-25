# 10-K extraction: LLM vs XBRL

*Experiment. Extracts facts that companies state in their 10-K filings and checks them against
the XBRL data filed with them. It describes what filings say; nothing here is investment advice.*

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