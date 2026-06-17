"""Provide tests for data preprocessing helpers."""

from math import inf
from typing import Any, cast

import pytest
from shapely.geometry import MultiPolygon, Point, Polygon

from geofeatureviz.data import preprocessor


def test_polygon_is_all_inf_returns_true_when_all_coordinates_are_infinite() -> None:
    polygon = Polygon([(inf, inf), (inf, inf), (inf, inf), (inf, inf)])

    assert preprocessor.polygon_is_all_inf(polygon)


def test_polygon_is_all_inf_returns_false_for_finite_polygon() -> None:
    polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 0)])

    assert not preprocessor.polygon_is_all_inf(polygon)


def test_polygon_is_all_inf_returns_false_for_unsupported_geometry() -> None:
    unsupported_geometry = cast(Any, Point(0, 0))

    assert not preprocessor.polygon_is_all_inf(unsupported_geometry)


def test_get_polygon_bounds_combines_multipolygon_bounds() -> None:
    multipolygon = MultiPolygon(
        [
            Polygon([(0, 0), (1, 0), (1, 1), (0, 0)]),
            Polygon([(2, -1), (4, -1), (4, 3), (2, -1)]),
        ]
    )

    assert preprocessor.get_polygon_bounds(multipolygon) == (0.0, -1.0, 4.0, 3.0)


def test_get_polygon_bounds_raises_for_unsupported_geometry() -> None:
    with pytest.raises(ValueError, match="Polygon or MultiPolygon"):
        preprocessor.get_polygon_bounds(cast(Any, Point(0, 0)))
