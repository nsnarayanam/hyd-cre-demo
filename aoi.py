"""Build the Hyderabad western-corridor AOI, the four demonstration assets, and the H3 grid.
Outputs: aoi.geojson, assets.geojson, grid_h3r9.geojson, buffers.geojson
"""
import json, h3
from shapely.geometry import Polygon, Point, shape, mapping
from shapely.ops import unary_union
import geopandas as gpd

AOI_BBOX = dict(west=78.32, south=17.40, east=78.40, north=17.47)
H3_RES = 9  # ~0.1 km2 cells, ~174 m edge

ASSETS = [
    dict(asset_id="HYD-001", name="Financial District, Nanakramguda", lat=17.418, lon=78.340,
         use="Grade A office cluster", note="Expect high built-up change and active construction"),
    dict(asset_id="HYD-002", name="Khajaguda lake edge", lat=17.425, lon=78.355,
         use="Office and mixed-use near notified lake", note="Expect flood-extent overlap, FTL buffer"),
    dict(asset_id="HYD-003", name="HITEC City, Madhapur", lat=17.447, lon=78.378,
         use="Mature office district", note="Expect low change, low risk; the control asset"),
    dict(asset_id="HYD-004", name="Kondapur, Botanical Garden road", lat=17.463, lon=78.360,
         use="Mixed-use, residential-led", note="Expect land-use change vs zoning, dense construction"),
]
PARCEL_HALF_SIDE_M = 120  # demonstration parcel ~ 240 m square (~5.8 ha); replace with real outlines

def sq(lat, lon, half_m):
    dlat = half_m / 111_320
    dlon = half_m / (111_320 * __import__("math").cos(__import__("math").radians(lat)))
    return Polygon([(lon-dlon, lat-dlat), (lon+dlon, lat-dlat), (lon+dlon, lat+dlat), (lon-dlon, lat+dlat)])

aoi = Polygon([(AOI_BBOX["west"], AOI_BBOX["south"]), (AOI_BBOX["east"], AOI_BBOX["south"]),
               (AOI_BBOX["east"], AOI_BBOX["north"]), (AOI_BBOX["west"], AOI_BBOX["north"])])
gpd.GeoDataFrame([{"name": "Hyderabad western corridor"}], geometry=[aoi], crs=4326).to_file("aoi.geojson", driver="GeoJSON")

rows, bufs = [], []
for a in ASSETS:
    parcel = sq(a["lat"], a["lon"], PARCEL_HALF_SIDE_M)
    cells = list(h3.h3shape_to_cells_experimental(h3.LatLngPoly([(y, x) for x, y in parcel.exterior.coords]), H3_RES, "overlap"))
    rows.append({**a, "h3_cells": ",".join(cells), "n_cells": len(cells), "geometry": parcel})
    # analysis buffers: 1 km (construction) and 2 km (built-up change)
    g = gpd.GeoSeries([Point(a["lon"], a["lat"])], crs=4326).to_crs(32644)
    for r in (1000, 2000):
        bufs.append({"asset_id": a["asset_id"], "radius_m": r, "geometry": g.buffer(r).to_crs(4326).iloc[0]})
gpd.GeoDataFrame(rows, crs=4326).to_file("assets.geojson", driver="GeoJSON")
gpd.GeoDataFrame(bufs, crs=4326).to_file("buffers.geojson", driver="GeoJSON")

# full AOI grid
cells = h3.geo_to_cells(h3.LatLngPoly([(y, x) for x, y in aoi.exterior.coords]), H3_RES)
feats = [{"h3": c, "geometry": Polygon([(lon, lat) for lat, lon in h3.cell_to_boundary(c)])} for c in cells]
gpd.GeoDataFrame(feats, crs=4326).to_file("grid_h3r9.geojson", driver="GeoJSON")
print(f"AOI cells at res {H3_RES}: {len(cells)}")
for r in rows: print(r["asset_id"], r["name"], "cells:", r["n_cells"])
