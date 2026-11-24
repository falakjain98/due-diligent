"""Note writer tests. No network: fake clients stand in for the provider SDKs."""
from types import SimpleNamespace

import pytest

from due_diligent import config
from due_diligent.models import TickerScreen
from due_diligent.notes import (
    PROMPT_VERSION, SYSTEM_PROMPT, ClaudeWriter, NoteError, OpenAIWriter,
    advice_terms, prompt_input, sentence_count, user_message,
)

ROW = {
    "ticker": "GOOD",
    "pe_ratio": 20.123456, "price_to_book": 3.0, "gross_margin": 0.4623451, "net_margin": 0.2,
    "return_on_assets": 0.25, "return_on_equity": 0.25, "debt_to_equity": 0.5, "capex_to_income": None,
    "pe_filter": True, "margin_filter": True, "returns_filter": True,
    "roa_rank": 1, "roe_rank": 1, "debt_to_equity_rank": 1, "capex_to_income_rank": 3, "final_rank": 6,
}
SCREEN = TickerScreen.from_row(ROW)
FIVE_SENTENCES = "One. Two has a P/E of 20.12. Three! Four? Five."


class FakeClaude:
    """Looks like anthropic.Anthropic() just enough for ClaudeWriter, and records the request."""
    def __init__(self, stop_reason="end_turn", text=FIVE_SENTENCES):
        self.sent = None
        self.response = SimpleNamespace(
            stop_reason=stop_reason,
            content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
            usage=SimpleNamespace(input_tokens=300, output_tokens=150),
        )
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **request):
        self.sent = request
        return self.response


class FakeOpenAI:
    """Looks like openai.OpenAI() just enough for OpenAIWriter, and records the request."""
    def __init__(self, status="completed", text=FIVE_SENTENCES):
        self.sent = None
        self.response = SimpleNamespace(
            status=status, output_text=text,
            usage=SimpleNamespace(input_tokens=250, output_tokens=400),
        )
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **request):
        self.sent = request
        return self.response


# --- the prompt ---------------------------------------------------------------------

def test_prompt_input_rounds_and_converts_to_percent():
    metrics = prompt_input(SCREEN)["metrics"]
    assert metrics["pe_ratio"] == 20.12
    assert metrics["gross_margin_pct"] == 46.2
    assert metrics["return_on_assets_pct"] == 25.0


def test_prompt_input_keeps_missing_values_and_drops_unused_columns():
    data = prompt_input(SCREEN)
    assert data["metrics"]["capex_to_income"] is None
    assert "price_to_book" not in data["metrics"]
    assert data["ranks"]["final_rank"] == 6


def test_user_message_is_compact_json_with_the_ticker():
    message = user_message(SCREEN)
    assert '"ticker":"GOOD"' in message
    assert ": " not in message  # compact: no spaces after colons


def test_system_prompt_uses_thresholds_from_config():
    assert f"below {config.PE_MAX}" in SYSTEM_PROMPT
    assert "not" in SYSTEM_PROMPT.lower() and "buy" in SYSTEM_PROMPT


# --- the writers ----------------------------------------------------------------------

def test_claude_writer_returns_a_note():
    fake = FakeClaude()
    note = ClaudeWriter(client=fake, model="claude-test", effort="low").write(SCREEN)
    assert note.text == FIVE_SENTENCES
    assert (note.input_tokens, note.output_tokens) == (300, 150)
    assert (note.provider, note.model, note.prompt_version) == ("anthropic", "claude-test", PROMPT_VERSION)
    assert "not investment advice" in note.disclaimer.lower()
    assert fake.sent["system"] == SYSTEM_PROMPT
    assert fake.sent["output_config"] == {"effort": "low"}


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_claude_writer_raises_when_there_is_no_usable_note(stop_reason):
    with pytest.raises(NoteError):
        ClaudeWriter(client=FakeClaude(stop_reason=stop_reason)).write(SCREEN)


def test_openai_writer_returns_a_note():
    fake = FakeOpenAI()
    note = OpenAIWriter(client=fake, model="gpt-test", reasoning_effort="low").write(SCREEN)
    assert note.text == FIVE_SENTENCES
    assert (note.input_tokens, note.output_tokens) == (250, 400)
    assert note.provider == "openai"
    assert fake.sent["instructions"] == SYSTEM_PROMPT
    assert fake.sent["reasoning"] == {"effort": "low"}


def test_openai_writer_without_reasoning_effort_sends_no_reasoning_setting():
    fake = FakeOpenAI()
    OpenAIWriter(client=fake, model="gpt-test", reasoning_effort=None).write(SCREEN)
    assert "reasoning" not in fake.sent


def test_openai_writer_raises_on_incomplete_response():
    with pytest.raises(NoteError):
        OpenAIWriter(client=FakeOpenAI(status="incomplete"), reasoning_effort=None).write(SCREEN)


def test_both_writers_get_the_same_prompt():
    claude, gpt = FakeClaude(), FakeOpenAI()
    ClaudeWriter(client=claude).write(SCREEN)
    OpenAIWriter(client=gpt).write(SCREEN)
    assert claude.sent["system"] == gpt.sent["instructions"]
    assert claude.sent["messages"][0]["content"] == gpt.sent["input"]


# --- the checks -------------------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    (FIVE_SENTENCES, 5),
    ("Net margin is 20.5% and P/E is 34.1.", 1),  # decimals don't split sentences
    ("", 0),
])
def test_sentence_count(text, expected):
    assert sentence_count(text) == expected


def test_advice_terms_finds_whole_words_only():
    assert advice_terms("Investors may want to BUY it; it looks undervalued.") == ["buy", "undervalued"]
    assert advice_terms("It passes the threshold and sells phones.") == []