"""Provide tests for helpers.py."""

from geofeatureviz import helpers


def test_get_top_directory() -> None:
    top_dir = helpers.get_top_directory()
    assert (top_dir / ".gitignore").exists()
    assert top_dir.name == "geofeatureviz"
