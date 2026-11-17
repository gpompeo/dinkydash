"""Resolve the file store for the current request."""

from flask import current_app


def current_store():
    return current_app.config["STORE"]
