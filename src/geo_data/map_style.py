"""Provide colors and styles for geographical map elements.

The most important variables defined in this module are the COLORS and STYLES dicts.
They are loaded from a config file and define colors and styles for geographical
elements like land, sea, etc.
"""

from types import MappingProxyType
from typing import Any

import yaml

from geo_data import helpers

# read config
CONFIG_PATH = helpers.get_top_directory() / "data" / "map_style.yaml"
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
