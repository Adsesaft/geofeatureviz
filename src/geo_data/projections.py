"""Provide classes and functions for different geographic projections."""

from abc import ABC, abstractmethod

import numpy as np
from numpy.typing import NDArray
from pyproj import Transformer


class Projection(ABC):
    """Provide a class interface for geographical projections.

    This interface ensures a consistent usage of projections throughout this project.
    New projections can be created by letting them inherit from this interface. Then,
    the projections are callable classes. The transformation is therefore defined in the
    __call__-method of each inheriting class. This method always takes longitude and
    latitude values (EPSG 4326) as input and transforms them into the wished projection.
    """

    @abstractmethod
    def __call__(
        self, lon: NDArray[np.float64], lat: NDArray[np.float64]
    ) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        """Project longitude and latitude values (EPSG 4326) into another space.

        Args:
            lon: Longitude values.
            lat: Latitude values.

        Returns:
            Transformed values.
        """
        pass


class Identity(Projection):
    """Project coordinates onto themselves."""

    def __call__(
        self, lon: NDArray[np.float64], lat: NDArray[np.float64]
    ) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        return lon, lat


class Mercator(Projection):
    """Project coordinates using the Mercator projection (EPSG 3857).

    Attributes:
        transformer: The pyproj transformer used for the projection.
    """

    def __init__(self) -> None:
        self.transformer: Transformer = Transformer.from_crs(
            "EPSG:4326", "EPSG:3857", always_xy=True
        )

    def __call__(
        self, lon: NDArray[np.float64], lat: NDArray[np.float64]
    ) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        x, y = self.transformer.transform(lon, lat)
        return x, y


class Equirectangular(Projection):
    """Project coordinates using an equirectangular projection (EPSG 32662).

    Attributes:
        transformer: The pyproj transformer used for the projection.
        y_scale: It is possible to scale the resulting y-values after the projection.
            This is necessary e.g. for some location maps from Wikipedia.
    """

    def __init__(self, y_scale: float = 1):
        """Initialize equirectangular projection.

        Args:
            y_scale: It is possible to scale the resulting y-values after the
                projection. This is necessary e.g. for some location maps from
                Wikipedia. Defaults to 1, hence no scaling.
        """
        self.y_scale: float = y_scale
        self.transformer: Transformer = Transformer.from_crs(
            "EPSG:4326", "EPSG:32662", always_xy=True
        )

    def __call__(
        self, lon: NDArray[np.float64], lat: NDArray[np.float64]
    ) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        x, y = self.transformer.transform(lon, lat)
        return x, y * self.y_scale


class Orthographic(Projection):
    """Project coordinates using an orthographic projection.

    Attributes:
        transformer: The pyproj transformer used for the projection.
        center: The center of the orthographic projection.
        world_radius: The radius of the world in the projected space (in meters).
    """

    def __init__(self, center: tuple[float, float] = (0, 0)):
        """Initialize the orthographic projection.

        Args:
            center: The center of the orthographic projection. Defaults to (0, 0).
        """
        self.center: tuple[float, float] = center
        ortho_proj_str = f"+proj=ortho +lat_0={center[1]} +lon_0={center[0]}"
        transformer: Transformer = Transformer.from_crs(
            "EPSG:4326", ortho_proj_str, always_xy=True
        )
        self.transformer = transformer
        assert transformer.target_crs is not None
        assert transformer.target_crs.ellipsoid is not None
        world_radius = transformer.target_crs.ellipsoid.semi_major_metre
        self.world_radius = world_radius

    def __call__(
        self, lon: NDArray[np.float64], lat: NDArray[np.float64]
    ) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        x, y = self.transformer.transform(lon, lat)
        return x, y
