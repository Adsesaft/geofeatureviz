"""Provide modules to render maps.

This package especially makes it possible to render maps as Scalable Vector Graphics
using a specific style, e.g. based on the Wikipedia map template.
"""

from .map_style import (
    COLORS,
    STYLES,
    ElevationColormap,
    ElevationNorm,
    get_elevation_cmap,
    get_topo_colors,
)
from .svg_handler import DiagonalStripedPattern, MapSVG, OrthoMapSVG

__all__ = [
    "COLORS",
    "DiagonalStripedPattern",
    "ElevationColormap",
    "ElevationNorm",
    "get_elevation_cmap",
    "get_topo_colors",
    "map_style",
    "MapSVG",
    "OrthoMapSVG",
    "STYLES",
]
