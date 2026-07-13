"""Load datasets."""

import geopandas as gpd

from geofeatureviz.io import path_settings
from geofeatureviz.preprocessing import preprocessor

from . import datasets


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
