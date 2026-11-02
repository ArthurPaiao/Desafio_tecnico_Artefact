import json

import pytest

from emporio.agent import Agent
from emporio.data import load_db
from emporio.providers import (OpenAICompatClient, ProviderError, from_openai_response, make_client,
                               to_openai_messages, to_openai_tools)
from emporio.tools import TOOL_DEFS


def chat(message, finish="stop"):
    return {"choices": [{"message": message, "finish_reason": finish}]}


def tool_call_message(name, args, call_id="call_1", **extra):
    return {"role": "assistant", "content": None,
            "tool_calls": [{"id": call_id, "type": "function",
                            "function": {"name": name, "arguments": json.dumps(args)}, **extra}]}


class FakePost:
    """Replaces the HTTP call: returns queued (status, headers, body) tuples."""
    def __init__(self, *responses):
        self.queue = list(responses)
        self.requests = []

    def __call__(self, url, headers, body):
        self.requests.append({"url": url, "headers": headers, "body": json.loads(body)})
        status, headers_, payload = self.queue.pop(0)
        return status, headers_, payload if isinstance(payload, str) else json.dumps(payload)


def ok(payload):
    return 200, {}, payload


def test_tools_are_translated_to_openai_function_format():
    tools = to_openai_tools(TOOL_DEFS)
    assert len(tools) == 7
    first = tools[0]
    assert first["type"] == "function" and first["function"]["name"] == "search_products"
    assert first["function"]["parameters"]["type"] == "object"


def test_history_is_translated_including_tool_calls_and_results():
    history = [
        {"role": "user", "content": "quanto custa o GD20?"},
        {"role": "assistant", "content": [
            {"type": "text", "text": "Vou conferir."},
            {"type": "tool_use", "id": "c1", "name": "get_product", "input": {"name": "GD20"},
             "extra_content": {"google": {"thought_signature": "sig"}}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "c1", "content": "{\"ok\": 1}"}]},
    ]
    out = to_openai_messages("SYS", history)
    assert [m["role"] for m in out] == ["system", "user", "assistant", "tool"]
    assistant = out[2]
    assert assistant["content"] == "Vou conferir."
    call = assistant["tool_calls"][0]
    assert call["id"] == "c1" and json.loads(call["function"]["arguments"]) == {"name": "GD20"}
    assert call["extra_content"] == {"google": {"thought_signature": "sig"}}   # echoed back untouched
    assert out[3] == {"role": "tool", "tool_call_id": "c1", "content": "{\"ok\": 1}"}


def test_assistant_turn_with_only_tool_calls_has_null_content():
    out = to_openai_messages("S", [{"role": "assistant", "content": [
        {"type": "tool_use", "id": "c", "name": "get_store_info", "input": {}}]}])
    assert out[1]["content"] is None


def test_response_with_text_becomes_end_turn():
    r = from_openai_response(chat({"role": "assistant", "content": "Oi!"}))
    assert r.stop_reason == "end_turn" and r.content[0].model_dump() == {"type": "text", "text": "Oi!"}


def test_response_with_tool_call_becomes_tool_use_and_keeps_extra_content():
    r = from_openai_response(chat(tool_call_message("get_product", {"name": "x"},
                                                    extra_content={"google": {"thought_signature": "s"}}), "tool_calls"))
    block = r.content[0].model_dump()
    assert r.stop_reason == "tool_use"
    assert block["type"] == "tool_use" and block["input"] == {"name": "x"}
    assert block["extra_content"]["google"]["thought_signature"] == "s"


def test_missing_tool_call_id_gets_a_generated_one():
    r = from_openai_response(chat(tool_call_message("get_store_info", {}, call_id="")))
    assert r.content[0].model_dump()["id"].startswith("call_")


def test_unparseable_arguments_do_not_crash():
    message = {"role": "assistant", "content": None, "tool_calls": [
        {"id": "c", "type": "function", "function": {"name": "get_product", "arguments": "{oops"}}]}
    block = from_openai_response(chat(message)).content[0].model_dump()
    assert block["input"] == {"_unparsed_arguments": "{oops"}


def test_length_finish_reason_maps_to_max_tokens():
    assert from_openai_response(chat({"content": "cortad"}, "length")).stop_reason == "max_tokens"


def test_malformed_response_raises_provider_error():
    with pytest.raises(ProviderError):
        from_openai_response({"error": "nope"})


def test_request_goes_to_chat_completions_with_bearer_key():
    post = FakePost(ok(chat({"content": "ok"})))
    client = OpenAICompatClient("https://example.test/v1beta/openai/", "KEY", post=post)
    client.messages.create(model="m", max_tokens=100, system="S", tools=TOOL_DEFS,
                           messages=[{"role": "user", "content": "oi"}])
    req = post.requests[0]
    assert req["url"] == "https://example.test/v1beta/openai/chat/completions"
    assert req["headers"]["Authorization"] == "Bearer KEY"
    assert req["body"]["model"] == "m" and req["body"]["tool_choice"] == "auto"


def test_gemini_key_goes_in_x_goog_api_key_and_not_as_bearer():
    post = FakePost(ok(chat({"content": "ok"})))
    client = OpenAICompatClient("https://x", "AQ.secret", post=post, auth_header="x-goog-api-key")
    client.messages.create(model="m", max_tokens=10, system="S", tools=[], messages=[])
    headers = post.requests[0]["headers"]
    assert headers["x-goog-api-key"] == "AQ.secret" and "Authorization" not in headers


def test_rate_limit_is_retried_using_retry_after():
    sleeps = []
    post = FakePost((429, {"Retry-After": "3"}, "slow down"), ok(chat({"content": "ok"})))
    client = OpenAICompatClient("https://x", "K", post=post, sleep=sleeps.append)
    client.messages.create(model="m", max_tokens=10, system="S", tools=[], messages=[])
    assert sleeps == [3.0] and len(post.requests) == 2


def test_persistent_failure_raises_after_retries():
    post = FakePost(*[(503, {}, "down")] * 4)
    client = OpenAICompatClient("https://x", "K", post=post, retries=3, sleep=lambda s: None)
    with pytest.raises(ProviderError, match="503"):
        client.messages.create(model="m", max_tokens=10, system="S", tools=[], messages=[])
    assert len(post.requests) == 4


def test_auth_error_is_not_retried_and_shows_the_cause():
    post = FakePost((401, {}, '{"error": {"message": "API key not valid"}}'))
    client = OpenAICompatClient("https://x", "bad", post=post, sleep=lambda s: None)
    with pytest.raises(ProviderError, match="401.*API key not valid"):
        client.messages.create(model="m", max_tokens=10, system="S", tools=[], messages=[])
    assert len(post.requests) == 1


def test_full_conversation_through_the_adapter(tmp_path):
    post = FakePost(
        ok(chat(tool_call_message("get_product", {"name": "Takamine GD20"}), "tool_calls")),
        ok(chat({"role": "assistant", "content": "O GD20 custa R$ 2.199,00."})),
    )
    client = OpenAICompatClient("https://x", "K", post=post)
    agent = Agent(client, "gem", model="gemini-test", state_dir=tmp_path, conn=load_db())
    assert agent.reply("quanto custa o Takamine GD20?") == "O GD20 custa R$ 2.199,00."
    second = post.requests[1]["body"]["messages"]
    assert [m["role"] for m in second] == ["system", "user", "assistant", "tool"]
    assert "2.199,00" in second[3]["content"]       # the real tool output reached the model
    assert agent.last_tool_calls[0]["name"] == "get_product"


def test_provider_failure_gives_a_friendly_reply_and_keeps_the_cause(tmp_path):
    post = FakePost((401, {}, "bad key"))
    agent = Agent(OpenAICompatClient("https://x", "K", post=post), "e", state_dir=tmp_path, conn=load_db())
    assert "problema técnico" in agent.reply("oi")
    assert "401" in str(agent.last_error) and agent.messages == []


def test_make_client_reads_the_right_environment(monkeypatch):
    for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "EMPORIO_API_KEY",
                "EMPORIO_BASE_URL", "EMPORIO_PROVIDER"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(ProviderError, match="GEMINI_API_KEY"):
        make_client()                                   # gemini is the default provider
    monkeypatch.setenv("GOOGLE_API_KEY", "g")
    client, model = make_client()
    assert isinstance(client, OpenAICompatClient) and "generativelanguage" in client.url
    assert client.auth_header == "Authorization"     # the compat endpoint rejects x-goog-api-key
    assert model == "gemini-3.5-flash-lite"
    with pytest.raises(ProviderError, match="EMPORIO_BASE_URL"):
        monkeypatch.setenv("EMPORIO_API_KEY", "k") or make_client("openai-compatible")
    monkeypatch.setenv("EMPORIO_BASE_URL", "https://api.groq.com/openai/v1")
    assert make_client("openai-compatible")[0].url == "https://api.groq.com/openai/v1/chat/completions"
    with pytest.raises(ProviderError, match="desconhecido"):
        make_client("nope")
