"""Dashboard paths."""

from flask import url_for


def board_path():
    return url_for("board.index")
