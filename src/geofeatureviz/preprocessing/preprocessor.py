"""Load geographical data and make it ready for later usage."""

import geopandas as gpd
import numpy as np
from shapely.geometry.multipolygon import MultiPolygon
from shapely.geometry.polygon import Polygon

from ..io import loader


def prep_dataset(
    feature: str,
    source: str = "ne",
    resolution: int = 10,
    identifier: str = "name",
    projection: int = 4326,
) -> gpd.GeoDataFrame:
    """Preprocess a dataset of geographical features.

    All available data sets can be found in the datasets module.

    Args:
        feature: Kind of geographical feature, e.g. "country" or "river".
        source: Data source, e.g. "ne" for NaturalEarth. Defaults to "ne".
        resolution: Resolution of the geographical data. Defaults to 10.
        identifier: There should be a unique identifier for each row in the
            GeoDataFrame. The identifier should be based on an existing column in the
            GeoDataFrame, e.g. the country name. The identifier-parameter determines
            the existing column that is used to base the added "id" column on,
            duplicates are automatically renamed. Defaults to "name".
        projection: The projection of the geographical data. Defaults to 4326, which
            represents projection to longitude and latitude. Options are:
            - 4326: 2D latitude and longitude
            - 3857: 2D in meters

    Raises:
        ValueError: If the identifier does not exist in the loaded GeoDataFrame.
        AssertionError: If the function is not able to create a unique identifier.

    Returns:
        A GeoPandas DataFrame with the requested geographical data.
    """
    gdf = loader.load_dataset(feature, source, resolution)
    gdf = clean_gdf(gdf)
    gdf = gdf.to_crs(epsg=projection)

    # make id unique by adding a suffix (_0, _1, ...) if necessary
    if identifier not in gdf.columns:
        raise ValueError(
            f"The given identifier '{identifier}' does not exist in the GeoDataFrame."
            f"Possibilities are: {gdf.columns}."
        )
    gdf["id"] = gdf[identifier].fillna("Unnamed").astype(str)
    gdf["id"] = (
        gdf.groupby("id")
        .cumcount()
        .astype(str)
        .radd("_")
        .mask(~gdf.duplicated("id", keep=False), "")
        .radd(gdf["id"])
    )
    assert gdf["id"].is_unique, "Error: 'id' column contains duplicate values!"
    return gdf


def clean_gdf(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Clean a geographical DataFrame.

    The process involves:
    - all column names to lower case
    - remove rows with an empty geometry

    Args:
        gdf: DataFrame that should be cleaned.

    Returns:
        A cleaned DataFrame.
    """
    gdf.columns = gdf.columns.str.lower()
    gdf = gdf[~gdf["geometry"].is_empty]
    return gdf


def polygon_is_all_inf(geometry: Polygon | MultiPolygon) -> bool:
    """Check whether ALL coordinate values in a Polygon or Multipolygon are infinity.

    Args:
        geometry: The polygon or multipolygon to check the coordinates.

    Returns:
        True when all coordinate values are infinity, else False.
    """
    if isinstance(geometry, Polygon):
        coords = np.array(geometry.exterior.coords)
    elif isinstance(geometry, MultiPolygon):
        coords = np.array([c for geom in geometry.geoms for c in geom.exterior.coords])
    else:
        return False
    return bool(np.isinf(coords).all())


def get_polygon_bounds(
    geometry: Polygon | MultiPolygon,
) -> tuple[float, float, float, float]:
    """Get the bounds of a Polygon or Multipolygon.

    Args:
        geometry: The polygon or multipolygon to get the bounds.

    Returns:
        A tuple with the bounds (min_x, min_y, max_x, max_y)
    """
    if isinstance(geometry, Polygon):
        min_x, min_y, max_x, max_y = geometry.bounds
        return min_x, min_y, max_x, max_y
    elif isinstance(geometry, MultiPolygon):
        min_x = min(geom.bounds[0] for geom in geometry.geoms)
        min_y = min(geom.bounds[1] for geom in geometry.geoms)
        max_x = max(geom.bounds[2] for geom in geometry.geoms)
        max_y = max(geom.bounds[3] for geom in geometry.geoms)
        return (min_x, min_y, max_x, max_y)
    else:
        raise ValueError("The geometry must be a Polygon or MultiPolygon.")
