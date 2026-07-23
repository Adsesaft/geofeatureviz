"""Tests for topography.raster_to_polygons."""

from itertools import combinations
from typing import Callable, ContextManager
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from contourpy.types import CLOSEPOLY, LINETO, MOVETO
from numpy.typing import NDArray
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

from geofeatureviz.topography import raster_to_polygon

# generous relative tolerance for areas of shapes
AREA_REL_TOL = 0.2


def _make_raster(
    shape: tuple[int, int], fill_value: float = 0.0
) -> NDArray[np.float64]:
    """Create a raster of the given shape, filled with a constant value."""
    return np.full(shape, fill_value, dtype=np.float64)


def _elevate(
    raster: NDArray[np.float64],
    rows: tuple[int, int],
    cols: tuple[int, int],
    value: float,
) -> NDArray[np.float64]:
    """Set a rectangular sub-region of the raster to a given value (in place)."""
    raster[slice(*rows), slice(*cols)] = value
    return raster


# These default values are changeable, but be careful when changing the fixtures itself,
# since e.g. the area of the polygons is tested, which depends on the slices inside the
# fixtures.
N_PIXELS = 21
FILL_VAL = 0.0
PEAK_VAL = 1.0
THRESHOLD = (PEAK_VAL - FILL_VAL) / 2


@pytest.fixture
def raster_one_peak() -> NDArray[np.float64]:
    raster = _make_raster((N_PIXELS, N_PIXELS), fill_value=FILL_VAL)
    _elevate(raster, (6, 15), (6, 15), value=PEAK_VAL)
    return raster


@pytest.fixture
def raster_two_peaks() -> NDArray[np.float64]:
    raster = _make_raster((N_PIXELS, N_PIXELS), fill_value=FILL_VAL)
    _elevate(raster, (3, 6), (3, 6), value=PEAK_VAL)
    _elevate(raster, (15, 18), (15, 18), value=PEAK_VAL)
    return raster


@pytest.fixture
def raster_three_peaks() -> NDArray[np.float64]:
    raster = _make_raster((N_PIXELS, N_PIXELS), fill_value=FILL_VAL)
    _elevate(raster, (3, 6), (3, 6), value=PEAK_VAL)
    _elevate(raster, (3, 6), (15, 18), value=PEAK_VAL)
    _elevate(raster, (15, 18), (15, 18), value=PEAK_VAL)
    return raster


@pytest.fixture
def raster_peak_with_hole() -> NDArray[np.float64]:
    raster = _make_raster((N_PIXELS, N_PIXELS), fill_value=FILL_VAL)
    _elevate(raster, (3, 18), (3, 18), value=PEAK_VAL)
    _elevate(raster, (9, 12), (9, 12), value=FILL_VAL)
    return raster


class TestNoDataAboveThreshold:
    """Cases where no pixel in the raster is larger than the threshold.

    Expected to produce an empty polygon.
    """

    def test_all_zero_returns_empty_polygon(self) -> None:
        raster = _make_raster((10, 10), fill_value=0.0)
        result = raster_to_polygon(raster, threshold=1.0)
        assert isinstance(result, Polygon)
        assert result.is_empty

    def test_random_below_threshold_returns_empty_polygon(self) -> None:
        raster = np.random.default_rng(seed=0).uniform(0.0, 5.0, size=(10, 10))
        threshold = float(raster.max()) + 0.1
        result = raster_to_polygon(raster, threshold=threshold)
        assert isinstance(result, Polygon)
        assert result.is_empty


class TestAllDataAboveThreshold:
    """Cases where every pixel in a raster is larger than the threshold.

    Expected to produce a rectangle covering the whole raster.
    """

    @pytest.mark.parametrize("n_pixel", [2, 5, 21])
    def test_polygon_coords(self, n_pixel: int) -> None:
        raster = _make_raster((n_pixel, n_pixel), fill_value=1.0)

        result = raster_to_polygon(raster, threshold=0.0)
        assert isinstance(result, Polygon)
        assert result.is_valid
        assert len(result.interiors) == 0

        whole_area = Polygon(
            [
                [0, 0],
                [n_pixel - 1, 0],
                [n_pixel - 1, n_pixel - 1],
                [0, n_pixel - 1],
                [0, 0],
            ]
        )
        assert result.equals(whole_area)

    @pytest.mark.parametrize("n_pixel", [2, 5, 21])
    def test_bounds_in_pixel_space(self, n_pixel: int) -> None:
        raster = _make_raster((n_pixel, n_pixel), fill_value=3.14)

        result = raster_to_polygon(raster, threshold=0.1)
        assert result is not None

        assert result.bounds == pytest.approx((0.0, 0.0, n_pixel - 1, n_pixel - 1))

    @pytest.mark.parametrize("n_pixel", [2, 5, 21])
    def test_area_in_pixel_space(self, n_pixel: int) -> None:
        raster = _make_raster((n_pixel, n_pixel), fill_value=31.41)

        result = raster_to_polygon(raster, threshold=10.1)
        assert result is not None
        assert result.area == pytest.approx((n_pixel - 1) * (n_pixel - 1))

    def test_input_raster_not_mutated(self) -> None:
        raster = _make_raster((5, 5), fill_value=1.0)

        raster_copy = raster.copy()
        _ = raster_to_polygon(raster, threshold=0.0)

        np.testing.assert_array_equal(raster, raster_copy)


class TestSingleConnectedRegion:
    """Cases with a single elevated blob inside the raster.

    Expected to produce exactly one Polygon with no holes.
    """

    def test_single_blob_returns_single_polygon(
        self, raster_one_peak: NDArray[np.float64]
    ) -> None:
        result = raster_to_polygon(raster_one_peak, threshold=THRESHOLD)
        assert isinstance(result, Polygon)
        assert result.is_valid
        assert len(result.interiors) == 0

    def test_polygon_roughly_positioned_and_sized(
        self, raster_one_peak: NDArray[np.float64]
    ) -> None:
        result = raster_to_polygon(raster_one_peak, threshold=THRESHOLD)
        assert isinstance(result, Polygon)

        expected_area = (15 - 6) ** 2
        assert result.area == pytest.approx(expected_area, rel=AREA_REL_TOL)

        # centroid should be at raster center
        centroid = (result.centroid.x, result.centroid.y)
        raster_center = 2 * ((raster_one_peak.shape[0] - 1) / 2,)
        assert centroid == pytest.approx(raster_center)

        # bounds should be approximately at pixels
        min_x, min_y, max_x, max_y = result.bounds
        assert 5 <= min_x and max_x <= 15
        assert 5 <= min_y and max_y <= 15

    def test_single_blob_with_different_values(
        self, raster_one_peak: NDArray[np.float64]
    ) -> None:
        value_shifts = np.array([-123.45, -1.23, 1.23, 123.45])
        thresholds = value_shifts + THRESHOLD

        mask = raster_one_peak == PEAK_VAL
        rng = np.random.default_rng(seed=1)

        rasters = []
        for shift in value_shifts:
            raster = raster_one_peak.copy()
            # replace ones with random values larger than one
            raster[mask] = rng.uniform(1, 12.3, size=mask.sum())
            raster += shift
            rasters.append(raster)

        polygons = [
            raster_to_polygon(r, threshold=t) for r, t in zip(rasters, thresholds)
        ]
        for p in polygons:
            assert isinstance(p, Polygon)
        # assert that polygons are not equal (because the different values should
        # change how polygons are drawn), but very similar
        max_diff = polygons[0].area * AREA_REL_TOL
        for p1, p2 in combinations(polygons, 2):
            assert 0 < p1.symmetric_difference(p2).area < max_diff
        # assert all(not polygons[0].equals(p) for p in polygons[1:])

    def test_boundary_equal_to_threshold(
        self, raster_one_peak: NDArray[np.float64]
    ) -> None:
        # when equal to threshold, no polygon should be drawn
        result_equal = raster_to_polygon(raster_one_peak, threshold=PEAK_VAL)
        assert result_equal.is_empty

        # when slightly smaller, the polygon should be found
        result = raster_to_polygon(raster_one_peak, threshold=PEAK_VAL - 1e-10)
        assert isinstance(result, Polygon)


class TestMultipleDisjointRegions:
    """Cases with separate elevated areas.

    Expected to produce a MultiPolygon whose parts do not touch or overlap.
    """

    def test_two_disjoint_blobs_return_two_parts(
        self, raster_two_peaks: NDArray[np.float64]
    ) -> None:
        result = raster_to_polygon(raster_two_peaks, threshold=THRESHOLD)

        assert isinstance(result, MultiPolygon)
        assert len(result.geoms) == 2
        for part in result.geoms:
            assert part.is_valid
            assert len(part.interiors) == 0

    def test_two_disjoint_blobs_do_not_overlap(
        self, raster_two_peaks: NDArray[np.float64]
    ) -> None:
        result = raster_to_polygon(raster_two_peaks, threshold=THRESHOLD)

        assert isinstance(result, MultiPolygon)
        part_a, part_b = result.geoms
        assert not part_a.intersects(part_b)

    def test_three_disjoint_blobs_return_three_parts(
        self, raster_three_peaks: NDArray[np.float64]
    ) -> None:
        result = raster_to_polygon(raster_three_peaks, threshold=THRESHOLD)

        assert isinstance(result, MultiPolygon)
        assert len(result.geoms) == 3
        for part in result.geoms:
            assert part.is_valid
            assert len(part.interiors) == 0

    def test_parts_area(self, raster_two_peaks: NDArray[np.float64]) -> None:
        result = raster_to_polygon(raster_two_peaks, threshold=THRESHOLD)
        assert isinstance(result, MultiPolygon)

        expected_area_per_blob = (5 - 2) ** 2
        for part in result.geoms:
            assert part.area == pytest.approx(expected_area_per_blob, rel=AREA_REL_TOL)


class TestHoles:
    """Cases where an elevated region has a below-threshold interior.

    Expected to produce a Polygon with an interior ring.
    """

    def test_produce_polygon_with_hole(
        self, raster_peak_with_hole: NDArray[np.float64]
    ) -> None:
        result = raster_to_polygon(raster_peak_with_hole, threshold=THRESHOLD)

        assert isinstance(result, Polygon)
        assert result.is_valid
        assert len(result.interiors) == 1

    def test_hole_is_smaller(self, raster_peak_with_hole: NDArray[np.float64]) -> None:
        result = raster_to_polygon(raster_peak_with_hole, threshold=THRESHOLD)
        assert isinstance(result, Polygon)

        outer = Polygon(result.exterior)
        hole = Polygon(result.interiors[0])
        assert 0 < hole.area < outer.area
        assert result.area == pytest.approx(outer.area - hole.area, rel=1e-6)

    def test_hole_position(self, raster_peak_with_hole: NDArray[np.float64]) -> None:
        result = raster_to_polygon(raster_peak_with_hole, threshold=THRESHOLD)
        assert isinstance(result, Polygon)

        hole = Polygon(result.interiors[0])

        # hole should be centered where we depressed the raster.
        hole_centroid = hole.centroid
        assert hole_centroid.x == pytest.approx(10)
        assert hole_centroid.y == pytest.approx(10)

    def test_inverse_values_produce_inverse_polygons(
        self, raster_one_peak: NDArray[np.float64]
    ) -> None:
        result = raster_to_polygon(raster_one_peak, threshold=THRESHOLD)
        assert isinstance(result, Polygon)
        assert result.is_valid
        assert len(result.interiors) == 0

        inv_result = raster_to_polygon(-raster_one_peak, threshold=-THRESHOLD)
        assert isinstance(inv_result, Polygon)
        assert inv_result.is_valid
        assert len(inv_result.interiors) == 1

        # create polygon from interior of second one
        inv_interior = Polygon(inv_result.interiors[0])
        assert inv_interior.equals(result)

        # test if the inverse and the standard polygon unified cover the whole area
        whole_area = Polygon(
            [
                [0, 0],
                [N_PIXELS - 1, 0],
                [N_PIXELS - 1, N_PIXELS - 1],
                [0, N_PIXELS - 1],
                [0, 0],
            ]
        )
        assert unary_union([result, inv_result]).equals(whole_area)


Points = NDArray[np.float64]
Codes = NDArray[np.int_]


@pytest.fixture
def bow_tie_contour() -> tuple[Points, Codes]:
    points = np.array(
        [[0, 0], [2, 2], [4, 0], [4, 4], [2, 2], [0, 4], [0, 0]],
        dtype=float,
    )
    codes = np.array([MOVETO, LINETO, LINETO, LINETO, LINETO, LINETO, CLOSEPOLY])
    return points, codes


MockFilledContoursFactory = Callable[[Points, Codes], ContextManager[MagicMock]]


@pytest.fixture
def mock_filled_contours_factory() -> MockFilledContoursFactory:
    """Mock contourpy.contour_generator's return value with points and codes.

    This returns a contextmanager factory, so that it can be used like:
    with mock_filled_contours(points, codes):
        result = raster_to_polygons(...)
    """

    def _create(points: Points, codes: Codes) -> ContextManager[MagicMock]:
        mock_contour_generator = MagicMock()
        mock_contour_generator.filled.return_value = ([points], [codes])

        module_name = "geofeatureviz.topography.contourpy.contour_generator"
        return patch(module_name, return_value=mock_contour_generator)

    return _create


class TestEdgeCasesAndAmbiguities:
    """Edge cases and ambiguous cases."""

    def test_single_isolated_pixel_above_threshold(self) -> None:
        raster = _make_raster((N_PIXELS, N_PIXELS), fill_value=FILL_VAL)
        raster[N_PIXELS // 2, N_PIXELS // 2] = PEAK_VAL

        result = raster_to_polygon(raster, threshold=THRESHOLD)

        assert isinstance(result, Polygon)
        assert result.is_valid
        assert result.area < 1  # tiny area

    def test_rectangular_non_square_raster(self) -> None:
        raster = _make_raster((10, 20), fill_value=FILL_VAL)
        _elevate(raster, (2, 8), (2, 15), value=PEAK_VAL)

        result = raster_to_polygon(raster, threshold=THRESHOLD)
        assert isinstance(result, Polygon)
        assert result.is_valid

    def test_diagonally_touching_blobs_stay_separate(self) -> None:
        """Two blobs sharing only a single pixel-corner (not an edge) must stay
        as two distinct polygons in the resulting MultiPolygon.
        """
        n = 6
        raster = _make_raster((n, n), fill_value=FILL_VAL)
        _elevate(raster, (1, 3), (1, 3), value=PEAK_VAL)
        _elevate(raster, (3, 5), (3, 5), value=PEAK_VAL)  # touches at corner (2, 2)

        result = raster_to_polygon(raster, threshold=THRESHOLD)

        assert isinstance(result, MultiPolygon)
        assert len(result.geoms) == 2
        part_a, part_b = result.geoms
        # no shared area, but touching at the pinch point is expected.
        assert part_a.intersection(part_b).area == pytest.approx(0.0, abs=1e-9)

    def test_single_pixel_bridge_between_blobs_produces_single_polygon(self) -> None:
        """A single-pixel-wide bridge connecting two otherwise separate blobs should
        result in a single valid Polygon.
        """
        raster = _make_raster((5, 9), fill_value=FILL_VAL)
        _elevate(raster, (1, 4), (1, 4), value=PEAK_VAL)
        _elevate(raster, (1, 4), (5, 8), value=PEAK_VAL)
        raster[2, 4] = PEAK_VAL  # single-pixel bridge

        result = raster_to_polygon(raster, threshold=THRESHOLD)

        assert isinstance(result, Polygon)
        assert result.is_valid
        assert len(result.interiors) == 0

    def test_invalid_polygon_is_repaired(
        self,
        mock_filled_contours_factory: MockFilledContoursFactory,
        bow_tie_contour: tuple[Points, Codes],
    ) -> None:
        """Test if an invalid polygon is repaired when contourpy returns one.

        Actually, contourpy is written so that this case should not happen; but this
        tests if raster_to_polygon still worked if it happens anyway, so this just tests
        an "insurance" part of the code.
        """
        raster = np.zeros((2, 2))  # content irrelevant, generator is mocked
        with mock_filled_contours_factory(*bow_tie_contour):
            result = raster_to_polygon(raster, threshold=THRESHOLD)

        assert isinstance(result, MultiPolygon)
        assert result.is_valid
        assert not result.is_empty
        assert len(result.geoms) == 2, "Result should be two touching triangles."
        assert result.area == pytest.approx(8.0, rel=AREA_REL_TOL)


def zero_rings() -> tuple[Points, Codes]:
    points = np.array([[0.0, 0.0], [0.0, 0.0], [0.0, 0.0]])
    codes = np.array([MOVETO, LINETO, CLOSEPOLY])
    return points, codes


def two_rings() -> tuple[Points, Codes]:
    ring_a = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 0.0]])
    ring_b = np.array([[5.0, 5.0], [6.0, 5.0], [6.0, 6.0], [5.0, 5.0]])
    points = np.concatenate([ring_a, ring_b])
    codes = np.array(
        [MOVETO, LINETO, LINETO, CLOSEPOLY, MOVETO, LINETO, LINETO, CLOSEPOLY]
    )
    return points, codes


class TestValueError:
    """Cases that could trigger the ValueError.

    In the implementation, I assume that there is always a single outer ring of a
    single polygon detected. The ValueError is only raised when this assumption was
    wrong (which I can't completely confirm). This is a test that the error is raised
    when the assumption is broken and mocks contourpy's function return value.
    """

    @pytest.mark.parametrize(
        "points, codes",
        [zero_rings(), two_rings()],
        ids=["zero_outer_rings", "two_outer_rings"],
    )
    def test_raises_value_error(
        self,
        points: Points,
        codes: Codes,
        mock_filled_contours_factory: MockFilledContoursFactory,
    ) -> None:
        raster = np.zeros((2, 2))  # content irrelevant, generator is mocked
        with mock_filled_contours_factory(points, codes):
            with pytest.raises(ValueError, match="Expected a single outer ring"):
                raster_to_polygon(raster, threshold=THRESHOLD)
