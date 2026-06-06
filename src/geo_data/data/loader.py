"""Load datasets and other files."""

import json
import warnings
from pathlib import Path
from typing import Optional, TypedDict, cast

import geopandas as gpd
import pandas as pd
import requests
import yaml
from shapely import LineString

from geo_data.data import datasets
from geo_data.data.config import path_settings


def load_dataset(
    feature: str,
    source: str = "ne",
    resolution: int = 10,
) -> gpd.GeoDataFrame:
    """Load geographical data from a file as GeoPandas GeoDataFrame.

    All available data sets can be found in the datasets module dictionary.

    Args:
        feature: Kind of geographical feature, e.g. "country" or "river".
        source: Data source, e.g. "ne" for NaturalEarth. Defaults to "ne".
        resolution: Resolution of the geographical data. Defaults to 10.

    Returns:
        A GeoPandas DataFrame with the requested geographical data.
    """
    dataset_key = datasets.DatasetKey(feature, source, resolution)
    file_path = datasets.get_dataset_path(dataset_key)

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


JSONValue = dict[str, "JSONValue"] | list["JSONValue"] | str | int | float | bool | None


class OverpassElement(TypedDict, total=False):
    """Provide the structure for an element of a response from the Overpass API."""

    tags: dict[str, "JSONValue"]
    geometry: list[dict[str, float]]


class OverpassResponse(TypedDict, total=False):
    """Provide the structure for a response from the Overpass API."""

    elements: list[OverpassElement]
    query: str


class OverpassAPIHandler:
    """Handle Overpass API requests and responses.

    Attributes:
        overpass_url: URL to the Overpass API.
        query: The query which will be requested from the Overpass API.
        file_path: Optional path to a file location where the requested response is
            saved to as JSON-file. If none is given, the response will not be saved.
    """

    def __init__(self, query: str, file_path: Optional[str | Path] = None) -> None:
        """Set up a handler for doing requests on the Overpass API.

        Args:
            query: The query which will be requested from the Overpass API.
            file_path: Optional path to a file location where the requested response is
                saved to as JSON-file. If none is given, the response will not be saved.
                Defaults to None.
        """
        self.overpass_url = "https://overpass-api.de/api/interpreter"
        if file_path is not None:
            file_path = Path(file_path)
            file_path = file_path.with_suffix(".json")
        self.file_path = file_path
        self.query = query

    def _strip_query(self) -> str:
        """Strip a query from trailing whitespaces and remove new lines.

        Returns:
            The stripped query.
        """
        stripped_query = self.query.strip()
        stripped_query = stripped_query.replace("\n", "")
        return stripped_query

    def _get_response_json(
        self,
    ) -> OverpassResponse:
        """Get the Overpass-API response based on the query given in class args.

        Returns:
            A dictionary containing the JSON response from the Overpass API.
        """
        response = requests.post(
            self.overpass_url,
            data={"data": self.query},
            headers={"User-Agent": "DataFetcher/1.0"},
        )
        response.raise_for_status()
        data: OverpassResponse = response.json()
        return data

    def _save_json(self, response_json: OverpassResponse) -> None:
        """Save a dictionary as JSON-file if a filepath was given in class args.

        Args:
            response_json: A dictionary containing a response to save as JSON.
        """
        if self.file_path is None:
            warnings.warn("No file path provided to save the JSON response.")
        else:
            with self.file_path.open("w", encoding="utf-8") as f:
                response_json["query"] = self._strip_query()
                json.dump(response_json, f, indent=2)

    def get(self, save: bool = True) -> OverpassResponse:
        """Get a response from the API as dictionary and save it if possible.

        Args:
            save: Whether the response should be saved as JSON-file in the filepath
                defined as class argument. Defaults to True.

        Returns:
            A dictionary containing the Overpass-API response.
        """
        if self.file_path is None or not self.file_path.exists():
            response_json = self._get_response_json()
            if save:
                self._save_json(response_json)
        else:
            with self.file_path.open("r", encoding="utf-8") as f:
                response_json = json.load(f)
                if response_json.get("query", None) != self._strip_query():
                    warnings.warn(
                        "The query in the existing file doesn't match the current "
                        "query.\n"
                        f"{response_json.get('query', None)}\n"
                        f"{self._strip_query()}\n"
                        "Consider deleting the existing file to get a new response:\n"
                        f"{self.file_path}."
                    )
        return response_json

    def parse_json(self, response_json: OverpassResponse) -> gpd.GeoDataFrame:
        """Parse a dictionary containing an Overpass-API response to a (Geo)DataFrame.

        In general, the response contains a list of "elements" (can be nodes, ways, or
        relations). Each element is represented as row in the DataFrame. The tags of
        the element are "unpacked". If the element contains a "geometry" key, the
        geometry is parsed to a shapely LineString and a geopandas GeoDataFrame is
        returned. If no Geometry is present, a regular pandas DataFrame is returned.

        Args:
            response_json: A dictionary containing the JSON response from the Overpass API.

        Returns:
            A GeoPandas GeoDataFrame containing the parsed elements and geometries or a
            regular Pandas DataFrame if no geometries are present.
        """
        elements = []
        for elem in response_json.get("elements", []):
            # "unpack" the tags
            tags = elem.get("tags", {})
            new_elem = {**elem, **tags}
            new_elem.pop("tags")
            # parse geometry if necessary
            if "geometry" in elem.keys():
                geometry = LineString(
                    [[g["lon"], g["lat"]] for g in elem.get("geometry", [])]
                )
                new_elem["geometry"] = geometry

            elements.append(new_elem)
        return gpd.GeoDataFrame(elements)
