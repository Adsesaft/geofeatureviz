"""Create scalable vector graphics from geometrical data."""

from pathlib import Path

import numpy as np
import svg
from shapely.geometry.base import BaseGeometry
from shapely.geometry.multipolygon import MultiPolygon
from shapely.geometry.polygon import Polygon

COLORS = {
    "background": "#f6f6f6",
    "border": "#646464",
    "land": "#fefee9",
    "river": "#0978ab",
    "lake": "#c6ecff",
}

_BOUNDS_TYPE = tuple[float, float] | tuple[float, float, float, float]


class MapSVG(svg.SVG):

    def __init__(
        self,
        size: int | tuple = 1000,
        bounds: _BOUNDS_TYPE = (-90, -180, 90, 180),
        *args,
        **kwargs,
    ):
        """Provide an interface to create SVG files for maps.

        Args:
            name: Name of the SVG file to create (with or without extension).
            size: Size in pixels. When an integer is given, the SVG will be a square.
                Defaults to 1000.
            bounds: Bounds of the geometry as (x_min, y_min, x_max, y_max) in the domain
                of the geographical data. If only (x_min, x_max) are given, the same
                limits are used for y as well.
        """
        if not isinstance(size, tuple):
            size = (size, size)
        self.size = size
        # TODO: can I remove size and only use the bounds and a scaling?

        if len(bounds) == 2:
            x_min, x_max = bounds
            y_min, y_max = bounds
            bounds = (x_min, y_min, x_max, y_max)
        self.bounds = bounds

        background = svg.Rect(
            x=0,
            y=0,
            width=size[0],
            height=size[1],
            fill=COLORS["background"],
            id="background",
        )
        super().__init__(
            width=size[0], height=size[1], elements=[background], *args, **kwargs
        )

    def get_kwargs(self, kind: str) -> dict:
        """Get keyword arguments for svgwrite elements from geographical feature type.

        Args:
            kind: Type of the geographical feature. Possibilities are: "land", "river",
                "lake", "sea".

        Raises:
            ValueError: When an unknown kind is given.

        Returns:
            A dictionary with keyword arguments for svgwrite elements.
        """
        if kind == "land":
            return {
                "fill": COLORS["land"],
                "stroke": COLORS["border"],
                "stroke_width": 1,
            }
        elif kind == "river":
            return {"style": "fill:none", "stroke": COLORS["river"], "stroke_width": 1}
        elif kind == "lake":
            return {
                "fill": COLORS["lake"],
                "stroke": COLORS["river"],
                "stroke_width": 1,
            }
        elif kind == "sea":
            return {"fill": COLORS["lake"]}
        else:
            raise ValueError(f"Unknown kind '{kind}'")

    def add(self, element: svg.Element, group_id: str | None = None) -> None:
        """Add an element to the SVG file.

        Args:
            element: Element to add to the group.
            group_id: The identifier of the group to which the element should be added.
                If None is given, the element is added to the base layer.
        """
        if group_id is None:
            group = self
        else:
            group = self.get_group_by_id(group_id)
        if group.elements is not None:
            group.elements.append(element)
        else:
            group.elements = [element]

    def get_group_by_id(self, group_id: str) -> svg.G:
        """Get a group in the SVG file by its identifier.

        Args:
            group_id: Identifier of the group to get.

        Raises:
            ValueError: If the group with the given identifier is not found.

        Returns:
            The group with the given identifier.
        """
        group = self._find_group_by_id(group_id, self)
        if group is None:
            raise ValueError(f"Group with id '{group_id}' not found in SVG.")
        return group

    def _find_group_by_id(self, group_id: str, element: svg.Element) -> svg.G | None:
        """Find a group in the SVG file by its identifier.

        Args:
            group_id: Identifier of the group to find.
            element: Element to start the search from. Typically, this is the base
                drawing.

        Returns:
            The group with the identifier. Returns None if the group is not found.
        """
        if isinstance(element, svg.G) and element.id == group_id:
            return element

        children = element.elements
        if children is not None:
            for child in children:
                result = self._find_group_by_id(group_id, element=child)
                if result is not None:
                    return result
        return None

    def geometry_to_svg(
        self,
        geometry: BaseGeometry,
        geometry_id: str,
        **kwargs,
    ) -> svg.Element:
        """Create an SVG-element from a shapely geometry (from a GeoDataFrame) to the SVG file.

        Currently, only Polygon and MultiPolygon geometries are supported. If a polygon
        is given, it is created as a single polygon. If a multipolygon is given, each
        polygon in the multipolygon is added as a separate polygon, and all polygons
        are grouped together in a group with the given geometry_id.

        Args:
            geometry: The geometry to create an SVG-element from. Currently, only
                Polygon and MultiPolygon are supported.
            geometry_id: Identifier name of the polygon or group of polygons.

        Raises:
            ValueError: If an unsupported geometry type is given.
        """
        if isinstance(geometry, Polygon):
            points = np.array(geometry.exterior.coords)
            points = self._transform_to_svg_coords(points)
            svg_element = svg.Polygon(
                points=list(points.flatten()), id=geometry_id, **kwargs
            )
        elif isinstance(geometry, MultiPolygon):
            group_polygons = []
            for i, polygon in enumerate(geometry.geoms):
                points = np.array(polygon.exterior.coords)
                points = self._transform_to_svg_coords(points)
                polygon = svg.Polygon(
                    points=list(points.flatten()), id=f"{geometry_id}_part_{i}"
                )
                group_polygons.append(polygon)
            svg_element = svg.G(id=geometry_id, elements=group_polygons, **kwargs)
        else:
            raise ValueError(f"This geom_type can not be added: {geometry.geom_type}")
        return svg_element

    def _transform_to_svg_coords(
        self,
        points: np.ndarray,
    ) -> np.ndarray:
        """Get the coordinates of a GeoPandas geometry in SVG coordinates.

        Args:
            points: Coordinate points in a domain that should be transformed to this
                SVG-coordinate system. Array of shape (n, 2).

        Returns:
            An array with the points of the geometry in SVG coordinates.
        """
        x_min, y_min, x_max, y_max = self.bounds
        x_range, y_range = x_max - x_min, y_max - y_min

        svg_size = np.array(self.size)

        points = points - np.array([x_min, y_min])
        points = points / np.array([x_range, y_range]) * svg_size
        # upside down
        points = points * np.array([1, -1]) + np.array([0, svg_size[1]])
        return points

    def save(self, file_path: str | Path) -> None:
        """Save the SVG file to the given path.

        Args:
            file_path: Path to save the SVG file to.
        """
        path = Path(file_path)
        path.write_text(str(self), encoding="utf-8")
