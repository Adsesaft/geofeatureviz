"""Load datasets and other files."""

from typing import TypedDict, cast

import geopandas as gpd
import pandas as pd
import yaml

from geofeatureviz.io import datasets, path_settings


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
    dataset_key = datasets.DatasetKey(feature, source, resolution)
    file_name = datasets.get_dataset_filename(dataset_key)
    file_path = path_settings.data_processed_dir / file_name
    if not file_path.exists():
        file_path = path_settings.data_raw_dir / file_name
    if not file_path.exists():
        raise FileNotFoundError(
            f"The dataset with key {dataset_key} is saved in the registry, but the "
            "dataset file could not be found in the files."
        )
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
    df = pd.read_csv(path_settings.country_translation_path)
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
    with open(path_settings.regional_groups_path, "r", encoding="utf-8") as f:
        regions = yaml.safe_load(f)
    return cast(dict[str, Region], regions)
