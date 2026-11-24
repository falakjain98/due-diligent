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

- What I learned: (compact + rounded saves 25-45%; numbers split into several tokens,
  so it is preferrable for Python to do the math and the model to only writes words)

## Context windows
- It is all the text that can be accessed and referenced by a model during responses.
- It is the working memory of the model and consists of the complete input and output of the model session.
- Looking at the token counts above, data of 500 s&p500 companies should take up about 150k - 200k tokens.
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