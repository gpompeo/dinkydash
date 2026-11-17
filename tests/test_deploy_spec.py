"""Health endpoints answer without accessing family data or a database."""

from web import create_app
from website.site import create_site_app


class Exploding:
    """A store that fails on any use: the health check must not touch it."""

    def __getattr__(self, name):
        raise AssertionError(f"the health check touched the store ({name})")


class TestTheProbe:
    def test_the_site_answers_healthz(self):
        response = create_site_app().test_client().get("/healthz")
        assert response.status_code == 200
        assert response.get_json()["status"] == "ok"

    def test_the_dashboard_answers_without_a_session_or_storage(self, monkeypatch):
        monkeypatch.setenv("DINKYDASH_MODE", "single")
        monkeypatch.setenv("DINKYDASH_PARENT_PASSWORD", "invented-password")
        monkeypatch.setenv("DINKYDASH_SECRET_KEY", "a-real-one")
        client = create_app(store=Exploding()).test_client()
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.get_json()["status"] == "ok"
