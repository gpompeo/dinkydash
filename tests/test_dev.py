"""Exercise the local dashboard launcher without a database."""

import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

import pytest

import dev


def test_configuration_uses_environment_ports_without_database(monkeypatch, tmp_path):
    monkeypatch.setattr(dev, "ROOT", tmp_path)
    monkeypatch.setenv("CONDUCTOR_PORT", "5300")
    monkeypatch.delenv("DINKYDASH_SECRET_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SENDGRID_API_KEY", "a-copied-key")
    assert dev.configure() == {"Dashboard": 5300}
    assert not os.environ.get("SENDGRID_API_KEY")


def test_invalid_port_is_refused(monkeypatch, tmp_path):
    monkeypatch.setattr(dev, "ROOT", tmp_path)
    monkeypatch.setenv("CONDUCTOR_PORT", "65536")
    with pytest.raises(RuntimeError):
        dev.configure()


def test_launcher_serves_the_dashboard_without_database(tmp_path):
    with socket.socket() as first:
        first.bind(("127.0.0.1", 0))
        port = first.getsockname()[1]
    config = tmp_path / "config.yaml"
    config.write_text("family_name: Test\n")
    root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "DINKYDASH_CONFIG": str(config), "DINKYDASH_PORT": str(port),
           "DINKYDASH_MODE": "single",
           "DINKYDASH_PARENT_PASSWORD": "", "DATABASE_URL": ""}
    log = tmp_path / "dev.log"
    with log.open("w") as output:
        process = subprocess.Popen([sys.executable, "dev.py"], cwd=root, env=env,
                                   stdout=output, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and "Dashboard: http://" not in log.read_text():
            assert process.poll() is None, log.read_text()
            time.sleep(0.05)
        assert "Dashboard: http://" in log.read_text(), log.read_text()
        with urlopen(f"http://127.0.0.1:{port}/") as response:
            assert response.status == 200
    finally:
        process.terminate()
        process.wait(timeout=10)
