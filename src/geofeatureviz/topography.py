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
    # translate coordinates to be around 0
    ring = ring - ring[0]
    x, y = ring[:, 0], ring[:, 1]
    return 0.5 * float(np.sum(x[:-1] * y[1:] - x[1:] * y[:-1]))


def raster_to_polygon(
    raster: NDArray[np.float64], threshold: float
) -> Polygon | MultiPolygon:
    """Convert elevations in a raster that exceed a threshold into a (Multi)Polygon.

    The (Multi)Polygon covers all areas with elevation > threshold, using marching
    squares (contourpy) so edges are smooth / sub-pixel rather than following raster
    cell boundaries. Note that there is no kind of transformation to any space of the
    resulting polygon, i.e. the result is in the pixel-space of the given raster.

    Args:
        raster: An array of shape (N, M) where each pixel describes an elevation.
        threshold: The resulting (Multi)Polygon covers all areas where the elevation is
            larger than this threshold.

    Raises:
        ValueError: When not a single outer ring was found. If this error is thrown, it
            is possible that this implementation is incorrect, since I assume that there
            is always a single outer ring found when using contourpy's filled function.

    Returns:
        A shapely Polygon or a MultiPolygon if the areas are not connected. When no
        value is above the threshold, an empty Polygon is returned.
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
        return Polygon()
    result = unary_union(polygons)
    # removes redundant points, e.g. on several points defining a straight line
    result = result.simplify(0, preserve_topology=True)
    assert isinstance(result, (Polygon, MultiPolygon))
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

    def _make_polygon(threshold: float) -> Polygon | MultiPolygon:
        """Create a transformed Multi(Polygon) from elevations and a threshold."""
        polygon = raster_to_polygon(elevations, threshold)
        return shapely_transform(_pixel_to_space_transform, polygon)

    geometries = [_make_polygon(t) for t in thresholds]
    return gpd.GeoDataFrame(
        {"elevation": thresholds, "geometry": geometries},
        geometry="geometry",
        crs=raster_src.crs,
    )


def get_thresholds(
    raster: NDArray[np.float64], n_thresholds: int
) -> NDArray[np.float64]:
    """Get thresholds for an elevation map.

    The thresholds are determined by the the minimum and maximum value of the raster
    and the number of thresholds. The thresholds are "rounded" to nice values and are
    shifted to be zero aligned (i.e., a continuation would always include 0).

    Args:
        raster: The raster for which the elevation steps should be computed. The only
            relevant values in the raster are its maximum and minimum; i.e, you can also
            pass a raster of just two values if you do not have the whole raster but
            just the max and min value.
        n_thresholds: The number of thresholds of elevation steps. This has to be at
            least three.

    Raises:
        ValueError: When the number of thresholds is smaller than three.
        ValueError: When the step size would be 0, which happens when the minimum and
            maximum value are equal (or extremely close).

    Returns:
        An array containing thresholds as elevation steps, with an equal step size
        between the thresholds and zero-aligned.
    """
    if n_thresholds < 3:
        raise ValueError(
            f"The number of thresholds has to be at least 3, not {n_thresholds}."
        )
    min_elev = np.min(raster)
    max_elev = np.max(raster)

    step_size = (max_elev - min_elev) / n_thresholds
    if step_size <= 0:
        raise ValueError(
            f"The step size has to be larger than 0. The probable error is that the "
            f"difference between the raster's min ({min_elev}) and the raster's max "
            f"({max_elev}) is zero."
        )

    exponent = int(np.floor(np.log10(step_size)))
    mantissa = step_size / (10.0**exponent)

    mantissa_rounded = np.ceil(mantissa * 2) / 2  # rounds up to nearest 0.5
    step_size = mantissa_rounded * (10**exponent)

    # align with zero
    offset = min_elev % step_size
    if offset > step_size / 2:
        offset -= step_size
    start = min_elev - offset

    thresholds: NDArray[np.float64] = start + step_size * np.arange(n_thresholds)
    return thresholds
