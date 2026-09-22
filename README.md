# Hyderabad western corridor, CRE demonstration run

AOI: 17.40 to 17.47 N, 78.32 to 78.40 E. H3 resolution 9 (614 cells).
Four demonstration assets: HYD-001 Financial District, HYD-002 Khajaguda lake edge,
HYD-003 HITEC City, HYD-004 Kondapur. Parcels are 240 m squares around the centroid;
replace with real outlines in aoi.py ASSETS if you have them.

## Run

    pip install pystac-client odc-stac rasterio xarray numpy scipy pandas geopandas h3 pyproj
    python aoi.py        # already run; regenerates aoi/assets/grid/buffers geojson
    python pipeline.py   # needs internet: Earth Search STAC (Sentinel-2 L2A, Sentinel-1 GRD, Copernicus DEM)

Runtime: roughly 10 to 25 minutes depending on bandwidth. All data is open; no keys needed.

## Outputs (out/)

- <asset>_profile.json: five figures, each with model id, rule text, scene IDs, window, run time, pipeline hash
- <asset>_cells.geojson: 2 km of cells around each asset with built_t0, built_t1, flood_2020, low_lying, construction
- profiles.csv: one row per figure, all assets
- run_manifest.json: every scene ID used, every model version, the code hash

## What to load in the demo

Portfolio view: all four *_cells.geojson layers, colour flood_2020 gold, construction amber outline,
low_lying hatched. Asset panel: the five figures from profiles.csv with the provenance line under each.
Label the screen "Demonstration profiles, Hyderabad, not client data".

## Known limits (say these if asked)

- Land-use and flood rules are simple index thresholds, chosen so a reviewer can read them.
  Production models replace them; the provenance record format does not change.
- Sentinel-1 Oct 2020 coverage over Hyderabad is two to three passes; the flood layer is the union.
- No HMDA zoning overlay yet; add hmda_zoning.geojson to the folder and join on cells to get
  the "built on non-built zoning" figure.
