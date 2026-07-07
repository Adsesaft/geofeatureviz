"""Provide colors and styles for geographical map elements.

The most important variables defined in this module are the COLORS and STYLES dicts.
They are loaded from a config file and define colors and styles for geographical
elements like land, sea, etc.
"""

from types import MappingProxyType
from typing import Any

import yaml

from geofeatureviz.data.config import path_settings

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
