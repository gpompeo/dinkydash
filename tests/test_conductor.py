"""Conductor delegates to the same validated launcher used in a terminal."""

from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def test_one_default_run_starts_the_dashboard():
    settings = tomllib.loads((ROOT / '.conductor/settings.toml').read_text())
    runs = settings['scripts']['run']
    assert runs['dev']['command'] == 'venv/bin/python dev.py'
    assert runs['dev']['default'] is True
    assert 'dashboard' not in runs
