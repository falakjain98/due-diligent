# LLM fundamentals: notes

Working notes from week 4 of building due-diligent. Experiments are in `scripts/`.

## Tokens
- It is the smallest unit of textual or numerical information that LLMs read as one input/output unit during inference.
- Input tokens are cheaper since they are read simulataneously while output tokens are created sequentially and memory constrained.
- Experiment: token counts for AAPL's screener JSON (table below).

| Format | Chars | Claude tokens | OpenAI tokens |
|---|---|---|---|
| pretty JSON | 618 | 314 | 221 |
| compact JSON | 492 | 251 | 155 |
| compact + rounded | 461 | 237 | 141 |

- What I learned: (compact + rounded saves 25-36%; numbers split into several tokens,
  so it is preferrable for Python to do the math and the model to only writes words)

## Context windows
- It is all the text that can be accessed and referenced by a model during responses.
- It is the working memory of the model and consists of the complete input and output of a single request.
- Looking at the token counts above, data of 500 s&p500 companies should take up about 100k - 120k tokens.
- While it is well under the 1M context window contraint of the latest models, all the companies should not be fit into one request for the following reasons:
  - Quality degrades as context window increases regardless of maximum limit.
  - The wait time for responses increases which is further limited by output length caps.
  - It creates a single point of failure and the complete request has to be run again in case of any issues.

## Transformers
- **The next-token loop:** the model splits the prompt into tokens and turns each
  one into a vector (a list of numbers). Its layers then let those vectors share
  information, so each one ends up carrying its meaning in context. At the end,
  the model outputs a probability for every token in its vocabulary. One token is
  picked, added to the end of the text, and the whole loop runs again until the
  answer is finished.
- **What attention does:** it lets every token look at every other token in the
  context and decide which ones matter for its own meaning. Example: in "Apple
  cut its capex because it expects lower iPhone demand", attention lets "it" link
  back to "Apple" (the company, not the fruit) because of "capex" and "iPhone".

## Embeddings
- An embedding is a list of numbers that represents a text's meaning numerically.
- Cosine similarity measures how closely two of those lists point the same way: near 1 means similar meaning.
- Experiment: 6 sentences, 2 topics (`scripts/explore_embeddings.py`). Highest pair: S1 & S2: 0.7, lowest: S1 & S4: 0.25.
- What I learned: Completely different phrases such as 'lot of debt' and 'highly leveraged' have a high cosine similarity since they have a similar meaning despite no commonality in vocabulary.

## Sampling
- The model gives a probability for every possible next token and one is sampled from them. Low temperature almost always picks the top token; high temperature spreads the choice out. Top-p only samples from the most likely tokens whose probabilities add up to p (e.g. 0.9).
- Experiment: same prompt, 3 runs per provider (`scripts/hello_llm.py`).

| Provider (model) | Median time | Input tokens | Output tokens | Visible answer | Temperature accepted? |
|---|---|---|---|---|---|
| Claude (claude-opus-5-5, effort low) | 2.35s | 35 | 135 | ~65 words | No |
| OpenAI (gpt-6-luna) | 2.86s | 24 | 85 | ~40 words | Yes |

- What I learned:
  - The 3 answers per provider were the same idea in different words; so one run
    isn't enough to judge a prompt, and evals need several runs.
  - Hidden thinking is billed as output. Claude wrote ~65 words (~85 tokens) but billed 135 output tokens, so ~50 were thinking at effort low. OpenAI wrote ~40 words (~55 tokens) but billed 85, so ~30 were reasoning: so much of what I paid for was text I never saw.
  - The same prompt was 35 input tokens at Claude and 24 at OpenAI: different tokenizers (plus a few tokens
    of message wrapping).
  - Claude Opus 5.5 rejects temperature; gpt-6-luna accepted it. Newer models are steered with the prompt and effort instead.

## What surprised me
- 30-40% of the total output tokens were thinking tokens.
- that the newest models refuse temperature and take effort as an input to guide models.
- one model turned out to be 140x more expensive that the other but both models performed similarly for this use case.
- that both models followed "use only numbers from the input" so well; the hard part was clarity where the responses just seemed like a laundry list rather than well-explained and articulated financial metrics.