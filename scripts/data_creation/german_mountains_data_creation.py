"""Create a dataset with German mountain ranges.

The geometries of the mountain ranges are loaded from OpenStreetMap.org using the
Overpass API. The mountain ranges that should be loaded are defined in a CSV-file
containing at least the OSM-ID and OSM-type (node / way / relation). The dataset is
saved as GeoJSON-file at the FILE_PATH.
"""

import geopandas as gpd
import pandas as pd
from shapely import LineString, MultiLineString, MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import linemerge, unary_union

from geofeatureviz.data import OverpassAPIHandler, path_settings

FILE_PATH = path_settings.data_processed_dir / "osm_10m_mountains_germany.geojson"


def create_polygons(line: BaseGeometry) -> Polygon | MultiPolygon:
    """Replace (Multi)LineStrings with (Multi)Polygons.

    Args:
        line: A (Multi)LineString that should be replaced by a (Multi)Polygon.

    Raises:
        TypeError: When the input is not a (Multi)LineString.
        ValueError: When the returned result is unexpectedly not a (Multi)Polygon.

    Returns:
        A (Multi)Polygon with the same coordinates as the input (Multi)LineString.
    """
    if not isinstance(line, (LineString, MultiLineString)):
        raise TypeError(f"Expected LineString or MultiLineString, got {type(line)}.")

    if isinstance(line, MultiLineString):
        line = linemerge(line)

    if isinstance(line, LineString):
        return Polygon(line.coords)
    elif isinstance(line, MultiLineString):
        result = unary_union([Polygon(g.coords) for g in line.geoms])
        if isinstance(result, (Polygon, MultiPolygon)):
            return result
        raise ValueError(
            f"Expected Polygon or MultiPolygon as result, got {type(result)}"
        )
    else:
        raise ValueError(f"Expected LineString or MultiLineString, got {type(line)}")


if __name__ == "__main__":
    osm_id_df = pd.read_csv(path_settings.german_mountain_osm_id_path, index_col=0)

    mountain_ids_str = ";".join(
        [f"{row.osm_type}({row.id})" for row in osm_id_df.itertuples()]
    )
    mountain_ids_query = f"({mountain_ids_str};)"

    api_handler = OverpassAPIHandler(
        file_path=path_settings.data_raw_dir
        / "osm_mountains"
        / "german_mountains.json",
    )
    api_handler.create_query(mountain_ids_query, output="geom")
    _ = api_handler.get()

    mountain_gdf = api_handler.parse_json().set_index("id")
    assert isinstance(mountain_gdf, gpd.GeoDataFrame)

    # create polygons from the lines
    mountain_gdf.geometry = gpd.GeoSeries(
        [create_polygons(geom) for geom in mountain_gdf.geometry],
        index=mountain_gdf.index,
        crs=mountain_gdf.crs,
    )

    # save
    if not FILE_PATH.exists():
        mountain_gdf.to_file(FILE_PATH, driver="GeoJson")
        print(f"The dataset has been saved to: {FILE_PATH}")
