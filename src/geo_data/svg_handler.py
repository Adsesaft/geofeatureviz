"""Create scalable vector graphics from geometrical data."""

from pathlib import Path

import numpy as np
import svgwrite
from shapely.geometry.base import BaseGeometry
from shapely.geometry.multipolygon import MultiPolygon
from shapely.geometry.polygon import Polygon
from svgwrite.container import Group

COLORS = {
    "background": "#f6f6f6",
    "border": "#646464",
    "land": "#fefee9",
    "river": "#0978ab",
    "lake": "#c6ecff",
}


class MapSVG:

    def __init__(self, name: str | Path, size: int | tuple = 1000):
        """Provide an interface to create SVG files for maps.

        Args:
            name: Name of the SVG file to create (with or without extension).
            size: Size in pixels. When an integer is given, the SVG will be a square.
                Defaults to 1000.
        """
        if not isinstance(size, tuple):
            size = (size, size)
        if not isinstance(name, Path):
            name = Path(name)
        name = name.with_suffix(".svg")

        self.size = size
        self.drawing = svgwrite.Drawing(str(name), size=size)
        self.drawing.add(
            self.drawing.rect(
                insert=(0, 0),
                size=self.size,
                fill=COLORS["background"],
                id="background",
            )
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
            return {"stroke": COLORS["river"], "stroke_width": 1}
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

    def add_group(self, group_id: str, parent_id: str | None = None, **kwargs) -> None:
        """Add a group to the SVG file.

        Args:
            group_id: Identifier of the group to add.
            parent_id: Identifier of the parent to which the group should be added. If
                None is given, the group is added on the base layer. Defaults to None.
        """
        group = self.drawing.g(id=group_id, **kwargs)
        self._add_to_group(parent_id, group)

    def save(self) -> None:
        """Save the SVG file."""
        self.drawing.save()

    def _find_group_by_id(
        self, group_id: str, element: svgwrite.base.BaseElement
    ) -> Group | None:
        """Find a group in the SVG file by its identifier.

        Args:
            group_id: Identifier of the group to find.
            element: Element to start the search from. Typically, this is the base
                drawing.

        Returns:
            The group with the identifier. Returns None if the group is not found.
        """
        if isinstance(element, Group) and element.get_id() == group_id:
            return element

        for child in getattr(element, "elements", []):
            result = self._find_group_by_id(group_id, element=child)
            if result is not None:
                return result

        return None

    def get_group_by_id(self, group_id: str) -> Group:
        """Get a group in the SVG file by its identifier.

        Args:
            group_id: Identifier of the group to get.

        Raises:
            ValueError: If the group with the given identifier is not found.

        Returns:
            The group with the given identifier.
        """
        group = self._find_group_by_id(group_id, self.drawing)
        if group is None:
            raise ValueError(f"Group with id '{group_id}' not found in SVG.")
        return group

    def _add_to_group(
        self, group_id: str | None, element: svgwrite.base.BaseElement
    ) -> None:
        """Add an element to a group in the SVG file.

        Args:
            group_id: The identifier of the group to which the element should be added.
            If
                None is given, the element is added to the base layer.
            element: Element to add to the group.
        """
        if group_id is None:
            group = self.drawing
        else:
            group = self.get_group_by_id(group_id)
        group.add(element)

    def _add_polygon(
        self, points: np.ndarray, element_id: str, group_id: str | None = None
    ) -> None:
        """Add a polygon to the SVG file based on an array of points.

        Args:
            points: Points of the polygon as an array of shape (N, 2).
            element_id: Identifier of the polygon element in the SVG.
            group_id: Identifier of the group to which the polygon should be added. If
                None is given, it is added to the base layer. Defaults to None.
        """
        polygon = self.drawing.polygon(
            points,
            id=element_id,
        )
        self._add_to_group(group_id, polygon)

    def add_polygon(
        self,
        geom: BaseGeometry,
        x_lim: tuple,
        polygon_id: str,
        group_id: str | None = None,
        y_lim: tuple | None = None,
    ) -> None:
        if isinstance(geom, Polygon):
            points = self._polygon_to_svg_coords(geom, x_lim=x_lim, y_lim=y_lim)
            self._add_polygon(points, polygon_id, group_id=group_id)
        elif isinstance(geom, MultiPolygon):
            self.add_group(polygon_id, group_id)
            for i, polygon in enumerate(geom.geoms):
                points = self._polygon_to_svg_coords(polygon, x_lim=x_lim, y_lim=y_lim)
                self._add_polygon(points, f"{polygon_id}_{i}", group_id=polygon_id)
        else:
            raise ValueError(f"This geom_type can not be drawn: {geom.geom_type}")

    def add_circle(self, circle_id: str, group_id: str | None = None, **kwargs) -> None:
        """Add a circle to the SVG file.

        Args:
            circle_id: Identifier of the circle element in the SVG.
            group_id: Identifier of the group to which the circle should be added. If
                None is given, it is added to the base layer. Defaults to None.
            **kwargs: Additional keyword arguments for svgwrite's circle method.
        """
        circle = self.drawing.circle(
            id=circle_id,
            **kwargs,
        )
        self._add_to_group(group_id, circle)

    def _polygon_to_svg_coords(
        self, geom: Polygon, x_lim: tuple, y_lim=None
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
            _description_
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
