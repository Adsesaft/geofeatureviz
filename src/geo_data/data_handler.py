import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

import geopandas as gpd
import numpy as np
import pandas as pd
import yaml
from anki.collection import Collection
from shapely.geometry.multipolygon import MultiPolygon
from shapely.geometry.polygon import Polygon

from geo_data import helpers

DATA_FILES = {
    ("country", "ne", 10): "ne_10m_admin_0_countries.zip",
    ("country", "ne", 110): "ne_110m_admin_0_countries.zip",
    ("state", "ne", 10): "ne_10m_admin_1_states_provinces.zip",
    ("river", "ne", 10): "ne_10m_rivers_lake_centerlines.zip",
    ("river_europe", "ne", 10): "ne_10m_rivers_europe.zip",
}
REGIONAL_GROUP_PATH = helpers.get_top_directory() / "data" / "regional_groups.yaml"
COUNTRY_TRANSLATION_PATH = (
    helpers.get_top_directory() / "data" / "country_translations.csv"
)

ANKI_COLLECTION_PATH = Path.home() / ".local" / "share" / "Anki2" / "Adrian"
ANKI_COLLECTION_PATH_COPY = helpers.get_top_directory() / "data"
ANKI_COLLECTION_FILE_NAME = "collection.anki2"


def load(
    kind: str,
    source="ne",
    resolution: int = 10,
    identifier: str = "name",
    projection: int = 4326,
) -> gpd.GeoDataFrame:
    """Load geographical data from a file as GeoPandas GeoDataFrame.

    All available data sets can be found in the DATA_FILES dictionary. A column with a
    unique identifier "id" is added to the DataFrame.

    Args:
        kind: Kind of geographical information, e.g. "country" or "river".
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
    file_path = _get_file_path(kind=kind, source=source, resolution=resolution)
    gdf = gpd.read_file(file_path)
    gdf = clean_gdf(gdf)
    gdf = gdf.to_crs(epsg=projection)

    # make id unique by adding a suffix (_0, _1, ...) if necessary
    if identifier not in gdf.columns:
        raise ValueError(
            f"The given identifier '{identifier}' does not exist in the GeoDataFrame."
        )
    gdf["id"] = gdf[identifier].fillna("Unnamed").astype(str)
    gdf["id"] = (
        gdf.groupby("id")
        .cumcount()
        .astype(str)
        .radd("_")
        .mask(gdf.duplicated("id", keep=False) == False, "")
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
        return geometry.bounds
    elif isinstance(geometry, MultiPolygon):
        min_x = min(geom.bounds[0] for geom in geometry.geoms)
        min_y = min(geom.bounds[1] for geom in geometry.geoms)
        max_x = max(geom.bounds[2] for geom in geometry.geoms)
        max_y = max(geom.bounds[3] for geom in geometry.geoms)
        return (min_x, min_y, max_x, max_y)
    else:
        raise ValueError("The geometry must be a Polygon or MultiPolygon.")


@contextmanager
def open_collection(path: Path | str) -> Generator[Collection, None, None]:
    """Open an anki collection as a context manager to ensure it is properly closed.

    Args:
        path: Path to the Anki collection file. This should never be the original file,
            but a copy.

    Yields:
        An open Anki collection to access decks, notes, note types, etc.
    """
    path = str(path)
    if path == str(ANKI_COLLECTION_PATH / ANKI_COLLECTION_FILE_NAME):
        raise ValueError(
            "The opened Anki collection should never be the original file! Please "
            "provide a copy."
        )
    col = Collection(path)
    try:
        yield col
    finally:
        col.close()


def anki_to_df(deck_name: str) -> pd.DataFrame:
    """Return an Anki deck in the local collection as a pandas DataFrame.

    When exporting Anki decks to csv, it is not possible to include the field names in
    of note type, making it very cumbersome to work with it. This function loads the
    local Anki collection and returns the notes in the deck, including the names of the
    fields of the note type, as well as a column called "NoteType" with the name of the
    note type.

    Args:
        deck_name: Name of the deck to get the notes from. The deck has to exist in the
            local Anki collection with exactly the same name.

    Raises:
        ValueError: When a deck name is given that does not exist in the collection.

    Returns:
        A dataframe with the field names of the note types as columns.
    """
    # copy the original file to avoid any modifications or interference with anki
    src = ANKI_COLLECTION_PATH / ANKI_COLLECTION_FILE_NAME
    copy = ANKI_COLLECTION_PATH_COPY / ANKI_COLLECTION_FILE_NAME
    shutil.copy(src, copy)

    with open_collection(copy) as col:
        # dict mapping note type names to the fields of the note type
        note_type_to_fields = {}
        for model in col.models.all():
            note_type_name = model["name"]
            fields = [field["name"] for field in model["flds"]]
            note_type_to_fields[note_type_name] = fields

        # get the deck
        deck_id = col.decks.id(deck_name)
        if deck_id is None:
            raise ValueError(
                f"The deck '{deck_name}' could not be found in the Anki collection."
            )
        # get cards in the deck
        card_ids = col.decks.cids(deck_id)
        # get note of card ids
        note_ids = set([col.get_card(cid).nid for cid in card_ids])
        notes = [col.get_note(nid) for nid in note_ids]
        assert notes != [], f"There are no notes in the deck '{deck_name}'."

        # create the pandas dataframe
        notes_with_type = []
        for note in notes:
            note_type = note.note_type()
            assert note_type is not None, f"The note {note} does not have a note type."
            note_type_name = note_type["name"]
            fields = note_type_to_fields[note_type_name]
            values = note.values()
            result = dict(zip(fields, values))
            result["NoteType"] = note_type_name
            notes_with_type.append(result)
    return pd.DataFrame(notes_with_type)


def get_regional_groups() -> dict[str, dict[str, list]]:
    """Add function to read in regional groups.

    Returns:
        A dictionary with the regional group names as key. The values are dictionaries
        with the keys:
        - "core": List of the core countries of the region.
        - "optional": List of optional countries of the region.
        - "continent": List of continents on which the region is located.
    """
    with open(REGIONAL_GROUP_PATH, "r", encoding="utf-8") as f:
        regions = yaml.safe_load(f)
    return regions


def get_country_translations() -> pd.DataFrame:
    """Get a dataframe containing translations of countries.

    Returns:
        A DataFrame currently containing 3 columns:
        - code: The ISO 3166 alpha 3 country code (3 letter unique country id)
        - german: The German name of the country (consistent with Anki Ultimate
                  Geography, which is consistent with German Wikipedia.)
        - english: The English name of the country (I didn't investigate further).
    """
    df = pd.read_csv(COUNTRY_TRANSLATION_PATH)
    return df
