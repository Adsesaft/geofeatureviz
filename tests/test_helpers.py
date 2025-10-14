"""Provide tests for helpers.py."""

from geo_data import helpers


def test_get_top_directory():
    top_dir = helpers.get_top_directory()
    assert (top_dir / ".gitignore").exists()
    assert top_dir.name == "geo_data"
