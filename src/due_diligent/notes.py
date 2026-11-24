"""Write a short plain-English note about one company's screening result with an LLM.

Python computes and formats every number; the model only describes the numbers it is given.
A note describes how a company scores against fixed rules. It is not investment advice.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Protocol

from pydantic import BaseModel, Field

from due_diligent import config
from due_diligent.models import DISCLAIMER, TickerScreen

# Bump this whenever SYSTEM_PROMPT or user_message changes, so old and new results stay comparable.
PROMPT_VERSION = "v1"

SYSTEM_PROMPT = f"""You explain the results of a stock fundamentals screener to a reader who is not a finance expert.

How the screener works:
- P/E filter: passes when the P/E ratio is above {config.PE_MIN} and below {config.PE_MAX}.
- Margin filter: passes when gross margin is above {config.GROSS_MARGIN_MIN:.0%} and net margin is above {config.NET_MARGIN_MIN:.0%}.
- Returns filter: passes when return on assets is above {config.ROA_MIN:.0%} and return on equity is above {config.ROE_MIN:.0%}.
- Ranks: return on assets, return on equity, debt-to-equity and capex-to-income each get a rank from 1 (best) to 3 (worst). final_rank is the sum of the four, from 4 (best) to 12 (worst).
- A missing value (null) fails its filter and gets rank 3.

Write a note about the company in the input:
- Exactly 5 sentences, as one paragraph. No lists, headings or bold text.
- Use only numbers that appear in the input, written as they appear. Do not calculate new numbers.
- Say plainly when a value is missing.
- Describe how the company scores on these rules. Do not judge it: never say whether to buy, sell or hold, never call the stock cheap, expensive, undervalued or overvalued, and never predict its price.
- Do not add a disclaimer. One is added automatically."""


class NoteError(Exception):
    """The model returned no usable note (it declined, or ran out of room)."""


class Note(BaseModel):
    """One generated note, plus what it cost to make."""
    ticker: str
    provider: str
    model: str
    prompt_version: str
    text: str
    input_tokens: int
    output_tokens: int  # includes any hidden thinking / reasoning tokens
    latency_s: float
    disclaimer: str = Field(default=DISCLAIMER)


class NoteWriter(Protocol):
    """Anything that can turn a screening result into a Note."""
    provider: str
    model: str

    def write(self, screen: TickerScreen) -> Note: ...


# --- the input the model sees -----------------------------------------------------

def _pct(value: float | None) -> float | None:
    """0.4623451 -> 46.2 (a percentage), or None if missing."""
    return None if value is None else round(value * 100, 1)


def _num(value: float | None) -> float | None:
    """34.123456 -> 34.12, or None if missing."""
    return None if value is None else round(value, 2)


def prompt_input(screen: TickerScreen) -> dict:
    """The compact, pre-formatted facts the model is allowed to use.

    Python does the formatting (rounding, fractions to percentages) so the model never
    has to do arithmetic. price_to_book is left out because no rule uses it.
    """
    m = screen.metrics
    return {
        "ticker": screen.ticker,
        "metrics": {
            "pe_ratio": _num(m.pe_ratio),
            "gross_margin_pct": _pct(m.gross_margin),
            "net_margin_pct": _pct(m.net_margin),
            "return_on_assets_pct": _pct(m.return_on_assets),
            "return_on_equity_pct": _pct(m.return_on_equity),
            "debt_to_equity": _num(m.debt_to_equity),
            "capex_to_income": _num(m.capex_to_income),
        },
        "filters": screen.filters.model_dump(),
        "ranks": screen.ranks.model_dump(),
    }


def user_message(screen: TickerScreen) -> str:
    """The per-company part of the prompt: compact JSON (fewer tokens, see Session 1)."""
    return "Screening result:\n" + json.dumps(prompt_input(screen), separators=(",", ":"))


# --- one class per provider ----------------------------------------------------------

class ClaudeWriter:
    """Writes notes with Anthropic's Claude."""
    provider = "anthropic"

    def __init__(self, client: Any = None, model: str = config.CLAUDE_MODEL, effort: str = config.CLAUDE_EFFORT):
        if client is None:
            import anthropic  # imported here so the rest of the package works without the llm extra
            client = anthropic.Anthropic()
        self.client = client
        self.model = model
        self.effort = effort

    def write(self, screen: TickerScreen) -> Note:
        start = time.perf_counter()
        response = self.client.messages.create(
            model=self.model,
            max_tokens=16000,
            output_config={"effort": self.effort},
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message(screen)}],
        )
        latency = time.perf_counter() - start
        if response.stop_reason in ("refusal", "max_tokens"):
            raise NoteError(f"{self.model} stopped with {response.stop_reason} for {screen.ticker}")
        text = "".join(block.text for block in response.content if block.type == "text").strip()
        if not text:
            raise NoteError(f"{self.model} returned no text for {screen.ticker}")
        return Note(
            ticker=screen.ticker, provider=self.provider, model=self.model, prompt_version=PROMPT_VERSION,
            text=text, input_tokens=response.usage.input_tokens, output_tokens=response.usage.output_tokens,
            latency_s=round(latency, 3),
        )


class OpenAIWriter:
    """Writes notes with OpenAI (Responses API)."""
    provider = "openai"

    def __init__(self, client: Any = None, model: str = config.OPENAI_MODEL,
                 reasoning_effort: str | None = config.OPENAI_REASONING_EFFORT):
        if client is None:
            import openai
            client = openai.OpenAI()
        self.client = client
        self.model = model
        self.reasoning_effort = reasoning_effort

    def write(self, screen: TickerScreen) -> Note:
        extra = {"reasoning": {"effort": self.reasoning_effort}} if self.reasoning_effort else {}
        start = time.perf_counter()
        response = self.client.responses.create(
            model=self.model,
            instructions=SYSTEM_PROMPT,   # OpenAI's name for the system prompt
            input=user_message(screen),
            **extra,
        )
        latency = time.perf_counter() - start
        text = (response.output_text or "").strip()
        if response.status != "completed" or not text:
            raise NoteError(f"{self.model} returned status {response.status} for {screen.ticker}")
        return Note(
            ticker=screen.ticker, provider=self.provider, model=self.model, prompt_version=PROMPT_VERSION,
            text=text, input_tokens=response.usage.input_tokens, output_tokens=response.usage.output_tokens,
            latency_s=round(latency, 3),
        )


# --- quick automatic checks (Session 4 uses these) ---------------------------------

ADVICE_TERMS = [
    "buy", "sell", "hold", "recommend", "recommendation", "undervalued", "overvalued",
    "cheap", "expensive", "bargain", "price target", "target price", "good investment",
]


def sentence_count(text: str) -> int:
    """Count sentences: a split after . ! or ? followed by a space, so '34.1' isn't split."""
    return len([part for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part])


def advice_terms(text: str) -> list[str]:
    """Advice-sounding words found in the text, as whole words ('threshold' doesn't match 'hold')."""
    return sorted(term for term in ADVICE_TERMS if re.search(rf"\b{re.escape(term)}\b", text, re.IGNORECASE))