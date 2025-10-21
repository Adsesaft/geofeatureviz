"""Create scalable vector graphics from geometrical data."""

from pathlib import Path
from typing import Callable, Optional, cast

import numpy as np
import svg
from geopandas import GeoDataFrame
from numpy.typing import ArrayLike, NDArray
from pyproj import Transformer
from shapely import (
    GeometryCollection,
    LineString,
    MultiPolygon,
    Polygon,
    make_valid,
    unary_union,
)
from shapely.geometry.base import BaseGeometry, BaseMultipartGeometry

COLORS = {
    "background": "#f6f6f6",
    "border": "#646464",
    "land": "#fefee9",
    "river": "#0978ab",
    "lake": "#c6ecff",
}
ProjectionCallable = Callable[[ArrayLike, ArrayLike], tuple[ArrayLike, ArrayLike]]


class MapSVG(svg.SVG):
    # TODO: class docstring with Attributes:
    def __init__(
        self,
        bounds: tuple[float, float] | tuple[float, float, float, float],
        height: Optional[int] = None,
        width: Optional[int] = None,
        projection: Optional[ProjectionCallable] = None,
        *args,
        **kwargs,
    ):
        # TODO: set default bounds to (-180, -90, 180, 90)
        """Provide an interface to create SVG files for maps.

        Args:
            bounds: Bounds of the geometry as (lon_min, lat_min, lon_max, lat_max) in
                the domain of the geographical data (longitude and latitude). If only
                (lon_min, lon_max) are given, the same limits are used for lat as well.
            height: Height of the SVG-file in pixels. If None is given, the height is
                automatically determined from the width and the bounds.
            width: Width of the SVG-file in pixels. If None is given, the width is
                automatically determined from the height and the bounds.
            projection: Callable function that projects coordinates from geographical
                coordinates (longitude and latitude). Defaults to mercator projection.
            *args: Arguments passed to svg.SVG.
            **kwargs: Keyword arguments passed to svg.SVG.
        """
        if projection is None:

            projection = Transformer.from_crs(
                "EPSG:4326", "EPSG:3857", always_xy=True
            ).transform
        self.projection = projection

        if len(bounds) == 2:
            lon_min, lon_max = bounds
            lat_min, lat_max = lon_min, lon_max
        else:
            lon_min, lat_min, lon_max, lat_max = bounds
        self.bounds = lon_min, lat_min, lon_max, lat_max

        # pre compute bounds and range in projection
        # bounds
        bounds_proj = projection([lon_min, lon_max], [lat_min, lat_max])
        (x_min, x_max), (y_min, y_max) = np.array(bounds_proj)
        self.bounds_proj = (x_min, y_min, x_max, y_max)

        # range
        x_range, y_range = x_max - x_min, y_max - y_min
        self.range_proj = np.array([x_range, y_range])

        # compute the width and height depending on what is given
        if height is None and width is None:
            raise ValueError("You have to either define the width or height.")
        elif height is None:
            height = round((y_range / x_range) * width)
        elif width is None:
            width = round((x_range / y_range) * height)
        assert width is not None and height is not None
        self.size = np.array([width, height])

        background = svg.Rect(
            x=0,
            y=0,
            width=width,
            height=height,
            fill=COLORS["background"],
            id="background",
        )
        super().__init__(
            width=width, height=height, elements=[background], *args, **kwargs
        )

    def as_str(self) -> str:
        """Get a string SVG representation of the canvas.

        This is a little bit cheeky and a workaround for the svg.SVG.as_string. This
        method creates an SVG-string (xml) from ALL instance attributes - including the
        ones that I set in this __init__, e.g. self.projection. This leads to breaking
        the SVG-files. Therefore, I remove all instance attributes of this class (but
        not the parent class), then use the as_str-method of the parent class, and then
        add the attributes again. This is a little weird, but it works.

        Returns:
            A string representation of the canvas, representing an SVG-xml-file.
        """
        # remove all attributes that this instance has set
        self_attrs = set(vars(self).keys())
        parent_attrs = set(vars(svg.SVG()).keys())
        self_attrs = self_attrs - parent_attrs
        attr_values = {}
        for attr in self_attrs:
            attr_values[attr] = getattr(self, attr)
            delattr(self, attr)
        # get the string representation of the parent class
        str_repr = super().as_str()
        # add all the attributes again
        for key, value in attr_values.items():
            setattr(self, key, value)
        return str_repr

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

    def geom_to_svg(
        self,
        geometry: BaseGeometry,
        geometry_id: str,
        **kwargs,
    ) -> svg.Element:
        """Create an SVG-element from a shapely geometry (from a GeoDataFrame).

        Currently, Polygon, MultiPolygon, LineString and MultiLineString geometries are
        supported. If a single geometry is given, it is created as a single SVG-element.
        If a multi-geometry is given, each geometry in the multi-geometry is added as a
        separate geometry, and all those are grouped together in a group with the given
        geometry_id.

        Args:
            geometry: The geometry to create an SVG-element from. Currently, the
                supported geometries are Polygon, MultiPolygon, LineString,
                MultiLineString.
            geometry_id: Identifier name of the geometry or group of geometries.

        Raises:
            ValueError: If an unsupported geometry type is given.
        """
        if isinstance(geometry, BaseMultipartGeometry):
            first_geom = geometry.geoms[0]
        else:
            first_geom = geometry

        # get the svg elements class
        if isinstance(first_geom, Polygon):
            svg_cls = svg.Polygon
            get_coords = lambda g: g.exterior.coords
        elif isinstance(first_geom, LineString):
            svg_cls = svg.Polyline
            get_coords = lambda g: g.coords
        else:
            raise ValueError(f"Unsupported geometry type: '{geometry.geom_type}'")

        def _create_svg_element(
            geom: BaseGeometry, geom_id: str, **kwargs
        ) -> svg.Element:
            """Use determined class and get_coords function to create SVG-element."""
            points = self._transformation(np.array(get_coords(geom)))
            return svg_cls(points=list(points.flatten()), id=geom_id, **kwargs)

        # create a group for multipart geometry
        if isinstance(geometry, BaseMultipartGeometry):
            svg_elements = [
                _create_svg_element(geom_part, f"{geometry_id}_part_{i}")
                for i, geom_part in enumerate(geometry.geoms)
            ]
            svg_element = svg.G(id=geometry_id, elements=svg_elements, **kwargs)
        # create a single element for single geometry
        else:
            svg_element = _create_svg_element(geometry, geometry_id, **kwargs)

        return svg_element

    def _transformation(
        self,
        coords: NDArray,
    ) -> NDArray:
        """Transform geographical coordinates to SVG coordinates.

        The coordinates should be in geographical representation (longitude and
        latitude). They first get projected, and this projection is then linearly
        transformed to the SVG coordinates.

        Args:
            coords: Coordinate points in geographical representation (longitude and
                latitude) that should be transformed to the SVG-coordinate system.
                Array of shape (n, 2).

        Returns:
            An array with the points of the geometry in SVG coordinates of shape (n, 2).
        """
        # use geographical projection
        xx, yy = self.projection(*coords.T)  # self.projection wants two lists xx and yy
        xx, yy = np.array(xx), np.array(yy)
        # shift to zero
        x_min, y_min, _, _ = self.bounds_proj
        xx, yy = xx - x_min, yy - y_min
        # scale to one
        x_range, y_range = self.range_proj
        xx, yy = xx / x_range, yy / y_range
        # scale to svg size
        xx, yy = xx * self.width, yy * self.height
        # turn upside down
        yy = -yy + self.height
        return np.array([xx, yy]).T

    def add_gdf(
        self, gdf: GeoDataFrame, gdf_id: str, group_id: str | None = None, **kwargs
    ):
        """Add all geometries in a GeoDataFrame to the canvas.

        Args:
            gdf: GeoDataFrame with at least two columns:
                - geometry: shapely geometries with geometrical information.
                - id: identifier of the geometries (e.g. country names)
            gdf_id: For each row, an SVG-element will be created. All these elements
                will be grouped. This parameter determines the SVG group identifier.
            group_id: Identifier of the group to which the created group should be added
                Defaults to None.
        """
        elements = []
        for _, row in gdf.iterrows():
            name = row["id"]
            geom = row.geometry
            svg_element = self.geom_to_svg(
                geometry=geom,
                geometry_id=name,
            )
            elements.append(svg_element)
        self.add(svg.G(id=gdf_id, elements=elements, **kwargs), group_id=group_id)

    def save(self, file_path: str | Path) -> None:
        """Save the SVG file to the given path.

        Args:
            file_path: Path to save the SVG file to.
        """
        path = Path(file_path)
        path.write_text(str(self), encoding="utf-8")


class OrthoMapSVG(MapSVG):
    def __init__(
        self,
        width: Optional[int] = None,
        height: Optional[int] = None,
        center: tuple[float, float] = (0, 0),
        *args,
        **kwargs,
    ):
        """Provide an interface to create SVG with an orthographically projected map.

        Args:
            width: Width of the SVG-file in pixels. If None is given, the width is
                equal to the height. Either width or height have to be given. If the
                width is given, the height parameter is irrelevant.
            height: Height of the SVG-file in pixels. If None is given, the height is
                equal to the width. Either width or height have to be given.
            center: Center of the orthographic projection as (longitude, latitude).
                Defaults to (0, 0).
        """
        if width is not None:
            height = width
        elif height is not None:
            width = height
        self.center = center
        ortho_proj_str = f"+proj=ortho +lat_0={center[1]} +lon_0={center[0]}"
        transformer = Transformer.from_crs("EPSG:4326", ortho_proj_str, always_xy=True)

        super().__init__(
            bounds=(-180, -90, 180, 90),
            height=height,
            width=width,
            projection=transformer.transform,
            *args,
            **kwargs,
        )
        # define the bounds manually; due to orthographic projection, the bounds are
        # infinite and defined for a round globe; however, we need them for a linear
        # scaling of the rectangular svg
        assert transformer.target_crs is not None
        assert transformer.target_crs.ellipsoid is not None
        world_radius = transformer.target_crs.ellipsoid.semi_major_metre
        self.world_radius = world_radius
        self.clipped_scaling = 0.99
        self.bounds_proj = (-world_radius, -world_radius, world_radius, world_radius)
        self.range_proj = np.array([2 * world_radius, 2 * world_radius])
        self.visible_lon_lat = self._get_visible_lon_lat(center)

        self.grad_id = "globeShadowGrad"
        grad = get_radial_shadow_grad(self.grad_id)
        defs = svg.Defs(elements=[grad])
        self.add(defs)

    def geom_to_svg(
        self,
        geometry: BaseGeometry,
        geometry_id: str,
        **kwargs,
    ) -> svg.Element:
        visible_geom = geometry.intersection(self.visible_lon_lat)
        return super().geom_to_svg(visible_geom, geometry_id, **kwargs)

    def _get_visible_lon_lat(self, center: tuple[float, float]) -> BaseGeometry:
        """Get a geometry that determines the visible part in longitude/latitude.

        This shape is not completely straightforward. This function creates a circle in
        the size of the world and projects it from an orthographic space into
        longitude/latitude space. Some additional checks are done to create the final
        approximated shape.

        Args:
            center: Center of the orthographic projection.

        Returns:
            A geometry that shows the part in longitude/latitude that will be visible
            if the orthographic projection with the given center would be applied.
        """
        ortho_proj_str = f"+proj=ortho +lat_0={center[1]} +lon_0={center[0]}"
        inv_transformer = Transformer.from_crs(
            ortho_proj_str, "EPSG:4326", always_xy=True
        )
        # we scale the radius slightly for some error margin
        world_radius = self.world_radius * self.clipped_scaling
        # define points on circle
        t = np.linspace(0, 2 * np.pi, 360)
        x = world_radius * np.cos(t)
        y = world_radius * np.sin(t)
        lon, lat = inv_transformer.transform(x, y)

        # the inverse transformation does not transform points to the boundaries
        # therefore, we have to set the boundaries manually
        # If latitude is larger then 0, the visible part goes to the top (+90°)
        if center[1] > 0:
            boundary = 90  # in deg
        # If latitude is lower then 0, the visible part goes to the top (-90°)
        elif center[1] < 0:
            boundary = -90  # in deg
        else:
            boundary = None
        # change the LATitude value to boundary where lowest and largest LONGitude
        if boundary is not None:
            i_min, i_max = [np.argmin(lon), np.argmax(lon)]
            lat[i_min] = lat[i_max] = boundary
            idx = np.r_[0 : i_min + 1, i_max : len(lat)]
            lon, lat = lon[idx], lat[idx]

        # if the longitude center is between -90 and 90, the shape is a polygon
        if -90 <= center[0] <= 90:
            visible = Polygon(zip(lon, lat))
        # if not, the shape is a multipolygon "clipping over the edge" of the map
        # therefore, we have to create 2 polygons instead of one
        else:
            lon, lat = np.array(lon), np.array(lat)
            mask = lon > 0
            p1 = Polygon(zip(lon[mask], lat[mask]))
            p2 = Polygon(zip(lon[~mask], lat[~mask]))
            visible = MultiPolygon([p1, p2])

        # final check if the geometry is valid; if not, make a single valid geometry
        if not visible.is_valid:
            visible = make_valid(visible)
            if isinstance(visible, GeometryCollection):
                # Keep only polygons
                polygons = [
                    g for g in visible.geoms if isinstance(g, (Polygon, MultiPolygon))
                ]
                visible = unary_union(polygons)
        return visible

    def add_sea(self):
        """Add a blue circle as background for the sea."""
        radius = self.size[0] / 2
        self.add(
            svg.Circle(
                id="sea",
                cx=radius,
                cy=radius,
                r=radius * self.clipped_scaling,
                **self.get_kwargs("sea"),
            )
        )

    def add_shadow(self):
        """Add a radial shadow to the canvas."""
        radius = self.size[0] / 2
        self.add(
            svg.Circle(
                cx=radius,
                cy=radius,
                r=radius * self.clipped_scaling,
                id="globeShadow",
                fill=f"url(#{self.grad_id})",
            )
        )


def get_radial_shadow_grad(identifier: str) -> svg.RadialGradient:
    """Get a radial gradient starting light in the center and getting darker.

    The gradient has to be added to the definitions of the canvas, e.g. with:
    ```python
    grad = svg_handler.get_radial_shadow_grad(identifier)
    defs = svg.Defs(elements=[grad])
    ```

    Then, it can be applied on an element (e.g. a circle) with its identifier:
    ```python
    svg.Circle(fill=f"url(#{identifier})")
    ```

    Args:
        identifier: Name of the radial gradient. This name has to be used to apply the
            gradient to an element.

    Returns:
        A radial gradient, with pre-defined values. In the future, it might be a good
        idea to be able to define these values, but for now this is sufficient.
    """
    grad = svg.RadialGradient(
        id=identifier,
        cx=0.5,
        cy=0.5,
        r=0.5,
        fx=0.5,
        fy=0.5,
        elements=cast(
            list[svg.Element],
            [
                svg.Stop(offset=0, stop_opacity=0, stop_color="black"),
                svg.Stop(offset=1, stop_opacity=0.25, stop_color="black"),
            ],
        ),
    )
    return grad
