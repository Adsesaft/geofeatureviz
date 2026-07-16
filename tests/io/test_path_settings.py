"""Provide tests for io.path_settings.py."""

from geofeatureviz.io import _path_settings


def test_get_project_root() -> None:
    top_dir = _path_settings._get_project_root()
    assert (top_dir / ".gitignore").exists()
    assert top_dir.name == "geofeatureviz"
