"""Provide functions to create topographic maps."""

from typing import Iterable, Optional, cast

import contourpy
import geopandas as gpd
import numpy as np
import rasterio
from numpy.typing import NDArray
from shapely import MultiPolygon, Polygon
from shapely.ops import transform as shapely_transform
from shapely.ops import unary_union

# contourpy magic number codes describing the function of contour coordinates
_MOVETO = 1  # when the coordinate is the start of a polygon ring
_CLOSEPOLY = 79  # when the coordinate closes the polygon ring


def _signed_area(ring: NDArray[np.float64]) -> float:
    """Get the signed area of a closed ring via the shoelace formula.

    The sign of the ring's area encodes whether the winding direction is:
    - positive: counter-clockwise
    - negative: clockwise
    in standard x-right / y-up orientation.

    This function can be used to determine whether a ring created by contourpy is an
    outer boundary (positive area) or a hole (negative area).

    Args:
        ring: An array of coordinates of shape (N, 2) with a closed ring (first = last).

    Returns:
        The area of the polygon enclosed by the ring, with the sign of the area
        indicating the winding direction.
    """
    x, y = ring[:, 0], ring[:, 1]
    return 0.5 * float(np.sum(x[:-1] * y[1:] - x[1:] * y[:-1]))


def raster_to_polygons(
    raster: NDArray[np.float64], threshold: float
) -> Polygon | MultiPolygon | None:
    """Convert elevations in a raster that exceed a threshold into a (Multi)Polygon.

    The (Multi)Polygon covers all areas with elevation >= threshold, using marching
    squares (contourpy) so edges are smooth / sub-pixel rather than following raster
    cell boundaries. Note that there is no kind of transformation to any space of the
    resulting polygon, i.e. the result is in the pixel-space of the given raster.

    Args:
        raster: An array of shape (N, N) where each pixel describes an elevation.
        threshold: The resulting (Multi)Polygon covers all areas where the elevation is
            larger than this threshold.

    Raises:
        ValueError: When not a single outer ring was found. If this error is thrown, it
            is possible that this implementation is incorrect, since I assume that there
            is always a single outer ring found when using contourpy's filled function.

    Returns:
        A shapely Polygon or a MultiPolygon if the areas are not connected. None if
        nothing is above the threshold.
    """
    cg = contourpy.contour_generator(z=raster, fill_type=contourpy.FillType.OuterCode)
    cg_fill_result = cg.filled(threshold, np.inf)
    points_list, codes_list = cg_fill_result[0], cg_fill_result[1]

    polygons = []
    for points, codes in zip(points_list, codes_list):
        if points is None:
            continue

        outers, holes = [], []
        start = None
        assert codes is not None
        for i, c in enumerate(codes):
            # the codes tells if coordinates are starters or closers
            if c == _MOVETO:
                start = i
            elif c == _CLOSEPOLY:
                ring = points[start : i + 1]
                # if the sign of the area is positive, it is the outer bound
                if _signed_area(ring) > 0:
                    outers.append(ring)
                # else it is a hole
                else:
                    holes.append(ring)
        if len(outers) != 1:
            raise ValueError(
                f"Expected a single outer ring, but actually {len(outers)} where found "
                f"for threshold {threshold}."
            )
        # check that polygon is valid and not empty
        polygon = Polygon(outers[0], holes=holes)
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
        if not polygon.is_empty:
            polygons.append(polygon)

    if not polygons:
        return None
    result = cast(Polygon | MultiPolygon, unary_union(polygons))
    return result


def raster_to_elevation_gdf(
    raster_src: rasterio.DatasetReader, thresholds: Iterable[float]
) -> gpd.GeoDataFrame:
    """Create a GeoDataFrame from a raster with a geometry for each elevation.

    For each threshold elevation step, a (Multi)Polygon is created of all the area that
    exceeds this elevation.

    Args:
        raster_src: A rasterio dataset reader, e.g. from rasterio.open(<file>).
        thresholds: The thresholds, with the elevation values for which (Multi)Polygons
            are created.

    Returns:
        A dataframe with a column "elevation" with the elevation steps and a column
        "geometry" with the associated (Multi)Polygons.
    """

    def _pixel_to_space_transform(
        x: float, y: float, z: Optional[float] = None
    ) -> tuple[float, float]:
        """Transform coordinates from pixel space to the geo space."""
        return cast(tuple[float, float], raster_src.transform * (x + 0.5, y + 0.5))

    # make sure that missing pixels are nan
    elevations = raster_src.read(1).astype("float64")
    if raster_src.nodata is not None:
        elevations = np.where(elevations == raster_src.nodata, np.nan, elevations)

    # create a (Multi)Polygon for each threshold
    polygon_dicts = []
    for threshold in thresholds:
        polygon = raster_to_polygons(elevations, threshold)
        if polygon is not None:
            polygon = shapely_transform(_pixel_to_space_transform, polygon)
        polygon_dicts.append({"elevation": threshold, "geometry": polygon})
    return gpd.GeoDataFrame(polygon_dicts, crs=raster_src.crs)


def get_thresholds(
    raster: NDArray[np.float64], n_thresholds: int
) -> NDArray[np.float64]:
    """Get thresholds for an elevation map.

    The thresholds are determined by the number of thresholds and the minimum and
    maximum value of the raster. The step size is "rounded" depending on the overall
    data range. Zero is always part of the thresholds.

    Args:
        raster: The raster for which the elevation steps should be computed.
        n_thresholds: The number of thresholds of elevation steps.

    Returns:
        An array containing the elevation steps.
    """
    min_elev = raster.min() if raster.min() <= 0 else 0
    max_elev = raster.max()

    step_size = (max_elev - min_elev) / n_thresholds

    exponent = np.floor(np.log10(step_size))
    mantissa = step_size / (10**exponent)

    CANDIDATES = np.arange(0, 10.5, 0.5)
    # choose best candidate by relative error in log space
    best = min([c for c in CANDIDATES if c >= mantissa])
    step_size = best * (10**exponent)

    start = (min_elev // step_size) * step_size
    end = start + (n_thresholds - 1) * step_size
    return np.linspace(start, end, n_thresholds)
