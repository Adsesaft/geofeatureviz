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

    def add_geometry(
        self,
        geom: BaseGeometry,
        x_lim: tuple,
        polygon_id: str,
        group_id: str | None = None,
        y_lim: tuple | None = None,
        **kwargs,
    ) -> None:
        """Add a shapely geometry (from a GeoDataFrame) to the SVG file.

        Currently, only Polygon and MultiPolygon geometries are supported. If a polygon
        is given, it is added as a single polygon. If a multipolygon is given, each
        polygon in the multipolygon is added as a separate polygon, and all polygons
        are grouped together in a group with the given polygon_id.

        Args:
            geom: The geometry to add. Currently, only Polygon and MultiPolygon are
                supported.
            x_lim: Limits of the x-axis of all shapes that will be added to the SVG in
                the domain of the geographical data as (x_min, x_max).
            polygon_id: Identifier name of the polygon or group of polygons.
            group_id: Identifier of the group to which the Polygon should be added.
                Defaults to None.
            y_lim: Limits of the y-axis of all shapes that will be added to the SVG in
                the domain of the geographical data as (y_min, y_max). If None is given,
                the same limits as for the x-axis are taken. Defaults to None.

        Raises:
            ValueError: If an unsupported geometry type is given.
        """
        if isinstance(geom, Polygon):
            points = self._polygon_to_svg_coords(geom, x_lim=x_lim, y_lim=y_lim)
            polygon = svg.Polygon(
                points=list(points.flatten()), id=polygon_id, **kwargs
            )
            self.add(polygon, group_id=group_id)
        elif isinstance(geom, MultiPolygon):
            group_polygons = []
            for i, polygon in enumerate(geom.geoms):
                points = self._polygon_to_svg_coords(polygon, x_lim=x_lim, y_lim=y_lim)
                polygon = svg.Polygon(
                    points=list(points.flatten()), id=f"{polygon_id}_{i}"
                )
                group_polygons.append(polygon)
            group = svg.G(id=polygon_id, elements=group_polygons, **kwargs)
            self.add(group, group_id=group_id)
        else:
            raise ValueError(f"This geom_type can not be added: {geom.geom_type}")

    def _polygon_to_svg_coords(
        self, geom: Polygon, x_lim: tuple, y_lim: tuple | None = None
    ) -> np.ndarray:
        """Get the coordinates of a GeoPandas geometry in SVG coordinates.

        Args:
            geom: Geometry from a GeoPandas GeoDataFrame.
            x_lim: Limits on the x-axis of all shapes that will be added to the SVG in
                the domain of the geographical data as (x_min, x_max).
            y_lim: Limits on the y-axis of all shapes that will be added to the SVG in
                the domain of the geographical data as (y_min, y_max).If None is given,
                the same limits as in x_lim are used. Defaults to None.

        Returns:
            An array with the points of the geometry in SVG coordinates.
        """
        if y_lim is None:
            y_lim = x_lim

        x_min, x_max = x_lim
        y_min, y_max = y_lim
        x_range = x_max - x_min
        y_range = y_max - y_min

        points = np.array(geom.exterior.coords)
        svg_size = np.array(self.size)

        points = points - np.array([x_min, y_min])
        points = points / np.array([x_range, y_range]) * svg_size
        # upside down
        points = points * np.array([1, -1]) + np.array([0, svg_size[0]])
        return points

    def save(self, file_path: str | Path) -> None:
        """Save the SVG file to the given path.

        Args:
            file_path: Path to save the SVG file to.
        """
        path = Path(file_path)
        path.write_text(str(self), encoding="utf-8")
