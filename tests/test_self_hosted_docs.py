"""The repository ships only the self-hosted app, and its guides link to files that exist."""

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUIDES = [ROOT / "README.md", ROOT / "CLAUDE.md", *sorted((ROOT / "doc").glob("*.md")),
          *sorted((ROOT / "doc/agents").glob("*.md")), *sorted((ROOT / "web").glob("*.md"))]
# Written as a log of the past; it names things that no longer exist.
GUIDES = [g for g in GUIDES if g.name != "operations.md"]
LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")


def test_no_second_application_ships():
    assert not (ROOT / "website").exists()
    assert not (ROOT / "requirements-site.txt").exists()


def test_nothing_imports_or_runs_the_removed_site():
    offenders = []
    for path in [*ROOT.glob("*.py"), *(ROOT / "dinkydash").glob("*.py"),
                 *(ROOT / "web").rglob("*.py"), *(ROOT / "tests").glob("*.py"),
                 *(ROOT / ".github").rglob("*.yml"), ROOT / "Dockerfile", ROOT / "compose.yaml"]:
        if path.name == Path(__file__).name:
            continue
        if re.search(r"\bwebsite[./ ]|requirements-site", path.read_text()):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_guides_link_only_to_files_that_exist():
    broken = []
    for guide in GUIDES:
        for target in LINK.findall(guide.read_text()):
            if re.match(r"[a-z]+:", target):
                continue
            if not (guide.parent / target).resolve().exists():
                broken.append(f"{guide.relative_to(ROOT)} -> {target}")
    assert broken == []


def test_self_hosting_guidance_is_in_the_repository():
    calendars = (ROOT / "doc/calendar-links.md").read_text()
    for provider in ("Google Calendar", "Apple iCloud", "Outlook", "Cozi"):
        assert provider in calendars
    guide = (ROOT / "doc/self-hosting.md").read_text()
    for heading in ("Raspberry Pi", "kiosk", "Troubleshooting", "What leaves your machine"):
        assert heading in guide
    assert "dinkydash.co" not in guide + calendars + (ROOT / "README.md").read_text()


def test_the_icon_script_runs_without_the_site():
    spec = importlib.util.spec_from_file_location("generate_icons", ROOT / "scripts/generate_icons.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.draw_mark(192).size == (192, 192)
    assert (ROOT / "web/static/icon-192.png").exists()


def test_licence_keeps_the_original_copyright_and_permission_notice():
    licence = (ROOT / "LICENSE").read_text()
    assert "Copyright (c) 2021-2026 Caspar Wrede" in licence
    assert "Permission is hereby granted, free of charge" in licence


def test_guidance_states_the_independent_fork_policy():
    for guide in (ROOT / "CLAUDE.md", ROOT / "README.md"):
        text = " ".join(guide.read_text().split())
        assert "GitHub fork" in text, guide.name
        assert "independently" in text, guide.name
        assert "selectively" in text or "take the ones that fit" in text, guide.name
    assert "no obligation to stay in sync" in " ".join((ROOT / "README.md").read_text().split())
    assert "nothing obliges the two to stay in sync" in " ".join((ROOT / "CLAUDE.md").read_text().split())
