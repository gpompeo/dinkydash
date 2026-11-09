"""Completions never reach the model: the prompt is built from config and today's tasks."""

import inspect
from datetime import date

from dinkydash import prompt
from dinkydash.context import tasks_for

CONFIG = {
    "family_name": "The Wilsons",
    "people": [{"id": "mia1", "name": "Mia", "date_of_birth": "2017-03-15"}],
    "tasks": [{"id": "tk1", "title": "Feed the fish", "emoji": "🐟",
               "recurrence": {"kind": "daily"},
               "assignment": {"mode": "fixed", "people": ["mia1"]}}],
}


def test_the_prompt_takes_no_completions():
    assert not any("complet" in name or "streak" in name
                   for name in inspect.signature(prompt.build_user_prompt).parameters)


def test_a_completion_never_appears_in_the_prompt():
    day = date(2026, 6, 1)
    completion = {"task_id": "tk1", "date": "2026-06-01", "person_id": "mia1",
                  "completed_at": "2026-06-01T08:00:00+02:00"}
    text = prompt.build_user_prompt(CONFIG, day, [], [], tasks_for(CONFIG, day), [])
    assert "Feed the fish" in text
    for value in completion.values():
        assert value not in text


def test_no_streak_wording_reaches_the_prompt():
    day = date(2026, 6, 1)
    text = prompt.build_user_prompt(CONFIG, day, [], [], tasks_for(CONFIG, day), [])
    assert "streak" not in text.lower()
    assert "in a row" not in text
