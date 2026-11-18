"""Startup rejects removed deployment modes before serving any requests."""

import pytest

from web import create_app


def test_cloud_mode_is_rejected(monkeypatch):
    monkeypatch.setenv("DINKYDASH_MODE", "cloud")
    monkeypatch.delenv("DINKYDASH_SECRET_KEY", raising=False)
    with pytest.raises(ValueError, match="cloud mode has been removed"):
        create_app()


def test_feedback_rate_limit_applies_on_a_local_network(monkeypatch, tmp_path):
    from dinkydash import mail
    from dinkydash.store import FileStore
    from tests.conftest import client_for
    from web.routes.settings import MOST_FEEDBACK

    monkeypatch.setenv("SENDGRID_API_KEY", "invented-key")
    monkeypatch.setenv("DINKYDASH_MAIL_FROM", "dash@example.com")
    monkeypatch.setenv("DINKYDASH_MAIL_REPLY_TO", "help@example.com")
    monkeypatch.setenv("DINKYDASH_FEEDBACK_TO", "inbox@example.com")
    sent = []
    monkeypatch.setattr(mail, "send", lambda *args, **kwargs: sent.append(args))
    client = client_for(create_app(FileStore(tmp_path / "config.yaml")))
    for _ in range(MOST_FEEDBACK + 1):
        response = client.post("/settings/feedback", data={"message": "Hello"})
    assert len(sent) == MOST_FEEDBACK
    assert "more than this form takes" in response.get_data(as_text=True)


def test_cloud_mode_is_rejected_by_the_scheduler(monkeypatch, tmp_path, capsys):
    import generate

    monkeypatch.setenv("DINKYDASH_MODE", "cloud")
    result = generate.main(["--config", str(tmp_path / "config.yaml"), "--tick"])
    assert result != 0
    assert "cloud mode has been removed" in capsys.readouterr().err
