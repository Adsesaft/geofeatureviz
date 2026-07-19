"""Provide tests for topography module."""

from dataclasses import dataclass

import numpy as np
import pytest
from numpy.typing import NDArray

from geofeatureviz import topography


@dataclass(frozen=True)
class Ring:
    coords: NDArray[np.float64]
    area: float

    def __post_init__(self) -> None:
        if not np.allclose(self.coords[0], self.coords[-1]):
            raise ValueError("Ring must be closed.")

    def clockwise(self) -> NDArray[np.float64]:
        return self.coords

    def counter_clockwise(self) -> NDArray[np.float64]:
        return self.coords[::-1]


line = Ring(
    np.array(
        [
            [0.0, 0.0],
            [1.0, 1.0],
            [2.0, 2.0],
            [0.0, 0.0],
        ]
    ),
    0.0,
)
triangle = Ring(
    np.array(
        [
            [0.0, 0.0],
            [0.0, 2.0],
            [2.0, 0.0],
            [0.0, 0.0],
        ]
    ),
    2.0,
)
square = Ring(
    np.array(
        [
            [0.0, 0.0],
            [0.0, 1.0],
            [1.0, 1.0],
            [1.0, 0.0],
            [0.0, 0.0],
        ]
    ),
    1.0,
)

# list of all rings to test (line, triangle, square)
RINGS = [
    pytest.param(line, id="line"),
    pytest.param(triangle, id="triangle"),
    pytest.param(square, id="square"),
]


class TestSignedArea:
    @pytest.mark.parametrize("ring", RINGS)
    def test_clockwise(self, ring: Ring) -> None:
        area = topography._signed_area(ring.clockwise())
        assert area == pytest.approx(-ring.area)

    @pytest.mark.parametrize("ring", RINGS)
    def test_counter_clockwise(self, ring: Ring) -> None:
        area = topography._signed_area(ring.counter_clockwise())
        assert area == pytest.approx(ring.area)

    def test_zero_area(self) -> None:
        assert topography._signed_area(line.clockwise()) == pytest.approx(0.0)

    @pytest.mark.parametrize("ring", RINGS)
    def test_orientation_sign_flip(self, ring: Ring) -> None:
        cw_area = topography._signed_area(ring.clockwise())
        ccw_area = topography._signed_area(ring.counter_clockwise())
        assert cw_area == -ccw_area

    @pytest.mark.parametrize("ring", RINGS)
    def test_signed_area_shifted(self, ring: Ring) -> None:
        coords = ring.clockwise()
        original_area = topography._signed_area(coords)

        shifted = coords + 12.34
        shifted_area = topography._signed_area(shifted)
        assert original_area == shifted_area

    @pytest.mark.parametrize("ring,", RINGS)
    def test_signed_area_scaled(self, ring: Ring) -> None:
        coords = ring.clockwise()
        original_area = topography._signed_area(coords)

        scaling = 2.0
        scaled = coords * scaling
        scaled_area = topography._signed_area(scaled)
        assert scaled_area == pytest.approx(original_area * scaling**2)

    @pytest.mark.parametrize("ring", RINGS)
    def test_signed_area_large_coords(self, ring: Ring) -> None:
        coords = ring.counter_clockwise() * 1e9
        assert topography._signed_area(coords) == pytest.approx(ring.area * 1e9**2)

    @pytest.mark.parametrize("ring", RINGS)
    def test_signed_area_small_coords(self, ring: Ring) -> None:
        coords = ring.counter_clockwise() * 1e-9
        assert topography._signed_area(coords) == pytest.approx(ring.area * 1e-9**2)
