"""Load datasets."""

from typing import TypedDict, cast

import geopandas as gpd
import pandas as pd
import yaml

from geofeatureviz.preprocessing import preprocessor

from . import _datasets
from ._path_settings import path_settings


def load_and_prep_data(
    feature: str,
    source: str = "ne",
    resolution: int = 10,
    identifier: str = "name",
    projection: int = 4326,
) -> gpd.GeoDataFrame:
    """Load a dataset with the given keys and preprocess it.

    This is just a convenience function to get a directly usable GeoDataFrame from a
    single function and is just a simple combination of the two functions:
    - loader.load_dataset
    - loader.load_and_prep_data

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

    Returns:
        A GeoPandas DataFrame with the requested preprocessed geographical data.
    """
    dataset = load_dataset(feature=feature, source=source, resolution=resolution)
    return preprocessor.prep_dataset(
        dataset, identifier=identifier, projection=projection
    )


def load_dataset(
    feature: str,
    source: str = "ne",
    resolution: int = 10,
) -> gpd.GeoDataFrame:
    """Load geographical data from a file as GeoPandas GeoDataFrame.

    All available data sets can be found in the datasets module dictionary. The dataset
    is either processed (and hence stored in `data/processed`) or raw (and hence stored
    in `data/raw`). This function returns processed if it exists and raw if not.

    Args:
        feature: Kind of geographical feature, e.g. "country" or "river".
        source: Data source, e.g. "ne" for NaturalEarth. Defaults to "ne".
        resolution: Resolution of the geographical data. Defaults to 10.

    Raises:
        FileNotFoundError: If the requested file could neither be found in the processed
            data dir nor in the raw data dir, even though it is saved in the registry.

    Returns:
        A GeoPandas DataFrame with the requested geographical data.
    """
    dataset_key = _datasets.DatasetKey(feature, source, resolution)
    file_path = _datasets.get_dataset_filepath(dataset_key)
    return gpd.read_file(file_path)


def load_country_translations() -> pd.DataFrame:
    """Get a dataframe containing translations of countries.

    Returns:
        A DataFrame currently containing 3 columns:
        - code: The ISO 3166 alpha 3 country code (3 letter unique country id)
        - german: The German name of the country (consistent with Anki Ultimate
                  Geography, which is consistent with German Wikipedia.)
        - english: The English name of the country (I didn't investigate further).
    """
    df = pd.read_csv(path_settings.country_translation)
    return df


class Region(TypedDict):
    """Provides the structure for regional groups read from the yaml file."""

    core: list[str]
    optional: list[str]
    continent: list[str]
    projection: str


def load_regional_groups() -> dict[str, Region]:
    """Add function to read in regional groups.

    Returns:
        A dictionary with the regional group names as key. The values are dictionaries
        with the keys:
        - "core": List of the core countries of the region.
        - "optional": List of optional countries of the region.
        - "continent": List of continents on which the region is located.
    """
    with open(path_settings.regional_groups, "r", encoding="utf-8") as f:
        regions = yaml.safe_load(f)
    return cast(dict[str, Region], regions)
