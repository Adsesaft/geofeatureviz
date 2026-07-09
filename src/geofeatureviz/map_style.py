"""Provide colors and styles for geographical map elements.

The most important variables defined in this module are the COLORS and STYLES dicts.
They are loaded from a config file and define colors and styles for geographical
elements like land, sea, etc.
"""

from collections.abc import Sequence
from types import MappingProxyType
from typing import Any

import matplotlib.colors as mplc
import numpy as np
import yaml
from matplotlib.typing import ColorType
from numpy.typing import ArrayLike, NDArray

from .io.config import path_settings

# read config
CONFIG_PATH = path_settings.data_dir / "map_style.yaml"
with CONFIG_PATH.open() as f:
    config = yaml.safe_load(f)

# get colors from config and create immutable dict
COLORS: MappingProxyType[str, str] = MappingProxyType(config["colors"])

# get styles from config and resolve colors
# (e.g. if in styles "fill: land", land is replaced by "#fefee9")
_styles = config["styles"]
for style_name, kwargs in _styles.items():
    for key, value in kwargs.items():
        kwargs[key] = COLORS.get(value, value)
    _styles[style_name] = MappingProxyType(kwargs)

# immutable dict
STYLES: MappingProxyType[str, MappingProxyType[str, Any]] = MappingProxyType(_styles)


def get_topo_colors() -> dict[str, dict[int, str]]:
    """Get all colors for topographical data.

    Returns:
        Dictionaries mapping elevation levels to colors. This will return a dictionary
        with the keys "land" and "water", each containing a dictionary mapping elevation
        levels to colors. It is necessary to differentiate between land and water
        because both can have negative and positive elevation levels, but the colors
        used for them are different (e.g., negative land can be dark green, but negative
        water can be dark blue).
    """
    topo_colors: dict[str, dict[int, str]] = {"land": {}, "water": {}}
    for color_name, color in COLORS.items():
        if "topo" in color_name:
            topo_str_split = color_name.split(":")
            topo_type, topo_level = topo_str_split[1], int(topo_str_split[2])
            topo_colors[topo_type][topo_level] = color
    return topo_colors


class ElevationColormap(mplc.ListedColormap):
    """Colormap of elevation levels for topographic maps."""

    def __init__(
        self,
        colors_below: Sequence[ColorType],
        color_sea_level: ColorType,
        colors_above: Sequence[ColorType],
    ) -> None:
        """Initialize the colormap for elevation levels in a topographic map.

        Args:
            colors_below: Colors for elevation levels below sea level, in increasing
                order of elevation.
            color_sea_level: Color for sea level (elevation = 0).
            colors_above: Colors for elevation levels above sea level, in increasing
                order of elevation.
        """
        n_max = max(len(colors_below), len(colors_above))
        colors_below = self._stretch_list(list(colors_below)[::-1], n_max)[::-1]
        colors_above = self._stretch_list(list(colors_above), n_max)
        assert len(colors_below) == len(colors_above)
        colors = list(colors_below) + [color_sea_level] + list(colors_above)
        super().__init__(colors, name="elevation")

    def _stretch_list(self, lst: list[Any], target_len: int) -> list[Any]:
        """Stretch a list to a target length by repeating the last element.

        Args:
            lst: The list to stretch.
            target_len: The desired length of the list.

        Returns:
            A new list of length target_len, where the last element of lst is repeated.
        """
        n_missing = target_len - len(lst)
        return list(lst) + n_missing * [lst[-1]]

    def get_hex(self, values: ArrayLike) -> str | NDArray[np.str_]:
        """Get the hex representation of the colors for the values.

        Args:
            values: Values for which the colors are requested.

        Returns:
            Colors in hex format for the given values.
        """
        values = np.asarray(values)
        colors = np.asarray(super().__call__(values)).reshape((-1, 4))
        hex_colors = [mplc.to_hex(tuple(color)) for color in colors]
        if values.ndim == 0:
            return hex_colors[0]
        return np.reshape(hex_colors, values.shape)


class ElevationNorm(mplc.TwoSlopeNorm):
    """Normalize elevation values around zero for diverging colormaps."""

    def __init__(self, thresholds: list[float]) -> None:
        """Initialize normalization to center around zero.

        Args:
            thresholds: Threshold values used to determine the symmetric normalization
                range. The maximum absolute threshold defines the distance from zero to
                the lower and upper normalization bounds.
        """
        max_threshold = np.max(np.abs(thresholds))
        super().__init__(vmin=-max_threshold, vmax=max_threshold, vcenter=0)


def get_elevation_cmap(topo_type: str = "land") -> ElevationColormap:
    """Get the colormap for elevations from the defined style.

    Args:
        topo_type: The topography type for which to get the colormap. Can be either
            "land" or "water". Default is "land".

    Returns:
        The elevation colormap for the specified topography type.
    """
    topo_colors = get_topo_colors()[topo_type]
    # sort and remove lower than sea level
    colors_above = []
    colors_below = []
    color_sea_level = ""
    for level, color in sorted(topo_colors.items()):
        if level < 0:
            colors_below.append(color)
        elif level > 0:
            colors_above.append(color)
        else:
            color_sea_level = color
    return ElevationColormap(
        colors_below=colors_below,
        color_sea_level=color_sea_level,
        colors_above=colors_above,
    )
