"""Load a `.env` file into the environment (standard library only).

Looks for `.env` in the current directory and in the project root. Variables
already set in the real environment win, so a shell `set` still overrides the file.
Values are stripped: a trailing space pasted along with an API key is the most
common reason for a "invalid API key" error.
"""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def parse(text: str) -> dict:
    values = {}
    for line in text.lstrip("﻿").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if name:
            values[name] = value.strip()
    return values


def load_dotenv() -> None:
    for folder in (Path.cwd(), ROOT):
        path = folder / ".env"
        if path.is_file():
            for name, value in parse(path.read_text(encoding="utf-8")).items():
                if value and not os.environ.get(name, "").strip():
                    os.environ[name] = value
