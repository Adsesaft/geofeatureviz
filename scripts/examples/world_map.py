"""Create a map of the world."""

from geofeatureviz.io import path_settings
from geofeatureviz.rendering import COLORS, MapSVG
from geofeatureviz_scripts import loader

# load preprocessed countries and simplify the geometries
countries = loader.load_and_prep_data(
    feature="country",
    source="ne",
    resolution=110,
)
countries.geometry = countries.geometry.simplify(tolerance=0.2, preserve_topology=True)

# create a canvas to draw a map to
canvas = MapSVG(width=600, height=400)

# add a background covering the whole canvas, defaults to a blue ocean color
canvas.add_background(COLORS["lake"])

# draw countries in the GeoDataFrame to the map
canvas.add_gdf(countries, "Countries", fill=COLORS["land"], stroke=COLORS["border"])

# save the svg file
canvas.save(path_settings.results_dir / "examples" / "world_map.svg", optimize=True)
