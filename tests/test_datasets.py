"""Provide tests for the dataset registry."""

from pathlib import Path

import pytest

from geofeatureviz.data import datasets


def test_get_dataset_filename_returns_registered_file_name() -> None:
    key = datasets.DatasetKey("country", "ne", 110)

    file_name = datasets.get_dataset_filename(key)

    assert file_name == Path("ne_110m_admin_0_countries.zip")


def test_get_dataset_filename_raises_for_unknown_key() -> None:
    key = datasets.DatasetKey("lake", "unknown", 50)

    with pytest.raises(ValueError, match="No data file found"):
        datasets.get_dataset_filename(key)
