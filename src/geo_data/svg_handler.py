"""Create scalable vector graphics from geometrical data."""

from pathlib import Path
from typing import Callable, Optional
from xml.dom.minidom import parseString

import numpy as np
import svg
from geopandas import GeoDataFrame
from numpy.typing import ArrayLike, NDArray
from pyproj import Transformer
from shapely import LineString, MultiPolygon, Polygon
from shapely.affinity import translate
from shapely.geometry.base import BaseGeometry, BaseMultipartGeometry
from shapely.ops import split

from geo_data.projections import Equirectangular, Orthographic, Projection

COLORS = {
    "background": "#f6f6f6",
    "border": "#646464",
    "land": "#fefee9",
    "river": "#0978ab",
    "lake": "#c6ecff",
    "highlight": "#c12737",
}
LAND_KWARGS = {
    "fill": COLORS["land"],
    "stroke": COLORS["border"],
    "stroke_width": 1,
}
RIVER_KWARGS = {"style": "fill:none", "stroke": COLORS["river"], "stroke_width": 1}
LAKE_KWARGS = {
    "fill": COLORS["lake"],
    "stroke": COLORS["river"],
    "stroke_width": 1,
}
SEA_KWARGS = {"fill": COLORS["lake"]}


class MapSVG(svg.SVG):
    """Provide an interface to create SVG files for maps.

    Attributes:
        bounds: Bounds of the geometry as (lon_min, lat_min, lon_max, lat_max) in the
            domain of the geographical data (longitude and latitude).
        projection: Callable function that projects coordinates from geographical
            coordinates (longitude and latitude).
        bounds_proj: The bounds projected into the space given by the projection.
        range_proj: The range of x- and y-values in the space given by the projection.
    """

    def __init__(
        self,
        bounds: Optional[
            tuple[float, float] | tuple[float, float, float, float]
        ] = None,
        height: Optional[int] = None,
        width: Optional[int] = None,
        projection: Optional[Projection] = None,
        *args,
        **kwargs,
    ):
        """Initialize an interface to create SVG files for maps.

        Args:
            bounds: Bounds of the geometry as (lon_min, lat_min, lon_max, lat_max) in
                the domain of the geographical data (longitude and latitude). If only
                (lon_min, lon_max) are given, the same limits are used for lat as well.
            height: Height of the SVG-file in pixels. If None is given, the height is
                automatically determined from the width and the bounds.
            width: Width of the SVG-file in pixels. If None is given, the width is
                automatically determined from the height and the bounds.
            projection: A callable class that projects coordinates from geographical
                coordinates (longitude and latitude). Defaults to equirectangular
                projection (EPSG 32662).
            *args: Arguments passed to svg.SVG.
            **kwargs: Keyword arguments passed to svg.SVG.
        """
        if projection is None:
            projection = Equirectangular()
        self.projection: Projection = projection

        if bounds is None:
            bounds = (-180, -90, 180, 90)
        if len(bounds) == 2:
            lon_min, lon_max = bounds
            lat_min, lat_max = lon_min, lon_max
        else:
            lon_min, lat_min, lon_max, lat_max = bounds
        self.bounds: tuple[float, float, float, float] = (
            lon_min,
            lat_min,
            lon_max,
            lat_max,
        )

        # pre compute bounds and range in projection
        # bounds
        bounds_proj = projection(
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
        self.range_proj: NDArray = np.array([x_range, y_range])

        # compute the width and height depending on what is given
        if height is None and width is None:
            raise ValueError("You have to either define the width or height.")
        elif height is None:
            height = round((y_range / x_range) * width)
        elif width is None:
            width = round((x_range / y_range) * height)
        assert width is not None and height is not None
        self.size = np.array([width, height])

        super().__init__(width=width, height=height, elements=[], *args, **kwargs)

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

    def as_pretty_str(self):
        """Get a pretty string representation of the canvas with indentations etc.

        Returns:
            A pretty string representation of the canvas.
        """
        self_str = self.as_str()
        dom = parseString(self_str)
        pretty_str = dom.toprettyxml(indent="  ")
        return pretty_str

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
            return LAND_KWARGS
        elif kind == "river":
            return RIVER_KWARGS
        elif kind == "lake":
            return LAKE_KWARGS
        elif kind == "sea":
            return SEA_KWARGS
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

    def add_background(self, color: Optional[str] = None):
        """Add a background (as first element in the list of elements) to the canvas.

        Args:
            color: Background color. Defaults to the background color defined in COLORS.
        """
        if color is None:
            color = COLORS["background"]
        width, height = self.size
        background = svg.Rect(
            x=0,
            y=0,
            width=width,
            height=height,
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
                can be grouped. This parameter determines the SVG group identifier. If
                None is given, all elements are added to the group given by 'group_id'.
                Note that the kwargs are only relevant if a gdf_id is given.
            group_id: Identifier of the group to which the created group should be
                added. If None is given, it is added to the canvas directly.
                Defaults toNone.
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
            self.add(svg.G(id=gdf_id, elements=elements, **kwargs), group_id=group_id)

    def save(self, file_path: str | Path, pretty: bool = True) -> None:
        """Save the SVG file to the given path.

        Args:
            file_path: Path to save the SVG file to.
            pretty: Whether the output file should be pretty (with indentations etc.) or
                not. Default is True.
        """
        if pretty:
            self_str = self.as_pretty_str()
        else:
            self_str = self.as_str()
        path = Path(file_path)
        path.write_text(self_str, encoding="utf-8")


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
        projection = Orthographic(center=center)

        super().__init__(
            bounds=(-180, -90, 180, 90),
            height=height,
            width=width,
            projection=projection,
            *args,
            **kwargs,
        )
        # define the bounds manually; due to orthographic projection, the bounds are
        # infinite and defined for a round globe; however, we need them for a linear
        # scaling of the rectangular svg
        world_radius = projection.world_radius
        self.world_radius = world_radius
        self.clipped_scaling = 0.99
        self.bounds_proj = (-world_radius, -world_radius, world_radius, world_radius)
        self.range_proj = np.array([2 * world_radius, 2 * world_radius])
        self.visible_lon_lat = self._create_visible_lon_lat()

        self.grad_id = "globeShadowGrad"
        self.add_def(RadialShadowGrad(id=self.grad_id))

    def geom_to_svg(
        self,
        geometry: BaseGeometry,
        geometry_id: str,
        **kwargs,
    ) -> svg.Element:
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
        polygon = Polygon(zip(lon, lat))

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

    def _get_boundary_rect(self, lon: NDArray, lat: NDArray) -> Polygon:
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
            check_wrap = lambda coords: np.max(coords) > limit
        elif shift < 0:
            direction = -1
            check_wrap = lambda coords: np.min(coords) < limit
        else:
            return polygon
        limit = direction * limit
        offset = -2 * limit

        # shift by longitude center
        shifted = translate(polygon, xoff=shift)

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


class RadialShadowGrad(svg.RadialGradient):
    def __init__(self, **kwargs):
        """Initialize a radial gradient for a globe shadow."""
        default_kwargs = {
            "cx": 0.5,
            "cy": 0.5,
            "r": 0.5,
            "fx": 0.5,
            "fy": 0.5,
            "elements": [
                svg.Stop(offset=0, stop_opacity=0, stop_color="black"),
                svg.Stop(offset=1, stop_opacity=0.25, stop_color="black"),
            ],
        }
        default_kwargs.update(kwargs)
        super().__init__(**default_kwargs)


class DiagonalStripedPattern(svg.Pattern):
    def __init__(self, color: tuple[str, str] = ("black", "white"), **kwargs):
        """Initialize a diagonally striped pattern.

        Args:
            color: The two colors that alternate in the striped pattern. Defaults to
                black and white.
        """
        default_kwargs = {
            "width": 8,
            "height": 8,
            "patternTransform": "rotate(45)",
            "patternUnits": "userSpaceOnUse",
            "elements": [
                svg.Rect(width=8, height=8, fill=color[1]),  # background
                svg.Rect(width=4, height=8, fill=color[0]),
            ],
        }
        default_kwargs.update(kwargs)
        super().__init__(**default_kwargs)
