"""Provide utils to run scripts using geofeatureviz.

GeoFeatureViz should serve as a standalone library that provides functionality for
visualizing geographical features. Running scripts using this library does, for example,
not integrate things like loading data, using jupyter notebooks, or using data-specific
configurations. The idea of this sub-project is to provide these kind of things, to
separate the core library from data- and user-specific script-utils.
"""

from . import loader
from ._path_settings import path_settings

__all__ = ["loader", "path_settings"]
