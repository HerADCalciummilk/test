"""Resolve standard resources while accepting the legacy server layout."""

from pathlib import Path


def resolve_resources(root):
    root = Path(root).resolve()
    for candidate in (root, root / "resource"):
        if (candidate / "config").is_dir() and (candidate / "terrain").is_dir():
            return candidate, "config", candidate / "terrain"
        if (candidate / "Parameter").is_dir() and (candidate / "lib/terrain").is_dir():
            return candidate, "Parameter", candidate / "lib/terrain"
    raise FileNotFoundError(f"No resource/config and resource/terrain layout found under {root}")
