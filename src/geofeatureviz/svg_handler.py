"""Create scalable vector graphics from geometrical data."""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional, cast
from xml.dom.minidom import parseString

import numpy as np
import svg
from geopandas import GeoDataFrame
from numpy.typing import NDArray
from pyproj import Transformer
from shapely import LineString, MultiPolygon, Polygon
from shapely.affinity import translate
from shapely.coords import CoordinateSequence
from shapely.geometry.base import BaseGeometry, BaseMultipartGeometry
from shapely.ops import split
from svg._types import Length, Number

from geofeatureviz import map_style
from geofeatureviz.projections import Equirectangular, Orthographic, Projection


@dataclass
class MapSVG(svg.SVG):
    """Provide an interface to create SVG files for maps.

    Args:
        bounds: Bounds of the geometry as (lon_min, lat_min, lon_max, lat_max) in
            the domain of the geographical data (longitude and latitude). If only
            (lon_min, lon_max) are given, the same limits are used for lat as well.
        projection: A callable class that projects coordinates from geographical
            coordinates (longitude and latitude). Defaults to equirectangular
            projection (EPSG 32662).
        height: Height of the SVG-file in pixels. If None is given, the height is
            automatically determined from the width and the bounds.
        width: Width of the SVG-file in pixels. If None is given, the width is
            automatically determined from the height and the bounds.

    Attributes:
        bounds: Bounds of the geometry as (lon_min, lat_min, lon_max, lat_max) in the
            domain of the geographical data (longitude and latitude).
        projection: Callable function that projects coordinates from geographical
            coordinates (longitude and latitude).
        bounds_proj: The bounds projected into the space given by the projection.
        range_proj: The range of x- and y-values in the space given by the projection.
    """

    bounds: tuple[float, float] | tuple[float, float, float, float] = (
        -180,
        -90,
        180,
        90,
    )
    projection: Projection = field(default_factory=Equirectangular)

    def __post_init__(
        self,
    ) -> None:
        """Precompute important values for the SVG canvas of a geographical map.

        This includes bounds and ranges in the projection space, and width and height
        of the SVG file.
        """
        if len(self.bounds) == 2:
            lon_min, lon_max = self.bounds[0], self.bounds[1]
            lat_min, lat_max = lon_min, lon_max
        else:
            lon_min, lat_min, lon_max, lat_max = self.bounds
        self.bounds = lon_min, lat_min, lon_max, lat_max

        # pre compute bounds and range in projection
        # bounds
        bounds_proj = self.projection(
            np.array([lon_min, lon_max]), np.array([lat_min, lat_max])
        )
        (x_min, x_max), (y_min, y_max) = np.array(bounds_proj)
        self.bounds_proj: tuple[float, float, float, float] = (
            x_min,
            y_min,
            x_max,
            y_max,
        )

        # range
        x_range, y_range = x_max - x_min, y_max - y_min
        self.range_proj: NDArray[np.float64] = np.array([x_range, y_range])

        # compute the width and height depending on what is given
        if self.height is None and self.width is None:
            raise ValueError("You have to either define the width or height.")
        elif self.height is None:
            self.height = int(round((y_range / x_range) * self.width))
        elif self.width is None:
            self.width = int(round((x_range / y_range) * self.height))
        assert self.width is not None and self.height is not None

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

    def as_pretty_str(self) -> str:
        """Get a pretty string representation of the canvas with indentations etc.

        Returns:
            A pretty string representation of the canvas.
        """
        self_str = self.as_str()
        dom = parseString(self_str)
        pretty_str = dom.toprettyxml(indent="  ")
        return pretty_str

    def add(self, element: svg.Element, group_id: str | None = None) -> None:
        """Add an element to the SVG file.

        Args:
            element: Element to add to the group.
            group_id: The identifier of the group to which the element should be added.
                If None is given, the element is added to the base layer.
        """
        if group_id is None:
            group: svg.Element = self
        else:
            group = self.get_group_by_id(group_id)
        if group.elements is not None:
            group.elements.append(element)
        else:
            group.elements = [element]

    def add_background(self, color: Optional[str] = None) -> None:
        """Add a background (as first element in the list of elements) to the canvas.

        Args:
            color: Background color. Defaults to the background color defined in COLORS.
        """
        if color is None:
            color = map_style.COLORS["background"]
        background = svg.Rect(
            x=0,
            y=0,
            width=self.width,
            height=self.height,
            fill=color,
            id="background",
        )
        if self.elements is None:
            self.elements = []
        self.elements = [background] + self.elements

    def add_def(self, definition: svg.Element) -> None:
        """Add a definition to the canvas Defs.

        Args:
            definition: The definition to add, e.g. a pattern or a gradient.
        """
        if self.elements is None:
            self.elements = []

        # get the first element that is an svg.Defs, else None
        defs = next((e for e in self.elements if isinstance(e, svg.Defs)), None)

        if defs is None:
            self.elements.append(svg.Defs(elements=[definition]))
        else:
            if defs.elements is None:
                defs.elements = [definition]
            else:
                defs.elements.append(svg.Defs(elements=[definition]))

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
        **kwargs: Any,
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
            **kwargs: Additional keyword arguments that are passed to the SVG-element(s)
                that are created.

        Raises:
            ValueError: If an unsupported geometry type is given.
        """
        if isinstance(geometry, BaseMultipartGeometry):
            first_geom = geometry.geoms[0]
        else:
            first_geom = geometry

        # get the svg elements class
        if isinstance(first_geom, Polygon):
            svg_cls: type[svg.Polygon] | type[svg.Polyline] = svg.Polygon

            def _get_coords(g: BaseGeometry) -> CoordinateSequence:
                g = cast(Polygon, g)
                return g.exterior.coords

        elif isinstance(first_geom, LineString):
            svg_cls = svg.Polyline

            def _get_coords(g: BaseGeometry) -> CoordinateSequence:
                return g.coords

        else:
            raise ValueError(f"Unsupported geometry type: '{geometry.geom_type}'")

        def _create_svg_element(
            geom: BaseGeometry, geom_id: str, **kwargs: Any
        ) -> svg.Element:
            """Use determined class and get_coords function to create SVG-element."""
            points = self._transformation(np.array(_get_coords(geom)))
            return svg_cls(points=list(points.flatten()), id=geom_id, **kwargs)

        # create a group for multipart geometry
        if isinstance(geometry, BaseMultipartGeometry):
            svg_elements = [
                _create_svg_element(geom_part, f"{geometry_id}_part_{i}")
                for i, geom_part in enumerate(geometry.geoms)
            ]
            return Group(id=geometry_id, elements=svg_elements, **kwargs)
        # create a single element for single geometry
        else:
            return _create_svg_element(geometry, geometry_id, **kwargs)

    def _transformation(
        self,
        coords: NDArray[np.float64],
    ) -> NDArray[np.float64]:
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
        self,
        gdf: GeoDataFrame,
        gdf_id: str,
        group_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Add all geometries in a GeoDataFrame to the canvas.

        Args:
            gdf: GeoDataFrame with at least two columns:
                - geometry: shapely geometries with geometrical information.
                - id: identifier of the geometries (e.g. country names)
            gdf_id: For each row, an SVG-element will be created. All these elements
                can be grouped. This parameter determines the SVG group identifier. If
                None is given, all elements are added to the group given by 'group_id'.
                Note that the kwargs are only relevant if a gdf_id is given.
            group_id: Identifier of the group to which the created group should be
                added. If None is given, it is added to the canvas directly.
                Defaults to None.
            **kwargs: Additional keyword arguments that are passed to the Group-element.
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
        if gdf_id is None:
            for elem in elements:
                self.add(elem, group_id=group_id)
        else:
            self.add(Group(id=gdf_id, elements=elements, **kwargs), group_id=group_id)

    def save(
        self, file_path: str | Path, pretty: bool = True, optimize: bool = False
    ) -> None:
        """Save the SVG file to the given path.

        Args:
            file_path: Path to save the SVG file to.
            pretty: Whether the output file should be pretty (with indentations etc.) or
                not. Default is True.
            optimize: Whether the output file should be optimized using svgo. Default is
                False.
        """
        if pretty:
            self_str = self.as_pretty_str()
        else:
            self_str = self.as_str()
        path = Path(file_path)
        path.write_text(self_str, encoding="utf-8")
        if optimize:
            # optimize saved svg
            subprocess.run(
                [
                    "svgo",
                    str(path),
                    "-o",
                    str(path),
                ]
            )

    def copy(self) -> MapSVG:
        """Copy this MapSVG instance."""
        from copy import deepcopy

        return deepcopy(self)


@dataclass
class OrthoMapSVG(MapSVG):
    """Provide an SVG canvas for maps with an orthographic projection.

    Args:
        center: Center of the orthographic projection as (longitude, latitude).
            Default is (0, 0).
        width: Width of the SVG-file in pixels. If None is given, the width is
            equal to the height. Either width or height have to be given. If the
            width is given, the height parameter is irrelevant.
        height: Height of the SVG-file in pixels. If None is given, the height is
            equal to the width. Either width or height have to be given.

    Attributes:
        center: Center of the orthographic projection as (longitude, latitude).
        world_radius: Radius of the world (in meters).
        clipped_scaling: During the orthographic projection, we scale the coordinates so
            that they are slightly smaller than the maximum value, so that we do not run
            into infinity projections. This is slightly hacky, but it works fine. Should
            be set to a value close to but smaller than one. Default is 0.99.
        visible_lon_lat: A geometry that determines the visible part of the map in
            longitude/latitude.
    """

    center: tuple[float, float] = (0, 0)

    def __post_init__(self) -> None:
        """Provide an interface to create SVG with an orthographically projected map."""
        if self.height is None and self.width is None:
            raise ValueError("You have to either define the width or height.")
        elif self.width is not None:
            self.height = self.width
        elif self.height is not None:
            self.width = self.height

        assert self.width is not None
        if isinstance(self.width, Length):
            diameter = self.width.value
        else:
            diameter = self.width
        self.radius: float = float(diameter) / 2

        projection = Orthographic(center=self.center)
        self.projection = projection
        world_radius = projection.world_radius
        self.world_radius = world_radius

        # define the bounds manually; due to orthographic projection, the bounds are
        # infinite and defined for a round globe; however, we need them for a linear
        # scaling of the rectangular svg
        self.bounds = (-180, -90, 180, 90)
        self.clipped_scaling = 0.99
        self.bounds_proj = (-world_radius, -world_radius, world_radius, world_radius)
        self.range_proj = np.array([2 * world_radius, 2 * world_radius])
        self.visible_lon_lat = self._create_visible_lon_lat()

    def geom_to_svg(
        self,
        geometry: BaseGeometry,
        geometry_id: str,
        **kwargs: Any,
    ) -> svg.Element:
        """Create an SVG-element from a shapely geometry (from a GeoDataFrame)."""
        visible_geom = geometry.intersection(self.visible_lon_lat)
        return super().geom_to_svg(visible_geom, geometry_id, **kwargs)

    def _create_visible_lon_lat(self) -> BaseGeometry:
        """Get a geometry that determines the visible part in longitude/latitude.

        This shape is not completely straightforward. This function creates a circle in
        the size of the world and projects it from an orthographic space into
        longitude/latitude space. Some additional checks are done to create the final
        approximated shape.

        Returns:
            A geometry that shows the part in longitude/latitude that will be visible
            if the orthographic projection with the given center would be applied.
        """
        # scale the radius slightly for some error margin
        world_radius = self.world_radius * self.clipped_scaling
        # define points on circle
        n_values = 720
        t = np.linspace(0, 2 * np.pi, n_values)
        x = world_radius * np.cos(t)
        y = world_radius * np.sin(t)
        # project from orthographic to lon/lat, pretend that the center is at lon=0
        ortho_proj_str = f"+proj=ortho +lat_0={self.center[1]} +lon_0={0}"
        inv_transformer = Transformer.from_crs(
            ortho_proj_str, "EPSG:4326", always_xy=True
        )
        lon, lat = inv_transformer.transform(x, y)
        lon, lat = np.array(lon), np.array(lat)
        polygon: BaseGeometry = Polygon(zip(lon, lat))

        idx_lon_min, idx_lon_max = lon.argmin(), lon.argmax()

        # due to projection, values are not projected to left/right border
        lon_margin = 3.6
        if lon.min() < (-180 + lon_margin):
            lon[idx_lon_min] = -180
        if lon.max() > (180 - lon_margin):
            lon[idx_lon_max] = 180

        # The inverse transformation does not transform points to the boundaries.
        # Therefore, we have to set the boundaries manually using a created rectangle.
        boundary_rect = self._get_boundary_rect(lon, lat)
        polygon = Polygon(zip(lon, lat)).union(boundary_rect)
        assert isinstance(polygon, Polygon)

        if self.center[0] != 0:
            polygon = self._shift_polygon(polygon, shift=self.center[0])

        return polygon

    def _get_boundary_rect(
        self, lon: NDArray[np.float64], lat: NDArray[np.float64]
    ) -> Polygon:
        """Get a rectangle that goes to the boundaries of the map fitting lon and lat.

        Args:
            lon: Longitudes of a shape that should go to the boundaries.
            lat: Latitudes of a shape that should go to the boundaries.

        Returns:
            A polygon, which is a rectangle that goes from the largest lon, to the
            smallest lon to the border.
        """
        idx_lon_min, idx_lon_max = lon.argmin(), lon.argmax()
        # If latitude is larger then 0, the visible part goes to the top (+90°)
        if self.center[1] > 0:
            boundary_points = [
                (lon[idx_lon_min], np.floor(lat[idx_lon_min])),
                (lon[idx_lon_max], np.floor(lat[idx_lon_max])),
                (lon[idx_lon_max], 90),
                (lon[idx_lon_min], 90),
            ]
        # If latitude is lower then 0, the visible part goes to the top (-90°)
        elif self.center[1] < 0:
            boundary_points = [
                (lon[idx_lon_min], np.ceil(lat[idx_lon_min])),
                (lon[idx_lon_max], np.ceil(lat[idx_lon_max])),
                (lon[idx_lon_max], -90),
                (lon[idx_lon_min], -90),
            ]
        # if lat is 0, the visible part is a simple rectangle
        else:
            boundary_points = [
                (lon[idx_lon_min], 90),
                (lon[idx_lon_max], 90),
                (lon[idx_lon_max], -90),
                (lon[idx_lon_min], -90),
            ]
        return Polygon(boundary_points)

    def _shift_polygon(
        self, polygon: Polygon, shift: float, limit: float = 180
    ) -> BaseGeometry:
        """Shift a polygon on the x-axis while wrapping to a min and max of (-)180°.

        Args:
            polygon: The polygon that should be shifted.
            shift: How far the polygon should be shifted.
            limit: The limit where the polygon has to be wrapped.

        Returns:
            Either a single polygon or a multipolygon.
            Single polygon:
            - if the shifted polygon does not does not exceed the limits
            - if the shifted polygon "touches" itself after wrapping
            Multipolygon:
            - if the shifted polygon has to be wrapped and does not "touch" itself
        """
        if shift > 0:
            direction = 1

            def check_wrap(coords: NDArray[np.float64]) -> np.bool_:
                return np.max(coords) > limit

        elif shift < 0:
            direction = -1

            def check_wrap(coords: NDArray[np.float64]) -> np.bool_:
                return np.min(coords) < limit

        else:
            return polygon
        limit = direction * limit
        offset = -2 * limit

        # shift by longitude center
        shifted: BaseGeometry = translate(polygon, xoff=shift)

        # split; create a multipolygon to ensure that all parts are polygons
        dateline = LineString([(limit, -91), (limit, 91)])
        split_parts = MultiPolygon(split(shifted, dateline))
        if len(split_parts.geoms) > 1:
            # determine which polygon has to be wrapped
            if check_wrap(np.array(split_parts.geoms[0].exterior.coords).T[0]):
                idx_orig, idx_wrapped = 1, 0
            else:
                idx_orig, idx_wrapped = 0, 1
            orig, wrapped = split_parts.geoms[idx_orig], split_parts.geoms[idx_wrapped]
            # move wrapped to the other side
            wrapped = translate(wrapped, xoff=offset)
            # merge if they touch
            if wrapped.touches(orig):
                shifted = wrapped.union(orig)
            else:
                shifted = MultiPolygon([orig, wrapped])
        return shifted

    def add_sea(self) -> None:
        """Add a blue circle as background for the sea."""
        radius = self.radius
        self.add(
            svg.Circle(
                id="sea",
                cx=radius,
                cy=radius,
                r=radius * self.clipped_scaling,
                **map_style.STYLES["sea"],
            )
        )

    def add_shadow(self, identifier: str) -> None:
        """Add a radial shadow to the canvas.

        Args:
            identifier: ID of the SVG-element that is added to the canvas.
        """
        grad_id = f"{identifier}Grad"
        self.add_def(RadialShadowGrad(id=grad_id))

        radius = self.radius
        self.add(
            svg.Circle(
                cx=radius,
                cy=radius,
                r=radius * self.clipped_scaling,
                id=identifier,
                fill=f"url(#{grad_id})",
                opacity=0.3,
            )
        )


@dataclass
class RadialShadowGrad(svg.RadialGradient):
    """Provide a radial shadow gradient for SVG.

    This is mainly a wrapper for svg.RadialGradient that sets some default attributes
    of the parent class, especially a black opaque radial gradient, with the opacity
    becoming higher towards the edges following a Lambertian reflectance.

    Args:
        n_colors: Number of colors in the gradient. Default is 10.
    """

    # set different defaults compared to parent class
    element_name = "radialGradient"
    cx: Length | Number | None = 0.5
    cy: Length | Number | None = 0.5
    r: Length | Number | None = 0.5
    fr: Length | Number | None = None
    fx: Length | Number | None = 0.5
    fy: Length | Number | None = 0.5

    elements: list[svg.Element] | None = None

    n_colors: int = 10

    def __post_init__(self) -> None:
        """Precompute the elements of the radial shadow gradient with the Lambertian."""
        if self.elements is None:
            offsets = np.round(np.linspace(0, 1, self.n_colors), 3)
            lambertian = 1 - np.sqrt(1 - offsets**2)

            self.elements = [
                svg.Stop(offset=off, stop_opacity=op, stop_color="black")
                for off, op in zip(offsets, lambertian)
            ]


@dataclass
class DiagonalStripedPattern(svg.Pattern):
    """Provide a diagonal striped pattern for SVG elements.

    This is mainly a wrapper for svg.Pattern that sets some default attributes
    of the parent class.

    Args:
        stripe_colors: The two colors that alternate in the striped pattern. Defaults to
            black and white.
        stripe_width: The width of the alternating stripes. Defaults to (1, 1).
        stripe_height: The height of the alternating stripes. Defaults to 8.
        patternTransform: Transformation of the pattern. Defaults to a 45° rotation.
        patternUnits: Units of the pattern. Defaults to "userSpaceOnUse".
        elements: Elements of the pattern. Defaults to two rectangles with the
            given colors.
    """

    stripe_colors: tuple[str, str] = ("black", "white")
    stripe_width: tuple[int, int] = (1, 1)
    stripe_height: int = 8
    patternTransform: Optional[list[svg.Transform]] = None
    patternUnits: Optional[Literal["userSpaceOnUse", "objectBoundingBox"]] = (
        "userSpaceOnUse"
    )
    elements: Optional[list[svg.Element]] = None

    def __post_init__(self) -> None:
        """Initialize a diagonally striped pattern."""
        if self.patternTransform is None:
            self.patternTransform = [svg.Rotate(45)]
        max_width = sum(self.stripe_width)
        self.width = max_width
        self.height = self.stripe_height
        if self.elements is None:
            self.elements = [
                svg.Rect(
                    width=max_width,
                    height=self.stripe_height,
                    fill=self.stripe_colors[1],
                ),  # background
                svg.Rect(
                    width=self.stripe_width[0],
                    height=self.stripe_height,
                    fill=self.stripe_colors[0],
                ),
            ]


@dataclass
class Group(svg.G):
    """Provide an SVG-element for groups with additional arguments.

    In the implementation of pysvg, groups can not take arguments that are specific for
    a special type (e.g. for lines only). However, it is actually possible in SVG to
    define these arguments in groups. Therefore, I created this class, with the only
    purpose to add additional arguments.

    Args:
        stroke_linejoin: How points of a line are joined. Defaults to None.
        stroke_linecap: How lines are ended. Defaults to None.
    """

    stroke_linejoin: Literal["butt", "round", "square", "inherit"] | None = None
    stroke_linecap: Literal["butt", "round", "square", "inherit"] | None = None
