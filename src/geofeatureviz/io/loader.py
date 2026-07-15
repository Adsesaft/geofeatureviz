"""Load datasets and other files."""

from typing import TypedDict, cast

import yaml

from .config import path_settings


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
