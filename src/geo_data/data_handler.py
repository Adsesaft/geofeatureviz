from pathlib import Path

import geopandas as gpd

from geo_data import helpers

DATA_FILES = {
    ("country", "ne", 10): "ne_10m_admin_0_countries.zip",
    ("country", "ne", 110): "ne_110m_admin_0_countries.zip",
    ("state", "ne", 10): "ne_10m_admin_1_states_provinces.zip",
    ("river", "ne", 10): "ne_10m_rivers_lake_centerlines.zip",
    ("river_europe", "ne", 10): "ne_10m_rivers_europe.zip",
}


def load(kind: str, source="ne", resolution: int = 10) -> gpd.GeoDataFrame:
    """Load geographical data from a file as GeoPandas DataFrame.

    All available data sets can be found in the DATA_FILES dictionary.

    Args:
        kind: Kind of geographical information, e.g. "country" or "river".
        source: Data source, e.g. "ne" for NaturalEarth. Defaults to "ne".
        resolution: Resolution of the geographical data. Defaults to 10.

    Returns:
        A GeoPandas DataFrame with the requested geographical data.
    """
    file_path = _get_file_path(kind=kind, source=source, resolution=resolution)
    gdf = gpd.read_file(file_path)
    gdf = clean_gdf(gdf)
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


def _get_file_path(kind: str, source: str, resolution: int) -> Path:
    """Get the file path to the data file from the kind, source, and resolution.

    Args:
        kind: Kind of geographical information, e.g. "country" or "river".
        source: Data source, e.g. "ne" for NaturalEarth.
        resolution: Resolution of the geographical data.

    Raises:
        ValueError: If no data file is found for the given parameters.

    Returns:
        A file path to the requested data file.
    """
    file_name = DATA_FILES.get((kind, source, resolution), None)
    if file_name is None:
        raise ValueError(
            f"No data file found for {kind}, {source}, {resolution}. Possible Values "
            f"are: {DATA_FILES}"
        )
    return helpers.get_top_directory() / "data" / file_name
