import json
from types import SimpleNamespace

import pytest

from due_diligent import assistant
from due_diligent.assistant import Answer, AssistantError, OpenAIAssistant, ToolCall
from test_pipeline import GOOD, FakeSource

SOURCE = FakeSource({"GOOD": GOOD})

def tool_request(name: str, arguments: dict, call_id: str):
    return SimpleNamespace(type="function_call", name=name, arguments=json.dumps(arguments), call_id=call_id)

def reply(output=(), text="", status="completed"):
    """A fake Responses API reply: a list of output items, the joined text, and token usage."""
    return SimpleNamespace(status=status, output=list(output), output_text=text,
                           usage=SimpleNamespace(input_tokens=100, output_tokens=20))

class FakeClient:
    """Plays back scripted replies and records what the assistant sent each round."""
    def __init__(self, *replies):
        self.replies = list(replies)
        self.sent = []
        self.responses = self

    def create(self, **kwargs):
        self.sent.append({**kwargs, "input": list(kwargs["input"])})  # copy: the list grows later
        return self.replies.pop(0)

def test_answer_without_tools_is_one_round():
    client = FakeClient(reply(text="I can help with screening questions."))
    answer = OpenAIAssistant(SOURCE, client=client).ask("Hi")
    assert answer.text == "I can help with screening questions."
    assert answer.rounds == 1 and answer.tool_calls == []
    assert [t["name"] for t in client.sent[0]["tools"]] == ["get_metrics", "run_screen", "compare"]

def test_tool_result_goes_back_with_the_same_call_id():
    client = FakeClient(
        reply([tool_request("get_metrics", {"ticker": "GOOD"}, "call_1")]),
        reply(text="GOOD has a P/E of 20 and a net margin of 20.0%."),
    )
    answer = OpenAIAssistant(SOURCE, client=client).ask("How does GOOD score?")

    second_round = client.sent[1]["input"]
    result = second_round[-1]
    assert result["type"] == "function_call_output" and result["call_id"] == "call_1"
    assert json.loads(result["output"])["metrics"]["pe_ratio"] == 20
    assert second_round[1].type == "function_call"  # the model's own request is kept, before the result
    assert answer.rounds == 2
    assert [c.name for c in answer.tool_calls] == ["get_metrics"]
    assert answer.input_tokens == 200 and answer.output_tokens == 40  # summed over both rounds

def test_two_requests_in_one_round_get_two_results():
    client = FakeClient(
        reply([tool_request("get_metrics", {"ticker": "GOOD"}, "a"),
               tool_request("get_metrics", {"ticker": "NOPE!"}, "b")]),
        reply(text="Done."),
    )
    answer = OpenAIAssistant(SOURCE, client=client).ask("q")
    results = [item for item in client.sent[1]["input"] if isinstance(item, dict) and item.get("type") == "function_call_output"]
    assert [r["call_id"] for r in results] == ["a", "b"]
    assert "error" in answer.tool_calls[1].output  # the bad ticker came back as an error, not a crash

def test_stops_after_max_rounds():
    looping = [reply([tool_request("get_metrics", {"ticker": "GOOD"}, f"c{i}")]) for i in range(3)]
    answer = OpenAIAssistant(SOURCE, client=FakeClient(*looping), max_rounds=3).ask("q")
    assert answer.stopped_early and answer.text == assistant.GAVE_UP
    assert len(answer.tool_calls) == 3

def test_failed_status_raises():
    with pytest.raises(AssistantError):
        OpenAIAssistant(SOURCE, client=FakeClient(reply(status="incomplete"))).ask("q")

def _answer(text: str, calls: list[ToolCall] = (), question: str = "q") -> Answer:
    return Answer(question=question, text=text, tool_calls=list(calls), rounds=1, stopped_early=False,
                  model="gpt-6-luna", prompt_version="v1", input_tokens=1_000_000, output_tokens=0, latency_s=1)

def test_ungrounded_numbers_flags_a_guess():
    guessed = _answer("Apple's P/E is about 31.5.")
    assert assistant.ungrounded_numbers(guessed) == ["31.5"]

def test_ungrounded_numbers_accepts_numbers_from_tools_and_question():
    call = ToolCall(round=1, name="get_metrics", arguments="{}", output={"metrics": {"pe_ratio": 31.5, "net_margin_pct": 24.3}})
    grounded = _answer("P/E 31.5 and net margin 24.3%, below your 40.", [call], question="Is it under 40?")
    assert assistant.ungrounded_numbers(grounded) == []

def test_answer_cost():
    assert assistant.answer_cost(_answer("x")) == pytest.approx(0.1)  # 1M input tokens at $0.10