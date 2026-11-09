"""Completions: add, remove, trim at 400 days, atomic writes, gone with the person."""

import json
import os
from datetime import date

import pytest

from dinkydash.store import FileStore

TODAY = date(2026, 6, 1)


@pytest.fixture
def store(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text('family_name: "The Wilsons"\n')
    return FileStore(path)


def entry(task="t1", day="2026-05-31", person="p1"):
    return {"task_id": task, "date": day, "person_id": person,
            "completed_at": "2026-06-01T08:00:00+02:00"}


def test_a_completion_is_recorded_and_read_back(store):
    store.record_completion(entry(), TODAY)
    assert store.load_completions() == [entry()]


def test_recording_twice_keeps_one(store):
    store.record_completion(entry(), TODAY)
    store.record_completion(entry(), TODAY)
    assert len(store.load_completions()) == 1


def test_a_completion_can_be_removed(store):
    store.record_completion(entry(), TODAY)
    store.record_completion(entry(person="p2"), TODAY)
    store.remove_completion(entry(), TODAY)
    assert [c["person_id"] for c in store.load_completions()] == ["p2"]


def test_since_filters_by_date(store):
    store.record_completion(entry(day="2026-05-01"), TODAY)
    store.record_completion(entry(day="2026-05-31"), TODAY)
    assert [c["date"] for c in store.load_completions(since=date(2026, 5, 30))] == ["2026-05-31"]


def test_entries_older_than_400_days_are_trimmed_on_write(store):
    store.record_completion(entry(day="2025-04-27"), date(2025, 4, 27))
    store.record_completion(entry(day="2025-05-01"), date(2025, 5, 1))
    # 2026-06-01 minus 400 days is 2025-04-27: that day is kept, the day before is not.
    store.record_completion(entry(task="t2"), date(2026, 6, 1))
    assert "2025-04-27" in [c["date"] for c in store.load_completions()]
    store.record_completion(entry(task="t3"), date(2026, 6, 2))
    days = [c["date"] for c in store.load_completions()]
    assert "2025-04-27" not in days and "2025-05-01" in days


def test_deleting_a_person_deletes_their_completions(store):
    store.record_completion(entry(person="p1"), TODAY)
    store.record_completion(entry(person="p2"), TODAY)
    store.drop_person_completions("p1")
    assert [c["person_id"] for c in store.load_completions()] == ["p2"]


def test_the_file_is_replaced_atomically(store, monkeypatch):
    store.record_completion(entry(), TODAY)
    path = store.base / "completions.json"
    before = path.read_text()

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        store.record_completion(entry(task="t2"), TODAY)
    assert path.read_text() == before
    assert [p.name for p in store.base.glob("*.tmp")] == []


def test_a_damaged_file_reads_as_empty(store):
    (store.base / "completions.json").write_text("{not json")
    assert store.load_completions() == []


def test_the_file_is_gitignored():
    ignored = open(os.path.join(os.path.dirname(__file__), "..", ".gitignore")).read().split()
    assert {"completions.json", "shopping.json"} <= set(ignored)
