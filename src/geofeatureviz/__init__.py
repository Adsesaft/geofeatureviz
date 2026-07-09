"""Provide a tool kit to work with data of geographical features and visualize them."""

__version__ = "0.1.0"

from . import io, map_style, projections, svg_handler
from .preprocessing import preprocessor, river_preprocessor

__all__ = [
    "io",
    "map_style",
    "preprocessor",
    "projections",
    "river_preprocessor",
    "svg_handler",
]
