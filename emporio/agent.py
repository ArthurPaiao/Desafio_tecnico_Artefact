"""The agent loop: model call, run requested tools, repeat until the model answers.

Plain function calling, no framework: the
loop is about thirty lines and every decision the agent makes is visible in
the message history.
"""

import json
import os
import re
from pathlib import Path

from emporio.data import load_db
from emporio.prompt import build_system_prompt
from emporio.tools import TOOL_DEFS, ToolBox

DEFAULT_MODEL = "gemini-3.5-flash-lite"
MAX_TOOL_ROUNDS = 6
MAX_TOKENS = 2048   # thinking models spend part of this before they start answering
SESSIONS_DIR = Path(os.environ.get("EMPORIO_SESSIONS_DIR",
                                   Path(__file__).resolve().parent.parent / "sessions"))

API_ERROR_REPLY = ("Desculpe, tive um problema técnico agora e não consegui concluir sua consulta. "
                   "Pode repetir a mensagem em instantes?")
EMPTY_REPLY = "Não consegui formular uma resposta. Pode reescrever a pergunta?"
TOO_MANY_STEPS_REPLY = ("Estou com dificuldade de concluir essa consulta sozinho. Posso encaminhar "
                        "para um atendente da equipe?")


def _block_to_dict(block) -> dict:
    """SDK content block -> plain dict that can be stored and sent back."""
    return block.model_dump(exclude_none=True)


class Agent:
    def __init__(self, client, session_id: str, model: str | None = None,
                 state_dir: Path = SESSIONS_DIR, conn=None, on_tool_call=None):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", session_id):
            raise ValueError("session id: use only letters, digits, '-' and '_' (max 64)")
        self.client = client
        self.model = model or os.environ.get("EMPORIO_MODEL", DEFAULT_MODEL)
        self.session_id = session_id
        self.state_dir = Path(state_dir)
        self.tools = ToolBox(conn or load_db(), session_id, self.state_dir)
        self.on_tool_call = on_tool_call
        self.last_tool_calls: list[dict] = []
        self.last_error: Exception | None = None
        self.messages: list[dict] = self._load()

    # persistence ------------------------------------------------------
    @property
    def _path(self) -> Path:
        return self.state_dir / f"{self.session_id}.json"

    def _load(self) -> list[dict]:
        if self._path.exists():
            saved = json.loads(self._path.read_text(encoding="utf-8"))
            self.tools.failed_verifications = saved.get("failed_verifications", 0)
            return saved["messages"]
        return []

    def _save(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps({"session_id": self.session_id, "messages": self.messages,
                                          "failed_verifications": self.tools.failed_verifications},
                                         ensure_ascii=False, indent=1), encoding="utf-8")

    # conversation -----------------------------------------------------
    def reply(self, user_text: str) -> str:
        """Send one customer message, return the assistant's answer."""
        checkpoint = len(self.messages)
        self.last_tool_calls = []
        self.last_error = None
        self.messages.append({"role": "user", "content": user_text})
        try:
            answer = self._run_turn()
        except Exception as e:  # network, rate limit, auth: keep the history valid
            del self.messages[checkpoint:]
            self.last_error = e
            return API_ERROR_REPLY
        self._save()
        return answer or EMPTY_REPLY

    def _run_turn(self) -> str:
        for _ in range(MAX_TOOL_ROUNDS):
            response = self.client.messages.create(
                model=self.model, max_tokens=MAX_TOKENS, system=build_system_prompt(),
                tools=TOOL_DEFS, messages=self.messages)
            blocks = [_block_to_dict(b) for b in response.content]
            self.messages.append({"role": "assistant", "content": blocks})

            if response.stop_reason != "tool_use":
                return "".join(b["text"] for b in blocks if b["type"] == "text").strip()

            results = []
            for block in blocks:
                if block["type"] != "tool_use":
                    continue
                output = self.tools.call(block["name"], block["input"])
                call = {"name": block["name"], "input": block["input"], "output": output}
                self.last_tool_calls.append(call)
                if self.on_tool_call:
                    self.on_tool_call(call)
                results.append({"type": "tool_result", "tool_use_id": block["id"],
                                "content": json.dumps(output, ensure_ascii=False)})
            self.messages.append({"role": "user", "content": results})
        # The model kept asking for tools: stop and offer a human instead of looping.
        self.messages.append({"role": "assistant", "content": [{"type": "text", "text": TOO_MANY_STEPS_REPLY}]})
        return TOO_MANY_STEPS_REPLY
