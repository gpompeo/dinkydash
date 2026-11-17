"""The dashboard's pages, and how one screen is set up to show them.

Pure: the registry, a setup read from a link's query, and the choice of page.
Nothing here reads a clock or a file.

A screen's setup lives in its own link and in that screen's browser, never in
`config.yaml`, so two screens showing one household cannot change each other
and there are no device accounts to manage. A page is added by appending a
`Page` to `REGISTRY`; the navigation, rotation and availability rules follow
without further change, and a page with nothing registered does not exist.
"""

from dataclasses import dataclass
from typing import Callable, Optional

from dinkydash.config import feature_on

MAIN = "main"

DEFAULT_INTERVAL = 30
# Faster than five seconds is not readable; slower than an hour is no rotation.
MIN_INTERVAL = 5
MAX_INTERVAL = 3600


@dataclass(frozen=True)
class Page:
    """One dashboard page.

    `feature` ties it to a feature switch and `when` to any other condition on
    the config; either one failing makes the page unavailable. `template` is
    the partial that draws it, rendered inside the page's own section.
    """

    key: str
    label: str
    feature: Optional[str] = None
    when: Optional[Callable[[dict], bool]] = None
    template: Optional[str] = None


REGISTRY = (Page(MAIN, "Dashboard"),)


def available(config, registry=None):
    """The pages this household can show, in order. The main dashboard is always one."""
    registry = REGISTRY if registry is None else registry
    shown = []
    for page in registry:
        if page.key != MAIN:
            if page.feature and not feature_on(config, page.feature):
                continue
            if page.when and not page.when(config):
                continue
        shown.append(page)
    return shown


@dataclass(frozen=True)
class Setup:
    """What one screen was set up to do."""

    touch: bool = False
    page: str = MAIN
    rotate: bool = False
    interval: int = DEFAULT_INTERVAL


def _interval(text):
    text = (text or "").strip()
    if not (text.isascii() and text.isdigit()) or len(text) > 6:
        return None
    value = int(text)
    return value if MIN_INTERVAL <= value <= MAX_INTERVAL else None


def parse_setup(args):
    """A setup from a link's query, and the problems found.

    A value that is wrong never breaks the screen: it falls back to its default
    and is reported, so the setup page can say so and the dashboard still shows.
    """
    problems = {}
    mode = (args.get("mode") or "").strip()
    if mode and mode not in ("touch", "static"):
        problems["mode"] = "Choose touch or no touch."
    raw_interval = args.get("every")
    interval = DEFAULT_INTERVAL
    if raw_interval is not None and raw_interval.strip() != "":
        parsed = _interval(raw_interval)
        if parsed is None:
            problems["every"] = (f"Use a whole number of seconds from {MIN_INTERVAL} "
                                 f"to {MAX_INTERVAL}.")
        else:
            interval = parsed
    return Setup(
        touch=mode == "touch",
        page=(args.get("page") or MAIN).strip() or MAIN,
        rotate=(args.get("rotate") or "").strip() == "1",
        interval=interval,
    ), problems


def initial_key(wanted, shown):
    """The page to open on: the one asked for if it is available, else the main one."""
    keys = [page.key for page in shown]
    if wanted in keys:
        return wanted
    if MAIN in keys or not keys:
        return MAIN
    return keys[0]


def link_query(setup):
    """The query that makes a screen behave as `setup`; defaults are left out."""
    query = {}
    if setup.touch:
        query["mode"] = "touch"
    if setup.page != MAIN:
        query["page"] = setup.page
    if setup.rotate:
        query["rotate"] = "1"
        if setup.interval != DEFAULT_INTERVAL:
            query["every"] = str(setup.interval)
    return query
