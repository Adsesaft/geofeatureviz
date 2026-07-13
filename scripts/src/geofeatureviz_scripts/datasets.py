"""Registry and path resolution for all datasets."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DatasetKey:
    """Interface to map arguments to datasets.

    Args:
        feature: Kind of geographical feature, e.g. "country" or "river".
        source: Data source, e.g. "ne" for NaturalEarth.
        resolution: Resolution of the geographical data.
    """

    feature: str
    source: str
    resolution: int


DATA_FILES: dict[DatasetKey, str] = {
    DatasetKey("country", "ne", 10): "ne_10m_admin_0_countries.zip",
    DatasetKey("country", "ne", 110): "ne_110m_admin_0_countries.zip",
    DatasetKey("state", "ne", 10): "ne_10m_admin_1_states_provinces.zip",
    DatasetKey("river", "ne", 10): "ne_10m_rivers_lake_centerlines.zip",
    DatasetKey("river_europe", "ne", 10): "ne_10m_rivers_europe.zip",
    DatasetKey("river_germany", "osm", 10): "osm_10m_rivers_germany.geojson",
    DatasetKey("mountain_germany", "osm", 10): "osm_10m_mountains_germany.geojson",
}


def get_dataset_filename(key: DatasetKey) -> Path:
    """Get the file path to the data file from the feature kind, source, and resolution.

    Args:
        key: A Dataset key, consisting of:
            - feature: Kind of geographical information, e.g. "country" or "river".
            - source: Data source, e.g. "ne" for NaturalEarth.
            - resolution: Resolution of the geographical data.

    Raises:
        ValueError: If no data file is found for the given parameters.

    Returns:
        The file name to the requested data.
    """
    file_name = DATA_FILES.get(key, None)
    if file_name is None:
        raise ValueError(
            f"No data file found for {key}. Possible Values are:\n{DATA_FILES}"
        )
    return Path(DATA_FILES[key])
