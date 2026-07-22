"""Tests for topography.raster_to_elevation_gdf.

The geometric correctness of the returned geometries is not tested here, since this is
only based on the correctness of topography.raster_to_polygons, which is properly
tested.
"""

from contextlib import contextmanager
from typing import Callable, ContextManager, Generator

import geopandas as gpd
import numpy as np
import pytest
from numpy.typing import NDArray
from rasterio.io import DatasetReader, MemoryFile
from rasterio.transform import from_origin
from shapely import MultiPolygon, Polygon

from geofeatureviz.topography import raster_to_elevation_gdf

RasterFactory = Callable[..., ContextManager[DatasetReader]]


@pytest.fixture
def raster_factory() -> RasterFactory:
    """Return a contextmanager for an in-memory rasterio raster.

    The input to topography.raster_to_elevation_gdf is an opened rasterio.DatasetReader.
    With this function, it is created in memory from a numpy array. Since this opens
    data, it is necessary to close it again. Therefore, this factory returns a
    contextmanager that can be used, e.g., like:

    with raster_factory(...) as raster_src:
        raster = raster_src.read(1)
    """

    @contextmanager
    def _make(
        array: NDArray[np.float64],
        pixel_size: float = 1.0,
        crs: str = "EPSG:25832",
        origin: tuple[float, float] = (0.0, 0.0),
    ) -> Generator[DatasetReader]:
        """Create an in-memory raster with one band from an array.

        Args:
            array: 2D array with elevation values.
            pixel_size: Size of a pixel in CRS units.
            crs: Coordinate reference system of the raster.
            nodata: Value that is used for
            origin: Coordinate (x, y) of the top left corner of the raster.
        """
        data = np.asarray(array, dtype="float64")
        transform = from_origin(origin[0], origin[1], pixel_size, -pixel_size)

        with MemoryFile() as mem_file:
            with mem_file.open(
                driver="GTiff",
                height=data.shape[0],
                width=data.shape[1],
                count=1,
                dtype=data.dtype,
                crs=crs,
                transform=transform,
            ) as dataset:
                dataset.write(data, 1)

            with mem_file.open(mode="r") as reader:
                yield reader

    return _make


PyramidRaster = Callable[[int], NDArray[np.float64]]


@pytest.fixture
def pyramid_raster() -> PyramidRaster:
    """Returns a factory for a raster that describes the elevation of a pyramid."""

    def _create(n_pixels: int) -> NDArray[np.float64]:
        if n_pixels % 2 == 0:
            raise ValueError(f"The number of pixels has to be odd, not {n_pixels}.")

        arr = np.zeros((n_pixels, n_pixels), dtype=int)

        for i in range((n_pixels + 1) // 2):
            arr[i : n_pixels - i, i : n_pixels - i] = i
        return arr

    return _create


@pytest.fixture
def mini_sample_raster() -> NDArray[np.float64]:
    return np.array([[1.0, 2.0], [3.0, 4.0]])


class TestBasicGDFStructure:
    def test_returns_gdf_with_expected_columns(
        self, raster_factory: RasterFactory, mini_sample_raster: NDArray[np.float64]
    ) -> None:
        with raster_factory(mini_sample_raster) as raster:
            result = raster_to_elevation_gdf(raster, thresholds=[1.5])
        assert isinstance(result, gpd.GeoDataFrame)
        assert set(result.columns) == {"elevation", "geometry"}

    def test_crs_matches_raster_crs(
        self, raster_factory: RasterFactory, mini_sample_raster: NDArray[np.float64]
    ) -> None:
        crs = "EPSG:25832"
        with raster_factory(mini_sample_raster) as raster:
            result = raster_to_elevation_gdf(raster, thresholds=[1.5])
        assert result.crs == raster.crs == crs

    def test_one_row_per_threshold(
        self, raster_factory: RasterFactory, mini_sample_raster: NDArray[np.float64]
    ) -> None:
        thresholds = [0.5, 1.5, 2.5]
        with raster_factory(mini_sample_raster) as raster:
            result = raster_to_elevation_gdf(raster, thresholds=thresholds)
        assert len(result) == len(thresholds)
        assert set(result["elevation"]) == set(thresholds)

    def test_empty_thresholds_returns_empty_gdf(
        self, raster_factory: RasterFactory, mini_sample_raster: NDArray[np.float64]
    ) -> None:
        with raster_factory(mini_sample_raster) as raster:
            result = raster_to_elevation_gdf(raster, thresholds=[])
        assert len(result) == 0
        assert set(result.columns) == {"elevation", "geometry"}


class TestGeometries:
    def test_all_geometries_polygons(
        self, raster_factory: RasterFactory, pyramid_raster: PyramidRaster
    ) -> None:
        thresholds = [0.5, 1.5, 2.5, 3.5]
        with raster_factory(pyramid_raster(9)) as raster:
            result = raster_to_elevation_gdf(raster, thresholds=thresholds)
        assert len(result) == 4
        for geometry in result["geometry"]:
            assert isinstance(geometry, Polygon)

    def test_all_geometries_multipolygons(
        self, raster_factory: RasterFactory, pyramid_raster: PyramidRaster
    ) -> None:
        two_pyramids = np.vstack((pyramid_raster(9), pyramid_raster(9)))
        thresholds = [1.5, 2.5, 3.5]
        with raster_factory(two_pyramids) as raster:
            result = raster_to_elevation_gdf(raster, thresholds=thresholds)
        assert len(result) == 3
        for geometry in result["geometry"]:
            assert isinstance(geometry, MultiPolygon)

    def test_area_decreases_with_elevation_level(
        self, raster_factory: RasterFactory, pyramid_raster: PyramidRaster
    ) -> None:
        thresholds = [0.5, 1.5, 2.5, 3.5]
        with raster_factory(pyramid_raster(9)) as raster:
            result = raster_to_elevation_gdf(raster, thresholds=thresholds)

        result = result.sort_values(by="elevation")
        result["area"] = result.geometry.area
        assert result["area"].is_monotonic_decreasing

    def test_threshold_higher_than_all_elevations_results_in_empty_polygon(
        self, raster_factory: RasterFactory
    ) -> None:
        with raster_factory(np.zeros((2, 2))) as raster:
            result = raster_to_elevation_gdf(raster, thresholds=[100])
        assert len(result) == 1
        geom = result.geometry.iloc[0]
        assert isinstance(geom, Polygon)
        assert geom.is_empty

    def test_transformation_is_applied(
        self, raster_factory: RasterFactory, mini_sample_raster: NDArray[np.float64]
    ) -> None:
        with raster_factory(
            mini_sample_raster, origin=(0, 0), pixel_size=1.0
        ) as raster:
            result1 = raster_to_elevation_gdf(raster, thresholds=[0])
        with raster_factory(
            mini_sample_raster, origin=(0, 0), pixel_size=2.0
        ) as raster:
            result2 = raster_to_elevation_gdf(raster, thresholds=[0])
        assert not result1.equals(result2)

        geom1 = result1.geometry.iloc[0]
        geom2 = result2.geometry.iloc[0]
        assert isinstance(geom1, Polygon)
        assert isinstance(geom2, Polygon)

        coords1 = np.array(list(geom1.exterior.coords))
        coords2 = np.array(list(geom2.exterior.coords))
        np.testing.assert_equal(2 * coords1, coords2)
