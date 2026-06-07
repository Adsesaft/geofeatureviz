from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from geofeatureviz.data import anki_connector


@patch("geofeatureviz.data.anki_connector.Collection")
def test_open_collection_yield_and_close_with_path(mock_col_cls: MagicMock) -> None:
    mock_col = MagicMock()
    mock_col_cls.return_value = mock_col

    test_path = Path("test") / "path"
    with anki_connector.open_collection(test_path) as col:
        assert col is mock_col
        mock_col_cls.assert_called_once_with(str(test_path))

    mock_col.close.assert_called_once()


@patch("geofeatureviz.data.anki_connector.Collection")
def test_open_collection_yield_and_close_with_str(mock_col_cls: MagicMock) -> None:
    mock_col = MagicMock()
    mock_col_cls.return_value = mock_col

    test_path = "test/path"
    with anki_connector.open_collection(test_path) as col:
        assert col is mock_col
        mock_col_cls.assert_called_once_with(str(test_path))

    mock_col.close.assert_called_once()


@patch("geofeatureviz.data.anki_connector.path_settings")
def test_open_collection_reject_original_path(mock_path_settings: MagicMock) -> None:
    test_path = Path("test") / "path"
    mock_path_settings.anki_collection_path = test_path
    with pytest.raises(ValueError):
        with anki_connector.open_collection(test_path):
            pass


@patch("geofeatureviz.data.anki_connector.Collection")
def test_open_collection_close_on_error(mock_col_cls: MagicMock) -> None:
    mock_col = MagicMock()
    mock_col_cls.return_value = mock_col

    test_path = Path("test") / "path"
    with pytest.raises(RuntimeError):
        with anki_connector.open_collection(test_path):
            raise RuntimeError("explosion")

    mock_col.close.assert_called_once()
