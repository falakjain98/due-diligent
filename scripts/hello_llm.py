"""Experiment: send the same prompt to two providers, three times each.

Prints each answer with its tokens and time, then checks whether each model
accepts a temperature setting.

Run from the repo root with your keys loaded:
    set -a; source .env; set +a
    python scripts/hello_llm.py
"""
from __future__ import annotations

import time

import anthropic
import openai

CLAUDE_MODEL = "claude-opus-5-5"
OPENAI_MODEL = "gpt-6-luna" 
RUNS = 3
PROMPT = "In two sentences, explain what a debt-to-equity ratio tells you about a company."


def ask_claude(client: anthropic.Anthropic, prompt: str, **extra) -> dict:
    """One Claude call. Returns the visible text, token counts and wall-clock time."""
    start = time.perf_counter()
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=16000,                 # a ceiling, not a target: you only pay for what's written
        output_config={"effort": "low"},  # how much the model thinks before answering
        messages=[{"role": "user", "content": prompt}],
        **extra,
    )
    seconds = time.perf_counter() - start
    if response.stop_reason == "refusal":
        text = "[the model declined to answer]"
    else:
        # The reply is a list of blocks. Thinking blocks come back empty by default;
        # the answer is in the text blocks.
        text = "".join(block.text for block in response.content if block.type == "text")
    return {
        "text": text,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,  # includes thinking tokens
        "seconds": seconds,
    }


def ask_openai(client: openai.OpenAI, prompt: str, **extra) -> dict:
    """One OpenAI call (Responses API). Same return shape as ask_claude."""
    start = time.perf_counter()
    response = client.responses.create(model=OPENAI_MODEL, input=prompt, **extra)
    seconds = time.perf_counter() - start
    details = getattr(response.usage, "output_tokens_details", None)
    return {
        "text": response.output_text,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,  # includes reasoning tokens
        "reasoning_tokens": getattr(details, "reasoning_tokens", None),
        "seconds": seconds,
    }


def try_temperature(name: str, call, **temperature_args) -> None:
    """Send a temperature setting and report whether the model accepts it."""
    try:
        call(PROMPT, **temperature_args)
        print(f"  {name}: accepted temperature")
    except (anthropic.BadRequestError, openai.BadRequestError, TypeError) as error:
        print(f"  {name}: rejected temperature -> {str(error)[:200]}")


def main() -> None:
    claude = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
    gpt = openai.OpenAI()           # reads OPENAI_API_KEY
    providers = {
        f"Claude ({CLAUDE_MODEL})": lambda prompt, **extra: ask_claude(claude, prompt, **extra),
        f"OpenAI ({OPENAI_MODEL})": lambda prompt, **extra: ask_openai(gpt, prompt, **extra),
    }

    print(f"Prompt: {PROMPT}\n")
    for name, call in providers.items():
        print(f"=== {name} ===")
        for run in range(1, RUNS + 1):
            result = call(PROMPT)
            extra_info = ""
            if result.get("reasoning_tokens") is not None:
                extra_info = f", of which reasoning {result['reasoning_tokens']}"
            print(
                f"[run {run}] {result['seconds']:.2f}s, "
                f"in {result['input_tokens']} / out {result['output_tokens']} tokens{extra_info}"
            )
            print(f"  {result['text']}\n")

    print("Does each model accept temperature?")
    claude_name, openai_name = providers
    # The current Anthropic SDK has dropped `temperature` from its arguments, so we
    # slip it into the raw request body to hear what the API itself says.
    try_temperature(claude_name, providers[claude_name], extra_body={"temperature": 1.0})
    try_temperature(openai_name, providers[openai_name], temperature=1.0)


if __name__ == "__main__":
    main()