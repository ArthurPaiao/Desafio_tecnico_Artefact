"""Model providers.

The agent loop keeps the conversation as text, tool_use and tool_result
blocks. Gemini's free tier, Groq, OpenRouter and a local Ollama all expose the
OpenAI chat-completions format, so OpenAICompatClient translates between the two.

It uses only the standard library: one POST endpoint does not justify a
dependency, and the transport can be replaced in tests.
"""

import json
import os
import re
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field

from emporio.env import load_dotenv

RETRY_STATUSES = {429, 500, 502, 503, 504, 529}


class ProviderError(RuntimeError):
    pass


@dataclass
class Block:
    """Mimics the SDK's content blocks: the agent only calls model_dump()."""
    fields: dict = field(default_factory=dict)

    def model_dump(self, exclude_none: bool = True) -> dict:
        return dict(self.fields)


@dataclass
class Response:
    content: list
    stop_reason: str


def to_openai_messages(system: str, messages: list[dict]) -> list[dict]:
    out = [{"role": "system", "content": system}]
    for message in messages:
        content = message["content"]
        if isinstance(content, str):
            out.append({"role": message["role"], "content": content})
        elif message["role"] == "assistant":
            texts = [b["text"] for b in content if b["type"] == "text"]
            calls = []
            for b in content:
                if b["type"] == "tool_use":
                    call = {"id": b["id"], "type": "function",
                            "function": {"name": b["name"],
                                         "arguments": json.dumps(b["input"], ensure_ascii=False)}}
                    if "extra_content" in b:       # e.g. Gemini 3 thought signatures: echo back untouched
                        call["extra_content"] = b["extra_content"]
                    calls.append(call)
            entry = {"role": "assistant", "content": "".join(texts) or None}
            if calls:
                entry["tool_calls"] = calls
            out.append(entry)
        else:  # a user turn made of tool results
            for b in content:
                if b["type"] == "tool_result":
                    out.append({"role": "tool", "tool_call_id": b["tool_use_id"], "content": b["content"]})
    return out


def to_openai_tools(tools: list[dict]) -> list[dict]:
    return [{"type": "function",
             "function": {"name": t["name"], "description": t["description"],
                          "parameters": t["input_schema"]}} for t in tools]


def from_openai_response(data: dict) -> Response:
    try:
        choice = data["choices"][0]
        message = choice["message"]
    except (KeyError, IndexError, TypeError):
        raise ProviderError(f"Resposta inesperada do provedor: {json.dumps(data)[:300]}")
    blocks = []
    if message.get("content"):
        blocks.append(Block({"type": "text", "text": message["content"]}))
    calls = message.get("tool_calls") or []
    for call in calls:
        raw = call["function"].get("arguments") or "{}"
        try:
            args = json.loads(raw)
        except json.JSONDecodeError:
            args = {"_unparsed_arguments": raw}   # the tool will reject it and the model can retry
        fields = {"type": "tool_use", "id": call.get("id") or f"call_{uuid.uuid4().hex[:12]}",
                  "name": call["function"]["name"], "input": args}
        if call.get("extra_content"):
            fields["extra_content"] = call["extra_content"]
        blocks.append(Block(fields))
    if calls:
        stop = "tool_use"
    else:
        stop = "max_tokens" if choice.get("finish_reason") == "length" else "end_turn"
    return Response(blocks, stop)


def _urllib_post(url: str, headers: dict, body: bytes, timeout: float = 90):
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode("utf-8", "replace")
    except urllib.error.URLError as e:
        raise ProviderError(f"Não consegui falar com o provedor: {e.reason}")


class OpenAICompatClient:
    """Exposes `.messages.create(...)` over the chat-completions endpoint."""

    def __init__(self, base_url: str, api_key: str, post=None, retries: int = 3, sleep=time.sleep,
                 auth_header: str = "Authorization"):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.api_key = api_key
        self.auth_header = auth_header
        self.post = post or _urllib_post
        self.retries = retries
        self.sleep = sleep
        self.messages = self

    def create(self, *, model, max_tokens, system, tools, messages, **_ignored) -> Response:
        body = json.dumps({
            "model": model, "max_tokens": max_tokens,
            "messages": to_openai_messages(system, messages),
            "tools": to_openai_tools(tools), "tool_choice": "auto",
        }, ensure_ascii=False).encode("utf-8")
        # Gemini's OpenAI-compatible endpoint answers "Missing or invalid Authorization header" to
        # x-goog-api-key, so every provider here uses Bearer. The x-goog-api-key option exists
        # only for Google's native endpoint, which this client does not call.
        credential = self.api_key if self.auth_header.lower() == "x-goog-api-key" else f"Bearer {self.api_key}"
        headers = {"Content-Type": "application/json", self.auth_header: credential,
                   "User-Agent": "emporio-agent/0.1"}
        for attempt in range(self.retries + 1):
            status, response_headers, text = self.post(self.url, headers, body)
            if status == 200:
                return from_openai_response(json.loads(text))
            if status in RETRY_STATUSES and attempt < self.retries:
                # Free tiers rate-limit hard (429): wait as told, or back off.
                wait = response_headers.get("Retry-After") or response_headers.get("retry-after")
                self.sleep(min(float(wait), 30) if wait and wait.replace(".", "").isdigit() else 2 ** attempt)
                continue
            raise ProviderError(f"HTTP {status} do provedor: {text[:300].replace(self.api_key, '***')}")
        raise ProviderError("Provedor indisponível após várias tentativas.")


PROVIDERS = {
    "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
               "key_envs": ("GEMINI_API_KEY", "GOOGLE_API_KEY"), "model": "gemini-3.5-flash-lite"},
    "openai-compatible": {"key_envs": ("EMPORIO_API_KEY",), "model": None},  # base URL from EMPORIO_BASE_URL
}
DEFAULT_PROVIDER = "gemini"


def make_client(provider: str | None = None):
    """Return (client, default_model) for a provider name (or EMPORIO_PROVIDER)."""
    load_dotenv()
    provider = provider or os.environ.get("EMPORIO_PROVIDER", DEFAULT_PROVIDER)
    if provider not in PROVIDERS:
        raise ProviderError(f"Provedor desconhecido: {provider}. Opções: {', '.join(PROVIDERS)}.")
    spec = PROVIDERS[provider]
    key = next((os.environ[k].strip() for k in spec["key_envs"] if os.environ.get(k, "").strip()), None)
    if not key:
        raise ProviderError(f"Defina {' ou '.join(spec['key_envs'])} (veja o README).")
    base_url = spec.get("base_url") or os.environ.get("EMPORIO_BASE_URL")
    if not base_url:
        raise ProviderError("Defina EMPORIO_BASE_URL (ex.: https://api.groq.com/openai/v1).")
    if not base_url.startswith("https://") and not re.match(r"http://(localhost|127\.0\.0\.1)([:/]|$)", base_url):
        raise ProviderError("EMPORIO_BASE_URL deve usar https:// (http só para localhost).")
    return OpenAICompatClient(base_url, key, auth_header=spec.get("auth_header", "Authorization")), spec["model"]
