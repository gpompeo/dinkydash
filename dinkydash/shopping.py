"""The shopping list's rules: caps, ticking, and when a bought item goes.

Pure: every function takes the list and a moment and returns a new list (and,
where a person can get it wrong, a plain-English problem). Nothing here reads a
file or a clock; `store.py` keeps the list and the routes supply the time.

The list never reaches the model.
"""

from datetime import datetime, timedelta

from . import config as config_module

MAX_ITEMS = 100
MAX_TEXT = 80
MAX_QUANTITY = 40

# A bought item stays on the list this long, then disappears.
BOUGHT_KEEPS = timedelta(hours=24)


def _stamp(now):
    return now.isoformat(timespec="seconds")


def _checked(text, quantity):
    text, quantity = (text or "").strip(), (quantity or "").strip()
    if not text:
        return None, None, "Say what to add."
    if len(text) > MAX_TEXT:
        return None, None, f"Keep an item to {MAX_TEXT} characters or fewer."
    if len(quantity) > MAX_QUANTITY:
        return None, None, f"Keep a quantity to {MAX_QUANTITY} characters or fewer."
    return text, quantity, None


def add_item(items, text, quantity, added_by, now):
    """The list with one more item, or the list unchanged and why not."""
    text, quantity, problem = _checked(text, quantity)
    if problem:
        return items, problem
    if len(items) >= MAX_ITEMS:
        return items, f"The list is full at {MAX_ITEMS} items. Clear some bought ones or delete something first."
    item = {"id": config_module.new_id(i["id"] for i in items), "text": text,
            "quantity": quantity, "added_by": added_by, "added_at": _stamp(now),
            "bought_at": None}
    return items + [item], None


def edit_item(items, item_id, text, quantity, now):
    text, quantity, problem = _checked(text, quantity)
    if problem:
        return items, problem
    return [dict(i, text=text, quantity=quantity) if i["id"] == item_id else i
            for i in items], None


def set_bought(items, item_id, bought, now):
    return [dict(i, bought_at=_stamp(now) if bought else None) if i["id"] == item_id else i
            for i in items]


def delete_item(items, item_id):
    return [i for i in items if i["id"] != item_id]


def clear_bought(items):
    return [i for i in items if not i.get("bought_at")]


def current(items, now):
    """The list as it stands at `now`: bought items older than a day are gone."""
    def keeps(item):
        bought = item.get("bought_at")
        if not bought:
            return True
        try:
            return now - datetime.fromisoformat(bought) < BOUGHT_KEEPS
        except ValueError:
            return False
    return [i for i in items if keeps(i)]
