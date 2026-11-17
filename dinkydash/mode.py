"""Validate the self-hosted deployment mode."""


def validate(value):
    selected = (value or "single").strip().lower() or "single"
    if selected == "cloud":
        raise ValueError("DINKYDASH_MODE=cloud: cloud mode has been removed.")
    if selected != "single":
        raise ValueError("DINKYDASH_MODE must be 'single'.")
    return selected
