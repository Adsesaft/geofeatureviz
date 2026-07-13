"""Load datasets."""

import geopandas as gpd

from geofeatureviz.io import loader
from geofeatureviz.preprocessing import preprocessor


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
    dataset = loader.load_dataset(feature=feature, source=source, resolution=resolution)
    return preprocessor.prep_dataset(
        dataset, identifier=identifier, projection=projection
    )
