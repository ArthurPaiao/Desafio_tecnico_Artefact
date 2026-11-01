"""Runs the agent through the real Anthropic SDK, with the network replaced by a
fake HTTP transport. Checks what a scripted fake cannot: that the SDK's own
response objects serialise back into a valid follow-up request."""

import json

import pytest

anthropic = pytest.importorskip("anthropic")

try:  # newer SDK releases ship their own HTTP client package
    import httpx2 as httpx
except ImportError:
    import httpx

from emporio.agent import Agent
from emporio.data import load_db


def message(content, stop_reason):
    return {"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-sonnet-5-5",
            "content": content, "stop_reason": stop_reason, "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 10}}


def test_agent_works_with_real_sdk_objects(tmp_path):
    bodies = []
    replies = iter([
        message([{"type": "text", "text": "Vou conferir."},
                 {"type": "tool_use", "id": "toolu_abc", "name": "get_product",
                  "input": {"name": "Takamine GD20"}}], "tool_use"),
        message([{"type": "text", "text": "Custa R$ 2.199,00."}], "end_turn"),
    ])

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=next(replies))

    client = anthropic.Anthropic(api_key="test", max_retries=0,
                                 http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    agent = Agent(client, "sdk", state_dir=tmp_path, conn=load_db())
    assert agent.reply("quanto custa o Takamine GD20?") == "Custa R$ 2.199,00."

    first, second = bodies
    assert first["model"] == "claude-sonnet-5-5"
    assert len(first["tools"]) == 7 and "Tom" in first["system"]
    # the assistant's tool_use block came back from the SDK and was sent again intact
    assistant = second["messages"][1]["content"]
    assert [b["type"] for b in assistant] == ["text", "tool_use"]
    assert assistant[1]["id"] == "toolu_abc" and assistant[1]["input"] == {"name": "Takamine GD20"}
    result = second["messages"][2]["content"][0]
    assert result["type"] == "tool_result" and result["tool_use_id"] == "toolu_abc"
    assert "2.199,00" in result["content"]


def test_http_error_becomes_a_friendly_reply(tmp_path):
    def handler(request):
        return httpx.Response(529, json={"type": "error", "error": {"type": "overloaded_error", "message": "busy"}})

    client = anthropic.Anthropic(api_key="test", max_retries=0,
                                 http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    agent = Agent(client, "sdk-err", state_dir=tmp_path, conn=load_db())
    assert "problema técnico" in agent.reply("oi")
    assert agent.messages == [] and isinstance(agent.last_error, anthropic.APIStatusError)
