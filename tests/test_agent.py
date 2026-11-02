import json

import pytest

from emporio.agent import API_ERROR_REPLY, MAX_TOOL_ROUNDS, TOO_MANY_STEPS_REPLY, Agent
from emporio.data import load_db
from emporio.prompt import build_system_prompt
from emporio.tools import MAX_FAILED_VERIFICATIONS, TOOL_DEFS, ToolBox
from tests.fakes import FakeClient, text, tool_call


@pytest.fixture(scope="module")
def db():
    return load_db()


@pytest.fixture
def make_agent(db, tmp_path):
    def build(script, session="s1"):
        client = FakeClient(script)
        return Agent(client, session, model="test-model", state_dir=tmp_path, conn=db), client
    return build


def test_plain_answer_without_tools(make_agent):
    agent, client = make_agent([text("Oi! Como posso ajudar?")])
    assert agent.reply("oi") == "Oi! Como posso ajudar?"
    assert [m["role"] for m in agent.messages] == ["user", "assistant"]
    assert client.requests[0]["model"] == "test-model"


def test_tool_round_trip_feeds_real_data_back_to_the_model(make_agent):
    agent, client = make_agent([
        tool_call("get_product", {"name": "Takamine GD20"}),
        text("O Takamine GD20 custa R$ 2.199,00."),
    ])
    assert agent.reply("quanto custa o Takamine GD20?") == "O Takamine GD20 custa R$ 2.199,00."
    second = client.requests[1]["messages"]
    assert [m["role"] for m in second] == ["user", "assistant", "user"]
    result = second[-1]["content"][0]
    assert result["type"] == "tool_result" and result["tool_use_id"] == "toolu_1"
    assert "R$ 2.199,00" in json.loads(result["content"])["list_price_text"]
    assert agent.last_tool_calls[0]["name"] == "get_product"


def test_history_is_saved_and_resumed(make_agent, db, tmp_path):
    agent, _ = make_agent([text("Olá!")], session="maria")
    agent.reply("oi")
    resumed = Agent(FakeClient([text("Claro.")]), "maria", model="m", state_dir=tmp_path, conn=db)
    assert len(resumed.messages) == 2
    resumed.reply("e então?")
    assert len(resumed.messages) == 4


def test_api_failure_keeps_history_valid(make_agent):
    agent, _ = make_agent([RuntimeError("boom"), text("Voltei!")])
    assert agent.reply("oi") == API_ERROR_REPLY
    assert agent.messages == []
    assert agent.reply("oi de novo") == "Voltei!"
    assert [m["role"] for m in agent.messages] == ["user", "assistant"]


def test_failure_after_a_tool_call_rolls_back_the_whole_turn(make_agent):
    agent, _ = make_agent([tool_call("get_store_info", {}), RuntimeError("boom")])
    assert agent.reply("horário?") == API_ERROR_REPLY
    assert agent.messages == []


def test_runaway_tool_loop_stops_and_offers_a_human(make_agent):
    script = [tool_call("get_store_info", {}, call_id=f"t{i}") for i in range(MAX_TOOL_ROUNDS)]
    agent, _ = make_agent(script)
    assert agent.reply("horário?") == TOO_MANY_STEPS_REPLY
    assert agent.messages[-1]["role"] == "assistant"


def test_unknown_tool_and_bad_arguments_do_not_crash(db, tmp_path):
    box = ToolBox(db, "s", tmp_path)
    assert "error" in box.call("drop_tables", {})
    assert "error" in box.call("get_product", {"colour": "red"})
    assert "error" in box.call("get_order_status", {"order_id": "abc", "contact": "x@y.com"})


def test_order_lookup_locks_after_repeated_failures(db, tmp_path):
    box = ToolBox(db, "s", tmp_path)
    for _ in range(MAX_FAILED_VERIFICATIONS):
        assert box.call("get_order_status", {"order_id": 8, "contact": "chute@x.com"})["verified"] is False
    locked = box.call("get_order_status", {"order_id": 8, "contact": "anacarol.ferreira@coldmail.com"})
    assert locked["locked"] is True          # even the right contact is refused now
    assert box.call("check_return_eligibility", {"order_id": 7, "contact": "x", "reason": "defeito"})["locked"]


def test_a_successful_lookup_does_not_reset_the_counter(db, tmp_path):
    # Otherwise a guesser could alternate two failures with a lookup of their own order.
    box = ToolBox(db, "s", tmp_path)
    box.call("get_order_status", {"order_id": 8, "contact": "chute@x.com"})
    assert box.call("get_order_status", {"order_id": 8, "contact": "anacarol.ferreira@coldmail.com"})["verified"]
    assert box.failed_verifications == 1


def test_lock_engages_exactly_at_the_third_failure(db, tmp_path):
    box = ToolBox(db, "s", tmp_path)
    for _ in range(MAX_FAILED_VERIFICATIONS - 1):
        box.call("get_order_status", {"order_id": 8, "contact": "chute@x.com"})
    assert box.call("get_order_status", {"order_id": 8, "contact": "anacarol.ferreira@coldmail.com"})["verified"]
    box.call("get_order_status", {"order_id": 8, "contact": "chute@x.com"})
    assert box.call("get_order_status", {"order_id": 8, "contact": "anacarol.ferreira@coldmail.com"})["locked"]
    # Everything that is not an order lookup keeps working.
    assert "error" not in box.call("get_store_info", {})
    assert box.call("escalate_to_human", {"reason": "other", "summary": "teste"})["ticket"].startswith("ATD-")


def test_lock_survives_a_resumed_session(make_agent):
    agent, _ = make_agent([text("a")], session="lock")
    agent.tools.failed_verifications = MAX_FAILED_VERIFICATIONS
    agent.reply("oi")
    again, _ = make_agent([text("b")], session="lock")
    assert again.tools.failed_verifications == MAX_FAILED_VERIFICATIONS


def test_only_declared_tools_can_be_called(db, tmp_path):
    box = ToolBox(db, "s", tmp_path)
    box.failed_verifications = 3
    for name in ("_init__", "verified", "init", "call", "__class__"):
        assert "error" in box.call(name, {"conn": "x", "session_id": "s", "state_dir": "/tmp"})
    assert box.failed_verifications == 3 and box.conn is db


def test_session_id_cannot_escape_the_sessions_folder(db, tmp_path):
    for bad in ("../x", "/tmp/x", "a/b", "", "x" * 65):
        with pytest.raises(ValueError):
            Agent(FakeClient([]), bad, state_dir=tmp_path, conn=db)


def test_escalation_writes_a_numbered_ticket(db, tmp_path):
    box = ToolBox(db, "sess-9", tmp_path)
    first = box.call("escalate_to_human", {"reason": "complaint", "summary": "Pedido 8 atrasado"})
    second = box.call("escalate_to_human", {"reason": "weird", "summary": "outro caso"})
    assert (first["ticket"], second["ticket"]) == ("ATD-0001", "ATD-0002")
    rows = [json.loads(l) for l in (tmp_path / "handoffs.jsonl").read_text().splitlines()]
    assert rows[0]["session"] == "sess-9" and rows[1]["reason"] == "other"


def test_every_tool_definition_has_a_handler_and_a_valid_schema(db, tmp_path):
    box = ToolBox(db, "s", tmp_path)
    names = [t["name"] for t in TOOL_DEFS]
    assert len(names) == len(set(names)) == 7
    for tool in TOOL_DEFS:
        assert tool["description"] and tool["input_schema"]["type"] == "object"
        assert hasattr(box, f"_{tool['name']}")


def test_system_prompt_carries_the_store_clock(monkeypatch):
    monkeypatch.setenv("EMPORIO_NOW", "2026-03-07T14:00:00")   # Saturday, after closing
    prompt = build_system_prompt()
    assert "sábado, 07/03/2026, 14:00" in prompt
    assert "closed now" in prompt and "segunda-feira, 09/03 às 09:00" in prompt
    monkeypatch.setenv("EMPORIO_NOW", "2026-03-10T10:00:00")
    assert "open now" in build_system_prompt()
