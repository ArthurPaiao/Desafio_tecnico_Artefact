import os

from emporio import env, providers


def test_parse_handles_quotes_spaces_comments_and_bom():
    text = '﻿# c\nGEMINI_API_KEY = "abc123 " \nexport EMPORIO_MODEL=m1\nbad line\n'
    assert env.parse(text) == {"GEMINI_API_KEY": "abc123", "EMPORIO_MODEL": "m1"}


def test_dotenv_fills_missing_but_never_overrides(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("GEMINI_API_KEY=from-file\nEMPORIO_MODEL=file-model\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("EMPORIO_MODEL", "shell-model")
    env.load_dotenv()
    assert os.environ["GEMINI_API_KEY"] == "from-file"
    assert os.environ["EMPORIO_MODEL"] == "shell-model"


def test_make_client_strips_key_with_trailing_space(monkeypatch):
    for k in ("GOOGLE_API_KEY", "EMPORIO_PROVIDER"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(providers, "load_dotenv", lambda: None)
    monkeypatch.setenv("GEMINI_API_KEY", "AQ.abc ")
    client, _ = providers.make_client("gemini")
    assert client.api_key == "AQ.abc"
