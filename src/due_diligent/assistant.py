"""Answer questions about the screener with an LLM that calls the tools in tools.py.

The loop: send the question and the tool list -> the model either answers, or asks for
one or more tools -> Python runs them and sends the results back -> repeat, at most
max_rounds times. Every number in an answer should come from a tool result, never from
the model's memory. Answers describe screening results; they are not investment advice.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

from pydantic import BaseModel, Field

from due_diligent import config
from due_diligent.data import DataSource
from due_diligent.models import DISCLAIMER
from due_diligent.tools import call_tool, openai_tools

# Bump whenever SYSTEM_PROMPT or a tool description changes, so old and new eval runs stay comparable.
PROMPT_VERSION = "v2"

SYSTEM_PROMPT = f"""You answer questions about a stock fundamentals screener, using its tools.

How the screener works:
- P/E filter: passes when the P/E ratio is above {config.PE_MIN} and below {config.PE_MAX}.
- Margin filter: passes when gross margin is above {config.GROSS_MARGIN_MIN:.0%} and net margin is above {config.NET_MARGIN_MIN:.0%}.
- Returns filter: passes when return on assets is above {config.ROA_MIN:.0%} and return on equity is above {config.ROE_MIN:.0%}.
- Ranks: four measures each get 1 (best) to 3 (worst); final_rank is their sum, from 4 (best) to 12 (worst).

Rules:
- Get every number from a tool. Never state a company's numbers from memory, even for well-known companies. If no tool gives you a number, say you don't have it.
- Use numbers as the tools return them. Fields ending in _pct are already percentages. Do not calculate new numbers.
- run_screen only covers the companies in the latest saved run. When you use it, say the run date and how many companies the run had.
- If a tool returns an error, fix the arguments and try once more, or tell the user what went wrong.
- Never give investment advice. Do not say whether to buy, sell or hold, do not call a stock cheap, expensive, undervalued or overvalued, and do not predict prices or returns. If asked, politely decline in one sentence, then offer to show how the company scores on the screener's rules.
- For questions the tools can't answer, say briefly what you can help with.
- Keep answers short: a few sentences or a small table. Do not add a disclaimer; one is added automatically."""

GAVE_UP = "Sorry, I couldn't finish this answer within the tool-call limit. Try a narrower question."

class AssistantError(Exception):
    """The model returned no usable answer (it failed or declined at the API level)."""

class ToolCall(BaseModel):
    """One tool request from the model, and what Python sent back."""
    round: int
    name: str
    arguments: str  # the raw JSON string the model wrote, kept as-is so we can see its mistakes
    output: dict

class Answer(BaseModel):
    """One question, the final answer, and the full trace of how it got there."""
    question: str
    text: str
    tool_calls: list[ToolCall]
    rounds: int        # model calls made (one per round)
    stopped_early: bool  # True = hit max_rounds without a final answer
    model: str
    prompt_version: str
    input_tokens: int    # summed over every round: each round resends the whole conversation
    output_tokens: int
    latency_s: float
    disclaimer: str = Field(default=DISCLAIMER)

class OpenAIAssistant:
    """The tool-calling loop on OpenAI's Responses API."""
    provider = "openai"

    def __init__(self, source: DataSource, client: Any = None, model: str = config.ASSISTANT_MODEL,
                 reasoning_effort: str | None = config.ASSISTANT_REASONING_EFFORT,
                 max_rounds: int = config.ASSISTANT_MAX_ROUNDS):
        if client is None:
            import openai  # imported here so the package works without the llm extra
            client = openai.OpenAI()
        self.source = source
        self.client = client
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.max_rounds = max_rounds

    def ask(self, question: str) -> Answer:
        extra = {"reasoning": {"effort": self.reasoning_effort}} if self.reasoning_effort else {}
        conversation: list[Any] = [{"role": "user", "content": question}]
        calls: list[ToolCall] = []
        input_tokens = output_tokens = 0
        start = time.perf_counter()

        for round_number in range(1, self.max_rounds + 1):
            response = self.client.responses.create(
                model=self.model,
                instructions=SYSTEM_PROMPT,
                input=conversation,
                tools=openai_tools(),
                **extra,
            )
            input_tokens += response.usage.input_tokens
            output_tokens += response.usage.output_tokens
            if response.status != "completed":
                raise AssistantError(f"{self.model} returned status {response.status}")

            requests = [item for item in response.output if item.type == "function_call"]
            if not requests:  # no tool wanted: this is the final answer
                text = (response.output_text or "").strip()
                if not text:
                    raise AssistantError(f"{self.model} returned no text")
                return self._answer(question, text, calls, round_number, False, input_tokens, output_tokens, start)

            # Keep the model's own turn (its tool requests, and any reasoning) in the conversation,
            # then add one result per request, matched by call_id.
            conversation += response.output
            for request in requests:
                output = call_tool(request.name, request.arguments, self.source)
                calls.append(ToolCall(round=round_number, name=request.name, arguments=request.arguments, output=output))
                conversation.append({
                    "type": "function_call_output",
                    "call_id": request.call_id,
                    "output": json.dumps(output, separators=(",", ":")),
                })

        return self._answer(question, GAVE_UP, calls, self.max_rounds, True, input_tokens, output_tokens, start)

    def _answer(self, question, text, calls, rounds, stopped_early, input_tokens, output_tokens, start) -> Answer:
        return Answer(
            question=question, text=text, tool_calls=calls, rounds=rounds, stopped_early=stopped_early,
            model=self.model, prompt_version=PROMPT_VERSION, input_tokens=input_tokens,
            output_tokens=output_tokens, latency_s=round(time.perf_counter() - start, 3),
        )


# --- checks on a finished answer -------------------------------------------------------

_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def _numbers(value: Any) -> set[float]:
    """Every number inside nested dicts/lists/strings, as positive floats ('2026-11-26' gives 2026, 11, 26)."""
    if isinstance(value, bool) or value is None:
        return set()
    if isinstance(value, (int, float)):
        return {abs(float(value))}
    if isinstance(value, str):
        return {float(n) for n in _NUMBER.findall(value)}
    if isinstance(value, dict):
        return set().union(set(), *(_numbers(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(set(), *(_numbers(item) for item in value))
    return set()


def ungrounded_numbers(answer: Answer) -> list[str]:
    """Numbers in the answer that no tool returned (and that aren't in the question or the rules).

    This is the "did it guess?" check. An answer with numbers and no tool calls will show up here.
    A hit isn't always a guess (a count like "2 companies"), so look at each one.
    """
    allowed = _numbers(answer.question) | _numbers(SYSTEM_PROMPT)
    for call in answer.tool_calls:
        allowed |= _numbers(call.output)
    return [n for n in _NUMBER.findall(answer.text) if float(n) not in allowed]


def answer_cost(answer: Answer) -> float | None:
    """Dollars, from config.PRICES_PER_MILLION; None if the model has no price yet."""
    input_price, output_price = config.PRICES_PER_MILLION.get(answer.model, (None, None))
    if input_price is None or output_price is None:
        return None
    return (answer.input_tokens * input_price + answer.output_tokens * output_price) / 1_000_000