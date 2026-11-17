"""What a public page must not say, as data both the tests and the live check read.

`tests/test_site.py` runs these against every page as rendered from the
working tree, and blocks a merge. `website/check_live.py` runs the same ones
against the pages as served from production, once a week. One set of rules, so
the gate before publishing and the check after it cannot disagree.

Standard library only: the live check runs on a bare Python with nothing
installed.
"""

import html
import re

# Draft text that has reached a public page at least once on a sister product.
# Case-sensitive for the shouted markers, so "todo list" is fine.
DRAFT = re.compile(r"\bTBD\b|\bTODO\b|\bFIXME\b|\bXXX\b|\bTKTK\b")
DRAFT_ANY_CASE = re.compile(
    r"lorem ipsum|internal note|note to self|\[insert|\[placeholder|"
    r"citation needed|as an ai language model|\bplaceholder\b",
    re.I)
# Markdown that failed to render: a bare `[text](url)` or `[text]` left in the
# visible text.
UNRENDERED = re.compile(r"\]\(|\[[^\]\n]{1,60}\](?!\()")
# A contraction can't end a clause: "where it's." reads as a typo.
CLAUSE_FINAL_CONTRACTION = re.compile(
    r"\b(?:there|it|that|here|what|where|who)'s[ \t]*[.,;:!?)]", re.I)

# Offers for the retired hosted product must not reappear in public copy.
RETIRED_OFFER = re.compile(r"(?:app\.dinkydash\.co/login|14.day hosted trial|we host it)", re.I)


def visible(html_text):
    """The text a visitor reads: no script, style, code block or tag attribute,
    so an `<input placeholder=...>` or a shell command cannot trip a check."""
    text = re.sub(r"<(script|style|pre|code)\b.*?</\1>", " ", html_text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return html.unescape(text).replace("’", "'")


def draft_markers(text):
    return [m.group(0) for pattern in (DRAFT, DRAFT_ANY_CASE) for m in pattern.finditer(text)]


def unrendered_markdown(text):
    return [m.group(0) for m in UNRENDERED.finditer(text)]


def clause_final_contractions(text):
    return [text[max(0, m.start() - 30):m.end()]
            for m in CLAUSE_FINAL_CONTRACTION.finditer(text)]


def problems(html_text):
    """Every check above, on one served page, as readable lines."""
    text = visible(html_text)
    found = [f"draft marker {m!r}" for m in draft_markers(text)]
    found += [f"unrendered Markdown {m!r}" for m in unrendered_markdown(text)]
    found += [f"contraction ends a clause {m!r}" for m in clause_final_contractions(text)]
    if RETIRED_OFFER.search(html_text):
        found.append("the retired hosted offer")
    return found
