"""Provide a tool kit to work with data of geographical features and visualize them."""

from . import io, projections, rendering
from .preprocessing import preprocessor, river_preprocessor

__version__ = "0.1.0"

__all__ = [
    "io",
    "preprocessor",
    "projections",
    "rendering",
    "river_preprocessor",
]
