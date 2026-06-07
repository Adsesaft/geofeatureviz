"""Preprocess river data."""

import warnings
from typing import cast

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import yaml
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from numpy.typing import NDArray
from shapely import LineString, MultiLineString
from shapely.ops import linemerge

from geofeatureviz import helpers


def _is_valid_member_gdf(member_gdf: gpd.GeoDataFrame) -> bool:
    """Check whether a GeoDataFrame contains members of an OSM river relation.

    Args:
        member_gdf: GeoDataFrame to check.

    Returns:
        True if valid (contains all required columns and has valid geometries),
        otherwise False.
    """
    required_columns = {"relation_name", "waterway", "role"}
    if not required_columns.issubset(member_gdf.columns):
        return False

    if not all(isinstance(g, LineString) for g in member_gdf.geometry):
        return False

    return True


class RiverCleanConfig:
    """Provide a class to load and apply a config file for cleaning rivers.

    The config file contains information about which members of a river relation should
    be modified, and how they should be modified. The modifications are defined as a
    list of either integers or slices, containing information about which nodes in the
    geometry of the member with the OSM-ID should be deleted in preprocessing. See the
    config file at `self.CONFIG_PATH` for more details.

    Attributes:
        CONFIG_PATH: File path to the config file for cleaning the river data.
    """

    CONFIG_PATH = (
        helpers.get_top_directory() / "data" / "config" / "river_clean_data_config.yaml"
    )

    def __init__(self) -> None:
        """Initialize the config by loading the config file."""
        self.config_dict = self._parse_config_dict()

    def _parse_config_dict(self) -> dict[str, dict[int, list[slice | int]]]:
        """Get config for cleaning the river data.

        Returns:
            A dictionary mapping river names to dictionaries containing information
            about what to delete. This dictionary maps OSM-IDs of the river members to
            a list of either integers or slices, containing information about which
            nodes in the geometry of the member with the OSM-ID should be deleted in
            preprocessing.
        """
        with self.CONFIG_PATH.open("r", encoding="utf-8") as f:
            river_clean_data_config = yaml.safe_load(f)
            for river_config in river_clean_data_config.values():
                for ref, idx_or_slices in river_config.items():
                    idx = []
                    for i_or_s in idx_or_slices:
                        if isinstance(i_or_s, list):
                            # parse slices
                            idx.append(slice(*i_or_s))
                        else:
                            idx.append(i_or_s)
                    river_config[ref] = idx
        return cast(dict[str, dict[int, list[slice | int]]], river_clean_data_config)

    def _get_idx_to_delete(
        self, idx_or_slices: list[int | slice], array_len: int
    ) -> NDArray[np.int_]:
        """Get the indices to delete from an array of the given length.

        Args:
            idx_or_slices: A list of either indices or slices.
            array_len: The length of the array from which the indices / slices should
                be deleted.

        Returns:
            The list of integers containing the indices to delete, sorted and without
            duplicates.
        """
        idx: list[int] = []
        for i_or_s in idx_or_slices:
            if isinstance(i_or_s, slice):
                idx.extend(range(*i_or_s.indices(array_len)))
            else:
                idx.append(i_or_s)
        return np.unique(idx)

    def apply(self, member_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Apply the changes defined in the config to the GeoDataFrame.

        Args:
            member_gdf: A GeoDataFrame containing the members of a river relation.
                Additionally, the GeoDataFrame should contain a column "relation_name"
                containing the name of the river relation. These relation names have to
                match the keys in the config dictionary.

        Returns:
            A GeoDataFrame with the same structure as the input, but with the geometries
            of the members modified according to the config. The geometries of the
            members that are not mentioned in the config are not modified. Additionally,
            members whose geometry is empty after the modifications are removed from the
            GeoDataFrame.
        """
        assert _is_valid_member_gdf(member_gdf)
        river_name = member_gdf["relation_name"].iloc[0]
        river_config = self.config_dict.get(river_name, {})
        for member_id, idx in river_config.items():
            if member_id not in member_gdf.index:
                warnings.warn(
                    f"Member with OSM-ID {member_id} not found in GeoDataFrame for "
                    f"river {river_name}, but is mentioned in the config. Skipping."
                )
                continue
            geom = member_gdf.loc[member_id, "geometry"]
            assert isinstance(geom, LineString)
            coords = list(geom.coords)
            idx = self._get_idx_to_delete(idx, len(coords))
            new_coords = np.delete(coords, idx, axis=0)
            member_gdf.loc[member_id, "geometry"] = LineString(new_coords)
        member_gdf = member_gdf[~member_gdf["geometry"].is_empty]

        return member_gdf


CONFIG = RiverCleanConfig()


def snap_endpoints(geom: MultiLineString, threshold: float) -> MultiLineString:
    """Snap the end points of the lines.

    Each lines' endpoints are snapped to the closest endpoints of the other lines, if
    their distance is lower than a specific threshold. This can be used to merge lines
    that are close to each other but are not connected, e.g. due to small gaps in the
    data. This function is similar to `shapely.ops.snap` but only applied to the
    endpoints of the lines.

    Args:
        geom: The MultiLineString where the lines should be snapped.
        threshold: The distance threshold for which line endpoints are "snapped". The
            unit should be the same as the given geometry (probably a projection to
            meters, e.g. through Web Mercator `gdf.to_crs("EPSG:3857")` is recommended).

    Returns:
        The resulting geometry after snapping.
    """
    lines = list(geom.geoms)
    for i, line in enumerate(lines):
        # has to be inside loop since the endpoints change
        end_points = np.array([np.array(line.coords)[[0, -1]] for line in lines])
        other_end_points = np.delete(end_points, i, axis=0).reshape((-1, 2))
        this_end_points = end_points[i]

        diff = other_end_points.reshape((1, -1, 2)) - this_end_points.reshape(
            (-1, 1, 2)
        )
        distances = np.linalg.norm(diff, axis=-1)

        min_idx = distances.argmin(axis=1)
        min_val = distances[np.arange(distances.shape[0]), min_idx]

        mask = min_val < threshold
        if min_idx[0] == min_idx[1]:
            eq_mask = np.arange(2) == np.argmax(min_val)
            mask = mask & eq_mask

        coords = np.array(line.coords)
        idx = np.array([0, -1])
        coords[idx[mask]] = other_end_points[min_idx[mask]]

        lines[i] = LineString(coords)
    return MultiLineString(lines)


def prep_member_gdf(member_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Preprocess a GeoDataFrame of members of a river relation.

    Preprocessing includes:
    - Removing members that do not have a "waterway" tag.
    - Removing members that have the role "side_stream" or "distributary".
    - Applying the cleaning config defined in `river_preprocessor.CONFIG` (removing
      nodes from the geometries of the members, sometimes even the complete member).

    Args:
        member_gdf: A GeoDataFrame that contains members of an OSM river relation. It
            has to contain a column "waterway" (matching the OSM tag "waterway") and a
            column "role" (matching the OSM role of the member in the relation).
            Additionally, it should contain a column "relation_name" containing the
            name of the river relation, which is used to apply the cleaning config.

    Returns:
        A preprocessed GeoDataFrame of river members.
    """
    member_gdf = member_gdf[~member_gdf["waterway"].isna()]
    member_gdf = member_gdf[~member_gdf["role"].isin(["side_stream", "distributary"])]
    member_gdf = CONFIG.apply(member_gdf)
    return member_gdf


def member_gdf_to_linestring(
    member_gdf: gpd.GeoDataFrame,
) -> LineString | MultiLineString:
    """Try to create a single linestring from a GeoDataFrame with river members.

    Args:
        member_gdf: A GeoDataFrame, where the geometries are all line strings.

    Returns:
        A geometry that is a single line string, if the geometries in the Geo DataFrame
        could be merged. If merging was not possible, a warning is given and a
        MultiLineString is returned.
    """
    assert _is_valid_member_gdf(member_gdf)
    geoms = cast(list[LineString], member_gdf.geometry.to_list())

    if not all(isinstance(g, (LineString, MultiLineString)) for g in geoms):
        raise TypeError("All geometries must be LineString or MultiLineString")
    geom = linemerge(geoms)

    if isinstance(geom, MultiLineString):
        # geom = snap_endpoints(geom, threshold=0.5)
        geom = linemerge(geom)
    if not isinstance(geom, LineString):
        warnings.warn(
            f"After merging the lines, the resulting geometry is still a "
            f"MultiLineString with {len(geom.geoms)} geometries."
        )
    return geom


def inspect_river_geom(
    geom: LineString | MultiLineString, member_gdf: gpd.GeoDataFrame
) -> tuple[Figure, Axes]:
    """Inspect a river geometry and its members by plotting them.

    Args:
        geom: Geometry of the river, which is either a LineString or a MultiLineString.
            Usually, this is the result of preprocessing the river, with the goal to
            obtain a single LineString, and if it is not a single LineString, to inspect
            why the members and their geometries fail to merge into a single LineString.
            This geometry is plotted transparently and wider in the background.

        member_gdf: A GeoDataFrame containing the members of the river relation. This is
            usually the GeoDataFrame before merging the geometries, but after
            preprocessing (e.g. removing members), so that it is possible to inspect
            which members cause trouble in merging the geometries. The geometries of all
            members are plotted in the foreground, and the ID of each member is shown
            as text next to the member's geometry.

    Returns:
        A tuple containing the matplotlib figure and axes.
    """
    assert _is_valid_member_gdf(member_gdf)
    fig, ax = plt.subplots(figsize=(10, 10))
    if isinstance(geom, MultiLineString):
        geoms = list(geom.geoms)
    else:
        geoms = [geom]
    for i, g in enumerate(geoms):
        coords = np.array(g.coords)
        ax.plot(*coords.T, linewidth=2, alpha=0.1, solid_capstyle="butt", label=f"{i}")
    for member_id, member_geom in member_gdf.geometry.items():
        coords = np.array(member_geom.coords)
        ax.plot(*coords.T, linewidth=0.1, solid_capstyle="butt")
        mean_coord = np.mean(coords, axis=0)
        ax.text(mean_coord[0], mean_coord[1], str(member_id), fontsize=0.5)
    ax.legend()
    ax.set_title(member_gdf["relation_name"].iloc[0])
    return fig, ax
