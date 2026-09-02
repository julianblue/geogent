"""The agent's tool registry.

geogent is an **agricultural raster analyst**: the surface is deliberately
narrow — field/parcel lookup, imagery discovery, single-scene and seasonal index
analytics, multi-date per-pixel reductions, and the UI actions that put those on
the map. General-purpose routing/isochrone tooling was removed (the backend
endpoints remain) so tool selection stays sharp on the ag workflows.
"""

from geogent_agent.tools.frontend_actions import (
    add_aggregation_layer,
    add_buffer_layer,
    confirm_feature_save,
    fly_to,
    list_features_in_viewport,
    render_dashboard,
    show_sentinel2_scene,
    show_temporal_layer,
)
from geogent_agent.tools.geo_tools import (
    analyze_index_season,
    area_of,
    buffer_geometry,
    crop_stats_within_bbox,
    distance_between,
    features_within,
    fields_within_bbox,
    geometries_intersect,
    list_features,
    list_fields,
    seasonal_index_time_series_for_field,
    temporal_features,
    zonal_stats_for_field,
)
from geogent_agent.tools.osm_tools import geocode_place
from geogent_agent.tools.stac_tools import (
    stac_get_item,
    stac_list_collections,
    stac_search,
)

TOOLS = [
    # --- fields & parcels -------------------------------------------------
    list_fields,
    fields_within_bbox,
    crop_stats_within_bbox,
    # --- raster analytics (one date -> a season -> per pixel) -------------
    zonal_stats_for_field,
    seasonal_index_time_series_for_field,
    analyze_index_season,
    temporal_features,
    # --- imagery discovery ------------------------------------------------
    stac_list_collections,
    stac_search,
    stac_get_item,
    # --- vector analytics -------------------------------------------------
    list_features,
    buffer_geometry,
    distance_between,
    area_of,
    geometries_intersect,
    features_within,
    # --- place lookup -----------------------------------------------------
    geocode_place,
    # --- UI actions -------------------------------------------------------
    fly_to,
    add_buffer_layer,
    add_aggregation_layer,
    list_features_in_viewport,
    confirm_feature_save,
    show_sentinel2_scene,
    show_temporal_layer,
    render_dashboard,
]

__all__ = [
    "TOOLS",
    "add_aggregation_layer",
    "add_buffer_layer",
    "analyze_index_season",
    "area_of",
    "buffer_geometry",
    "confirm_feature_save",
    "crop_stats_within_bbox",
    "distance_between",
    "features_within",
    "fields_within_bbox",
    "fly_to",
    "geocode_place",
    "geometries_intersect",
    "list_features",
    "list_features_in_viewport",
    "list_fields",
    "render_dashboard",
    "seasonal_index_time_series_for_field",
    "show_sentinel2_scene",
    "show_temporal_layer",
    "stac_get_item",
    "stac_list_collections",
    "stac_search",
    "temporal_features",
    "zonal_stats_for_field",
]
