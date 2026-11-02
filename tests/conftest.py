import pytest


@pytest.fixture(autouse=True)
def ignore_the_real_dotenv(monkeypatch):
    """A developer's own .env (with a real key) must not change what the tests see."""
    from emporio import providers
    monkeypatch.setattr(providers, "load_dotenv", lambda: None)
