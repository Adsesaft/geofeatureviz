"""Provide colors and styles for geographical map elements.

The most important variables defined in this module are the COLORS and STYLES dicts.
They are loaded from a config file and define colors and styles for geographical
elements like, land, sea, etc.
"""

import matplotlib.colors as mcolors
import numpy as np
import yaml
from matplotlib.typing import ColorType
from numpy.typing import NDArray

from geo_data import helpers

# read config
CONFIG_PATH = helpers.get_top_directory() / "data" / "map_style.yaml"
with CONFIG_PATH.open() as f:
    config = yaml.safe_load(f)

# get colors from config
COLORS: dict[str, ColorType] = config["colors"]

# get styles from config and resolve colors
# (e.g. if in styles "fill: land", land is replaced by "#fefee9")
STYLES: dict[str, dict] = config["styles"]
for _, kwargs in STYLES.items():
    for key, value in kwargs.items():
        if value in COLORS.keys():
            kwargs[key] = COLORS[value]
