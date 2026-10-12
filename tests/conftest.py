"""Testy nikdy nesmí sáhnout na skutečné Smoobu, Telegram ani Claude: smyšlené klíče a zákaz sítě."""
import pytest
import requests

from agent import config


@pytest.fixture(autouse=True)
def bez_skutecnych_sluzeb(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "SMOOBU_API_KEY", "usr_live_abc123")
    monkeypatch.setattr(config, "SMOOBU_API_SECRET", "your_api_secret")
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "")
    monkeypatch.setattr(config, "UKLIDY_HESLO", "")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "agent.db")
    monkeypatch.setattr(config, "LOG_PATH", tmp_path / "agent.log")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")

    def zadna_sit(*args, **kwargs):
        raise AssertionError("Test se pokusil o skutečný síťový požadavek")
    monkeypatch.setattr(requests.Session, "request", zadna_sit)
    monkeypatch.setattr(requests, "post", zadna_sit)
    monkeypatch.setattr(requests, "get", zadna_sit)
