"""Health endpoints answer without accessing family data or a database."""

import pytest

from tests.conftest import client_for
from web import create_app
from website.site import create_site_app


class Exploding:
    """A pool that fails on any use: the health check must not touch it."""

    def __getattr__(self, name):
        raise AssertionError(f"the health check touched the pool ({name})")


class TestTheProbe:
    def test_the_site_answers_healthz(self):
        response = create_site_app().test_client().get("/healthz")
        assert response.status_code == 200
        assert response.get_json()["status"] == "ok"

    def test_the_cloud_app_answers_without_a_session_or_database(self, monkeypatch):
        pytest.importorskip("psycopg")
        monkeypatch.setenv("DINKYDASH_MODE", "cloud")
        monkeypatch.setenv("DINKYDASH_SECRET_KEY", "a-real-one")
        client = client_for(create_app(pool=Exploding()))
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.get_json()["status"] == "ok"
