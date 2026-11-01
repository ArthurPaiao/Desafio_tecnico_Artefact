"""A scripted stand-in for the Anthropic client, so the agent loop is testable offline."""

from types import SimpleNamespace


class Block:
    def __init__(self, **fields):
        self.fields = fields

    def model_dump(self, exclude_none=True):
        return dict(self.fields)


def text(content):
    return SimpleNamespace(content=[Block(type="text", text=content)], stop_reason="end_turn")


def tool_call(name, args, call_id="toolu_1", preface=None):
    blocks = [Block(type="text", text=preface)] if preface else []
    blocks.append(Block(type="tool_use", id=call_id, name=name, input=args))
    return SimpleNamespace(content=blocks, stop_reason="tool_use")


class FakeClient:
    """`script` items are responses, or exceptions to raise."""

    def __init__(self, script):
        self.script = list(script)
        self.requests = []
        self.messages = self

    def create(self, **kwargs):
        # Snapshot: the agent keeps mutating the same list afterwards.
        self.requests.append({**kwargs, "messages": [dict(m) for m in kwargs["messages"]]})
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
