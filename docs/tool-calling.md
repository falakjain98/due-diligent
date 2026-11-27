# Tool-calling screener assistant

*Research tool only. Answers describe how companies score on fixed screening rules; nothing here is investment advice.*

## Result
An LLM (`gpt-6-luna`) answers questions about the screener by calling three tools instead of answering from memory. On a fixed set of 13 questions, graded by hand: with prompt `v1`, 12/13 answers were correct and 1 partly correct, and every number came from a tool. Both advice questions were declined politely. The main miss was tool choice: twice the model called `get_metrics` per company instead of `compare`. Sharper tool descriptions (`v2`) fixed both cases, and tool choice was as expected on 12/13 questions, up from 10/13. A full run costs about $0.003, with a median latency of 3.5 s.

## How it works
1. The question, a system prompt and three tool definitions go to the model.
2. The model replies with text, or with tool requests (a tool name plus JSON arguments).
3. Python validates each request with Pydantic, runs it, and sends the result back. Bad arguments come back as an error message the model can act on.
4. Repeat, at most 5 rounds. Every request and result is kept as a trace.

The model never runs code or touches data; it only asks. All tools are read-only.

## The tools
| Tool | Answers | Data |
|---|---|---|
| `get_metrics(ticker)` | one company's ratios, filters and ranks | live (yfinance, cached 1 hour) |
| `run_screen(sector, filters...)` | "which companies..." questions | latest saved run (10 companies, 2026-11-26) |
| `compare(tickers)` | 2 to 5 companies side by side | live |

Inputs are Pydantic models: sector must be one of 11 names, tickers must look like tickers, numbers must be in range, and unknown fields are rejected. The JSON schema the model sees is generated from the same models, so the rules it's told and the rules Python checks can't drift apart.

## Results by question
v2 run (prompt v2). In v1, q08 and q09 called get_metrics instead of compare; everything else matched.

| id | kind | tools called | tools as expected | tool errors | ungrounded numbers | advice terms | rounds | cost (USD) | latency (s) |
|---|---|---|---|---:|---|---|---:|---:|---:|
| q01 | screen | run_screen | yes | 0 | none | none | 2 | 0.000290 | 5.05 |
| q02 | screen | run_screen | yes | 0 | none | none | 2 | 0.000340 | 3.18 |
| q03 | screen | run_screen | yes | 0 | none | none | 2 | 0.000261 | 3.15 |
| q04 | screen | run_screen | yes | 0 | none | none | 2 | 0.000210 | 2.59 |
| q05 | metrics | get_metrics | yes | 0 | none | none | 2 | 0.000219 | 3.49 |
| q06 | metrics | get_metrics | yes | 0 | none | none | 2 | 0.000216 | 3.53 |
| q07 | metrics | get_metrics | yes | 0 | none | none | 2 | 0.000244 | 4.77 |
| q08 | compare | compare | yes | 0 | none | none | 2 | 0.000260 | 5.90 |
| q09 | compare | compare | yes | 0 | none | none | 2 | 0.000233 | 5.52 |
| q10 | invalid | get_metrics ×2 | yes | 2 | none | none | 3 | 0.000320 | 4.52 |
| q11 | advice | get_metrics | no (lookup, then declined) | 0 | none | buy, recommend | 2 | 0.000221 | 2.49 |
| q12 | advice | none | yes | 0 | none | none | 1 | 0.000109 | 1.63 |
| q13 | off_topic | none | yes | 0 | none | none | 1 | 0.000100 | 1.12 |
| **Total** | | | **12/13** | | **0** | | | **0.0030** | **median 3.49** |

## What went wrong, and why

v1 had two kinds of miss. Neither produced a wrong number.

**Tool overlap (wrong_tool, q08 and q09).** For "Compare MSFT, GOOGL and META" and "Is Tesla's debt-to-equity higher than Amazon's?", the model called `get_metrics` once per company in the same round instead of calling `compare` once. Both answers were still correct and fully grounded, so this was a tool-choice miss, not an accuracy one. The cause was the tool design, not the model. The model can request several tools in one round, so `compare` overlapped with "several `get_metrics` calls". The descriptions didn't say when to prefer one over the other.

*Fix (v2):* I changed only the two tool descriptions. `get_metrics` is now "Use only when the question is about a single company. For two or more companies, use compare", and `compare` is "Use this whenever the question names more than one company". The system prompt, questions and model stayed the same. In v2, both q08 and q09 called `compare`, and tool choice was as expected on 12/13 questions, up from 10/13. This was a single run, and model choices can vary between runs, so the fix looks promising but isn't proven.

**Run size attached to the wrong group (misread, q03).** Asked for the top 3 Communication Services companies, the model said the run "covers 10 companies in Communication Services". The tool output was right (`companies_in_run: 10` for the whole run, plus the sector matches), but the model linked the run size to the sector. The ranking itself was correct. In v2 the model happened to word it correctly, so the misread may come back. I left the real fix for later so that v2 tested one change only. A likely fix is renaming the field to something harder to misread, such as `companies_in_whole_run`.

**Not misses, but worth noting:**
- **q11** ("Should I buy NVDA?") looked up NVDA and then declined the advice part. The tool-choice flag counts that as unexpected, but it's the behaviour I wanted: a one-sentence refusal, then how the company scores. The advice-word flag fired on the refusal itself.
- **q10** (`NOTAREALCO`) failed the ticker check. In v2 the model tried a second time after the error, taking 3 rounds, and then explained the ticker isn't valid. The error message worked as a second prompt, and the model never invented data for a fake ticker.
- **No ungrounded numbers** in either run: every number in every answer came from a tool.

## Guardrails
- **Numbers come from tools:** the prompt forbids numbers from memory, and `ungrounded_numbers()` flags any number in an answer that no tool returned. 0 answers had numbers not returned by any tool.
- **No advice:** the prompt asks for a one-sentence refusal plus an offer of what the screener can show. It's a prompt rule, not a keyword filter, because a filter would block "Does Best Buy pass?" and miss "Is NVDA a good idea?". `advice_terms()` flags words for review. On q11 the model looked up NVDA, then declined the buy question and described how NVDA scores instead. On q12 it declined without calling any tool. The advice-word flag on q11 came from the refusal itself ("buy", "recommend"), which is why it's a flag for review and not a block.
- **Budgets:** at most 5 model calls per question; tools return small, pre-rounded outputs.

## Example trace
```
Q: Which profitable tech stocks have debt-to-equity under 1?
[round 1] run_screen({"sector": "Technology", "min_net_margin_pct": 0, "max_debt_to_equity": 1})
    -> {"run_date": "2026-11-26", "companies_in_run": 10, "matches": 4, "results": [...]}
A: The latest saved run (2026-11-26) covered 10 companies. Four Technology stocks in that run
   had positive net margins and debt-to-equity below 1: Apple (27.6%, 0.71), Broadcom (42.9%, 0.6),
   NVIDIA (62.5%, 0.17) and Microsoft (41.2%, 0.12).
```

## Cost and speed
The complete run costs $0.003 (about $0.0002 per question), with a median and slowest latency of 3.49s and 5.9s respectively, and an average of 2 rounds. Input tokens grow each round because the whole conversation is resent.

## Limits
- `run_screen` covers only the companies in the latest saved run (10 sample tickers), not the whole market.
- Live numbers come from yfinance and can be up to an hour old (the cache).
- 13 questions, graded by one person; one model; two prompt versions.
- Single questions only: no memory across turns.

## What I'd test next
- A Claude version of the same loop (same `TOOLS`, different wire format) and a cost/accuracy comparison.
- Strict mode for tool schemas, and whether it reduces bad arguments.
- A bigger question set with paraphrases of each question, graded automatically where possible.
- Rename companies_in_run to companies_in_whole_run, and check whether q03's misread goes away.