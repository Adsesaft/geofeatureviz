"""Load datasets and other files."""

import json
import warnings
from pathlib import Path
from typing import Literal, NotRequired, Optional, TypedDict, cast

import geopandas as gpd
import pandas as pd
import requests
import yaml
from shapely import LineString, MultiLineString, Point
from shapely.ops import linemerge

from geofeatureviz.data import datasets
from geofeatureviz.data.config import path_settings


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


JSONValue = dict[str, "JSONValue"] | list["JSONValue"] | str | int | float | bool | None


class OverpassNode(TypedDict):
    """Structure of an OSM-node in the JSON response from the Overpass API."""

    id: int
    type: Literal["node"]
    lat: float
    lon: float


class OverpassGeometry(TypedDict):
    """Structure of a geometry in the JSON response from the Overpass API."""

    lat: float
    lon: float


class OverpassWay(TypedDict):
    """Structure of an OSM-way in the JSON response from the Overpass API."""

    id: int
    type: Literal["way"]
    nodes: list[int]
    tags: NotRequired[dict[str, "JSONValue"]]
    bounds: NotRequired[dict[str, float]]
    geometry: NotRequired[list[OverpassGeometry]]


class RelationMember(TypedDict):
    """Structure of a relation member in the JSON response from the Overpass API."""

    type: Literal["node", "way", "relation"]
    ref: int
    role: str
    geometry: NotRequired[list[OverpassGeometry]]


class OverpassRelation(TypedDict):
    """Structure of an OSM-relation in the JSON response from the Overpass API."""

    id: int
    type: Literal["relation"]
    members: list[RelationMember]
    tags: NotRequired[dict[str, "JSONValue"]]
    bounds: NotRequired[dict[str, float]]


OverpassElement = OverpassNode | OverpassWay | OverpassRelation


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

    def __init__(self, query: str = "", file_path: Optional[str | Path] = None) -> None:
        """Set up a handler for doing requests on the Overpass API.

        Args:
            query: The query which will be requested from the Overpass API. To create a
                request, a query is mandatory, but it can also be set using the
                `create_query` method and is therefore optional. Default is an empty
                string.
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
        self.response_json: OverpassResponse | None = None

    def _strip_query(self) -> str:
        """Strip a query from trailing whitespaces and remove new lines.

        Returns:
            The stripped query.
        """
        lines = self.query.split("\n")
        stripped_query = "".join([line.strip() for line in lines])
        return stripped_query

    def _get_response_json(
        self,
    ) -> OverpassResponse:
        """Get the Overpass-API response based on the query given in class args.

        Returns:
            A dictionary containing the JSON response from the Overpass API.
        """
        if self.query == "":
            raise ValueError(
                "The query is empty. Set a query by either setting the class attribute "
                "or using `create_query`."
            )
        response = requests.post(
            self.overpass_url,
            data={"data": self.query},
            headers={"User-Agent": "DataFetcher/1.0"},
        )
        response.raise_for_status()
        response_json: OverpassResponse = response.json()
        return response_json

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
        self.response_json = response_json
        return response_json

    def parse_json(
        self, response_json: Optional[OverpassResponse] = None
    ) -> gpd.GeoDataFrame:
        """Parse a dictionary containing an Overpass-API response to a (Geo)DataFrame.

        In general, the response contains a list of "elements" (can be nodes, ways, or
        relations). After parsing, each element is represented as a row in a DataFrame.
        The tags of the element are "unpacked", and if the element contains geometric
        information, the geometry is parsed to a shapely geometry:
        - node:     Point
        - way:      LineString
        - relation: MultiLineString (or LineString if the member lines can be merged)

        If there is a geometry, a geopandas.GeoDataFrame is returned, else a regular
        pandas.DataFrame.

        Args:
            response_json: A dictionary containing the JSON response from the
                Overpass API. If this is not given, the class attribute response_json
                is used, which has to be not None (e.g., by calling
                `OverpassAPIHandler.get()`).

        Returns:
            A geopandas.GeoDataFrame containing the parsed elements and geometries or a
            regular pandas.DataFrame if no geometries are present.
        """
        if response_json is None:
            response_json = self.response_json
        if response_json is None:
            raise ValueError(
                "Either provide a response_json as input parameter or set the class "
                "attribute response_json (e.g. with `get()`)."
            )
        elements = []
        for elem in response_json.get("elements", []):
            new_elem = dict(elem)

            # parse geometry if necessary
            geometry: Point | LineString | MultiLineString | None = None
            if elem["type"] == "node":
                geometry = Point(elem["lon"], elem["lat"])
                new_elem.pop("lon")
                new_elem.pop("lat")
            elif elem["type"] == "way" and "geometry" in elem.keys():
                geometry = self._parse_geom(elem.pop("geometry"))
                new_elem.pop("nodes")
            elif elem["type"] == "relation":
                geoms = []
                for member in elem["members"]:
                    if "geometry" in member.keys():
                        geoms.append(self._parse_geom(member.get("geometry", [])))
                if geoms:
                    geometry = linemerge(geoms)
                    new_elem.pop("members")

            if geometry is not None:
                new_elem["geometry"] = geometry

            # "unpack" the tags
            if elem["type"] == "way" or elem["type"] == "relation":
                tags = elem.get("tags", {})
                new_elem.pop("tags")
                new_elem = new_elem | tags

            elements.append(new_elem)
        return gpd.GeoDataFrame(elements, crs="EPSG:4326")

    def _parse_geom(self, geom_list: list[OverpassGeometry]) -> LineString:
        """Parse a list of lon/lat values to a LineString.

        Args:
            geom_list: A list of dictionaries, where each dictionary has the keys "lon"
                and "lat", containing longitude and latitude of the point. All points
                are parsed and a LineString is created from the points.

        Returns:
            A LineString geometry of all points.
        """
        return LineString([[g["lon"], g["lat"]] for g in geom_list])

    def create_query(self, query: str, timeout: int = 150, output: str = "body") -> str:
        """Create a query for the overpass API and set the class attribute.

        This function just covers up some of the required syntax of the OSM query
        language and sets the default beginning and end of a query.

        Args:
            query: The elements that should be requested from the API using the OSM
                query syntax, e.g., 'relation(123456)' or 'relation["name"~"^A$|^B$"]'.
            timeout: Maximum time to wait for the API response. Default is 150.
            output: The output of the API response, e.g. "geom" for the geometries or
                "body" for IDs, tags, and references. Default is "body".

        Returns:
            The created query, which is also set as class attribute.
        """
        query = f"""[out:json][timeout:{timeout}];
        {query};
        out {output};"""
        self.query = query
        return query
