"""Extraction tests. No network: a fake client stands in for the OpenAI SDK."""
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from due_diligent.edgar import Filing
from due_diligent.extract import (
    PROMPT_VERSION, SYSTEM_PROMPT, Amount, Extraction, ExtractError, FilingExtract, OpenAIExtractor,
    ungrounded, user_message,
)

FILING = Filing("AAPL", 320193, "Apple Inc.", "10-K", "0000320193-25-000079",
                "2025-10-31", "2025-09-27", "aapl-20250927.htm")
TEXT = ("Item 1A. Risk Factors\nCompetition is intense and could reduce our margins.\n"
        "Item 8. Financial Statements\nTotal net sales $ 416,161\nNet income $ 112,010\n"
        "We expect revenue to grow next year.")


def make_data(**changes) -> dict:
    risk = {"title": "Competition", "quote": "Competition is intense and could reduce our margins."}
    data = {
        "company_name": "Apple Inc.", "fiscal_year": 2025, "fiscal_year_end": "2025-09-27",
        "revenue": {"as_written": "416,161", "scale": "millions"},
        "net_income": {"as_written": "112,010", "scale": "millions"},
        "total_debt": None,
        "segments": [{"name": "Americas", "revenue": None}],
        "top_risks": [risk] * 5,
        "guidance": "Revenue is expected to grow.", "guidance_quote": "We expect revenue to grow next year.",
    }
    return data | changes


class FakeOpenAI:
    """Looks like openai.OpenAI() just enough for OpenAIExtractor, and records the request."""
    def __init__(self, status="completed", data=None, error=None):
        self.sent = None
        self.error = error
        self.response = SimpleNamespace(
            status=status,
            output_parsed=None if data is None else FilingExtract(**data),
            usage=SimpleNamespace(input_tokens=90_000, output_tokens=1_500),
        )
        self.responses = SimpleNamespace(parse=self._parse)

    def _parse(self, **request):
        self.sent = request
        if self.error:
            raise self.error
        return self.response


# --- amounts ---------------------------------------------------------------------

def test_amount_in_millions_becomes_dollars():
    assert Amount(as_written="416,161", scale="millions").dollars() == 416_161_000_000


def test_brackets_mean_negative():
    assert Amount(as_written="(1,234)", scale="thousands").dollars() == -1_234_000


def test_dollar_sign_and_decimals_are_fine():
    assert Amount(as_written="$ 2.5", scale="billions").dollars() == 2_500_000_000


def test_words_are_not_an_amount():
    with pytest.raises(ValidationError):
        Amount(as_written="416 billion", scale="millions")


# --- the schema --------------------------------------------------------------------

def test_valid_extract_parses():
    assert FilingExtract(**make_data()).revenue.dollars() == 416_161_000_000


@pytest.mark.parametrize("changes", [
    {"fiscal_year": 25},                    # not a plausible year
    {"fiscal_year_end": "Sept 27, 2025"},   # not YYYY-MM-DD
    {"top_risks": []},                      # must be exactly 5
    {"revenue": {"as_written": "416,161", "scale": "lakhs"}},  # not an allowed scale
])
def test_bad_extracts_are_rejected(changes):
    with pytest.raises(ValidationError):
        FilingExtract(**make_data(**changes))


# --- the extractor -----------------------------------------------------------------

def test_extractor_sends_schema_and_rules():
    client = FakeOpenAI(data=make_data())
    OpenAIExtractor(client=client, model="m", reasoning_effort="low").extract(FILING, TEXT)
    assert client.sent["text_format"] is FilingExtract
    assert client.sent["instructions"] == SYSTEM_PROMPT
    assert client.sent["reasoning"] == {"effort": "low"}
    assert TEXT in client.sent["input"]


def test_period_end_is_not_given_to_the_model():
    assert FILING.report_date not in user_message(FILING, TEXT)


def test_extractor_returns_tokens_and_version():
    extraction = OpenAIExtractor(client=FakeOpenAI(data=make_data()), model="m").extract(FILING, TEXT, False)
    assert (extraction.input_tokens, extraction.output_tokens) == (90_000, 1_500)
    assert extraction.prompt_version == PROMPT_VERSION
    assert extraction.used_sections is False


def test_incomplete_reply_raises():
    with pytest.raises(ExtractError):
        OpenAIExtractor(client=FakeOpenAI(status="incomplete", data=make_data()), model="m").extract(FILING, TEXT)


def test_schema_break_raises_extract_error():
    try:
        FilingExtract(**make_data(top_risks=[]))
    except ValidationError as error:
        broken = error
    with pytest.raises(ExtractError, match="schema"):
        OpenAIExtractor(client=FakeOpenAI(error=broken), model="m").extract(FILING, TEXT)


# --- grounding ---------------------------------------------------------------------

def extraction_of(data: dict) -> Extraction:
    return Extraction(ticker="AAPL", accession=FILING.accession, provider="openai", model="m",
                      prompt_version="v1", used_sections=True, data=FilingExtract(**data),
                      input_tokens=1, output_tokens=1, latency_s=1.0)


def test_numbers_and_quotes_found_in_text():
    assert ungrounded(extraction_of(make_data()), TEXT) == []


def test_curly_quotes_and_spacing_still_match():
    text = TEXT.replace("next year.", "next\n  year.").replace("our", "our")
    quote = "We expect revenue to grow next year."
    assert ungrounded(extraction_of(make_data(guidance_quote=quote)), text) == []


def test_invented_number_and_quote_are_flagged():
    data = make_data(net_income={"as_written": "99,999", "scale": "millions"},
                     guidance_quote="We will double sales.")
    assert ungrounded(extraction_of(data), TEXT) == ["net_income", "guidance"]