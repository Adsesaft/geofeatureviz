"""Tests for topography.get_thresholds."""

from typing import cast

import numpy as np
import pytest
from numpy.typing import NDArray

from geofeatureviz.topography import get_thresholds


@pytest.fixture
def sample_raster() -> NDArray[np.float64]:
    return np.array([[-13.0, 12.0], [41.0, 42.0]])


@pytest.fixture(params=[3, 5, 12, 123])
def n_thresholds(request: pytest.FixtureRequest) -> int:
    return cast(int, request.param)


class TestBasicProperties:
    def test_returns_n_thresholds_values(
        self, sample_raster: NDArray[np.float64], n_thresholds: int
    ) -> None:
        result = get_thresholds(sample_raster, n_thresholds)
        assert len(result) == n_thresholds

    def test_result_is_increasing_with_same_step_size(
        self, sample_raster: NDArray[np.float64], n_thresholds: int
    ) -> None:
        result = get_thresholds(sample_raster, n_thresholds)
        diffs = np.diff(result)
        assert np.all(diffs > 0)
        assert np.allclose(diffs, diffs[0]), "The step size is not equal."

    def test_zero_is_included(
        self, sample_raster: NDArray[np.float64], n_thresholds: int
    ) -> None:
        result = get_thresholds(sample_raster, n_thresholds)
        assert np.any(result == 0.0)

    def test_range_is_roughly_correct(
        self, sample_raster: NDArray[np.float64], n_thresholds: int
    ) -> None:
        result = get_thresholds(sample_raster, n_thresholds)
        assert result.min() == pytest.approx(sample_raster.min(), rel=1)
        assert result.max() == pytest.approx(sample_raster.max(), rel=1)

    def test_nice_values(self) -> None:
        raster = np.array([-1.111, 9.888])

        result = get_thresholds(raster, n_thresholds=11)
        np.testing.assert_equal(result, np.arange(-1, 10))

        result = get_thresholds(raster, n_thresholds=22)
        np.testing.assert_equal(result, np.arange(-1, 10, 0.5))


class TestEdgeCases:
    @pytest.mark.parametrize("n_thresholds", [-123, -12, 0, 1, 2])
    def test_n_thresholds_too_small_raises_value_error(
        self, sample_raster: NDArray[np.float64], n_thresholds: int
    ) -> None:
        with pytest.raises(ValueError):
            get_thresholds(sample_raster, n_thresholds)

    def test_zero_raster_raises_value_error(self, n_thresholds: int) -> None:
        raster = np.zeros((2, 2))
        with pytest.raises(ValueError):
            get_thresholds(raster, n_thresholds)

    def test_only_positive_values(self, n_thresholds: int) -> None:
        raster = np.array([100, 152])
        result = get_thresholds(raster, n_thresholds)
        assert len(result) == n_thresholds
        assert result[0] == pytest.approx(100, rel=0.5)
        assert result[-1] == pytest.approx(152, rel=0.5)
        step_size = result[1] - result[0]
        n_until_zero = result[-1] / step_size
        assert np.isclose(n_until_zero, np.round(n_until_zero))

    def test_only_negative_values(self, n_thresholds: int) -> None:
        raster = np.array([-152, -100])
        result = get_thresholds(raster, n_thresholds)
        assert len(result) == n_thresholds
        assert result[0] == pytest.approx(-152, rel=0.5)
        assert result[-1] == pytest.approx(-100, rel=0.5)
        step_size = result[1] - result[0]
        n_until_zero = result[-1] / step_size
        assert np.isclose(n_until_zero, np.round(n_until_zero))
