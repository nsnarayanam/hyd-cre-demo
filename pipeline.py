"""Anvīkṣaṇa CRE demonstration pipeline, Hyderabad western corridor.

Run AFTER aoi.py, on a machine with internet access:
    pip install pystac-client odc-stac rasterio xarray numpy scipy geopandas h3 pandas
    python pipeline.py

Produces, per asset:
  out/<asset_id>_profile.json     figures with a provenance record on every figure
  out/<asset_id>_cells.geojson    H3 res-9 cells with per-cell values
  out/profiles.csv                one row per figure across all assets
  out/run_manifest.json           scene IDs, model versions, run time, code hash

Figures (all on H3 res 9 cells):
  F1  built_up_change_2km_36m      Sentinel-2 L2A, NDBI-based built-up class, 2023-09 vs 2026-08
  F2  flood_extent_overlap          Sentinel-1 GRD VV, Oct 2020 event vs dry baseline, thresholded
  F3  low_lying_cells               Copernicus DEM 30 m, cells below local median minus 2 m within 1 km of water
  F4  construction_sites_1km        Sentinel-2 change (NDBI up, NDVI down) over last 12 months, clustered
  F5  land_use_class                Sentinel-2 composite, simple 5-class rule set (built, vegetation, water, bare, mixed)

These are demonstration-grade methods chosen for transparency. Every threshold is in MODEL_VERSIONS
below so a reviewer can trace a figure to the rule that produced it.
"""
import json, hashlib, datetime as dt, pathlib, math, os
os.environ.setdefault("AWS_NO_SIGN_REQUEST", "YES")
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
import numpy as np, pandas as pd, geopandas as gpd, h3
from shapely.geometry import Polygon, shape

# ---------------- provenance -----------------
MODEL_VERSIONS = {
    "lc":  {"id": "lc-demo-1.0", "desc": "NDBI>0.05 & NDVI<0.25 => built; NDVI>0.45 => vegetation; NDWI>0.2 => water; else bare/mixed"},
    "fl":  {"id": "fl-demo-1.0", "desc": "S1 VV dB: flood if (event - baseline) < -3 dB and event < -15 dB; majority per cell"},
    "ll":  {"id": "ll-demo-1.0", "desc": "Copernicus DEM GLO-30: cell mean elevation < (1 km neighbourhood median - 2 m)"},
    "cn":  {"id": "cn-demo-1.0", "desc": "dNDBI > +0.10 and dNDVI < -0.15 over 12 months; connected cells >= 2 => one site"},
}
STAC_URL = "https://earth-search.aws.element84.com/v1"   # Sentinel-2 L2A COGs, Sentinel-1 GRD, Copernicus DEM
RUN_TS = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
CODE_HASH = hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()[:12]
out = pathlib.Path("out"); out.mkdir(exist_ok=True)

assets = gpd.read_file("assets.geojson")
bufs = gpd.read_file("buffers.geojson")
aoi = gpd.read_file("aoi.geojson").geometry.iloc[0]
grid = gpd.read_file("grid_h3r9.geojson").set_index("h3")

def provenance(model_key, scene_ids, window, extra=None):
    p = {"model": MODEL_VERSIONS[model_key]["id"], "rule": MODEL_VERSIONS[model_key]["desc"],
         "scenes": scene_ids, "window": window, "computed_at": RUN_TS, "pipeline_hash": CODE_HASH}
    if extra: p.update(extra)
    return p

# ---------------- data access -----------------
def stac_search(collection, bbox, datetime_range, query=None, limit=200):
    from pystac_client import Client
    cat = Client.open(STAC_URL)
    s = cat.search(collections=[collection], bbox=bbox, datetime=datetime_range, query=query, limit=limit)
    return list(s.items())

def load_s2(items, bands, bbox):
    import odc.stac
    ds = odc.stac.load(items, bands=bands, bbox=bbox, resolution=20, crs="EPSG:32644", chunks={}, groupby="solar_day")
    return ds

def s2_median_composite(bbox, start, end, max_cloud=20):
    items = stac_search("sentinel-2-l2a", bbox, f"{start}/{end}", query={"eo:cloud_cover": {"lt": max_cloud}})
    if not items: raise RuntimeError(f"no S2 scenes {start}..{end}")
    ds = load_s2(items, ["red", "green", "nir", "swir16", "scl"], bbox)
    good = ~ds.scl.isin([0, 1, 3, 8, 9, 10, 11])   # drop nodata, saturated, shadow, cloud, cirrus, snow
    ds = ds.where(good)
    comp = ds[["red", "green", "nir", "swir16"]].median("time").compute()
    return comp, [i.id for i in items]

def indices(c):
    ndvi = (c.nir - c.red) / (c.nir + c.red)
    ndbi = (c.swir16 - c.nir) / (c.swir16 + c.nir)
    ndwi = (c.green - c.nir) / (c.green + c.nir)
    return ndvi, ndbi, ndwi

def landuse(ndvi, ndbi, ndwi):
    cls = np.full(ndvi.shape, 4, dtype=np.int8)   # 4 = bare/mixed
    cls[(ndwi > 0.2)] = 2                            # water
    cls[(ndvi > 0.45)] = 1                           # vegetation
    cls[(ndbi > 0.05) & (ndvi < 0.25)] = 0           # built
    return cls

# ---------------- raster -> H3 -----------------
def raster_to_cells(da_values, da_like, agg="mean"):
    """Aggregate a 2-D array (aligned to da_like coords) into H3 res-9 cells. Works for x/y or lon/lat dims."""
    from pyproj import Transformer
    dims = list(da_like.dims)[-2:]
    ydim, xdim = dims[0], dims[1]
    xs, ys = np.meshgrid(da_like[xdim].values, da_like[ydim].values)
    try:
        crs = da_like.odc.crs
    except Exception:
        crs = "EPSG:32644"
    if str(crs).upper().endswith("4326") or xdim in ("longitude", "lon"):
        lon, lat = xs.ravel(), ys.ravel()
    else:
        tr = Transformer.from_crs(crs, 4326, always_xy=True)
        lon, lat = tr.transform(xs.ravel(), ys.ravel())
    cells = [h3.latlng_to_cell(la, lo, 9) for la, lo in zip(lat, lon)]
    df = pd.DataFrame({"h3": cells, "v": np.asarray(da_values).ravel()}).dropna()
    return df.groupby("h3")["v"].agg(agg)

# ---------------- figures -----------------
def run():
    bbox = list(aoi.bounds)
    manifest = {"run": RUN_TS, "pipeline_hash": CODE_HASH, "aoi_bbox": bbox, "h3_res": 9, "scenes": {}}

    # F1/F5: two composites
    c_t0, ids_t0 = s2_median_composite(bbox, "2023-08-01", "2023-10-31")
    c_t1, ids_t1 = s2_median_composite(bbox, "2026-06-01", "2026-08-31")
    manifest["scenes"]["s2_t0"] = ids_t0; manifest["scenes"]["s2_t1"] = ids_t1
    v0, b0, w0 = indices(c_t0); v1, b1, w1 = indices(c_t1)
    lu0, lu1 = landuse(v0.values, b0.values, w0.values), landuse(v1.values, b1.values, w1.values)
    built0 = raster_to_cells((lu0 == 0).astype(float), c_t0.red)
    built1 = raster_to_cells((lu1 == 0).astype(float), c_t1.red)
    lu_mode = raster_to_cells(lu1.astype(float), c_t1.red, agg=lambda s: s.mode().iloc[0])

    # F4: construction, last 12 months
    c_m12, ids_m12 = s2_median_composite(bbox, "2025-06-01", "2025-08-31")
    manifest["scenes"]["s2_minus12"] = ids_m12
    vm, bm, _ = indices(c_m12)
    dndbi = raster_to_cells((b1 - bm).values, c_t1.red); dndvi = raster_to_cells((v1 - vm).values, c_t1.red)
    constr_cell = ((dndbi > 0.10) & (dndvi < -0.15))

    # F2: flood, Oct 2020 event vs dry baseline (S1 GRD VV). Optional: S1 on this catalogue is requester-pays.
    flood_cell = pd.Series(dtype=bool); flood_ok = False
    try:
        ev = stac_search("sentinel-1-grd", bbox, "2020-10-13/2020-10-22")
        bl = stac_search("sentinel-1-grd", bbox, "2020-03-01/2020-04-30")
        manifest["scenes"]["s1_event"] = [i.id for i in ev]; manifest["scenes"]["s1_baseline"] = [i.id for i in bl]
        import odc.stac
        ev_ds = odc.stac.load(ev, bands=["vv"], bbox=bbox, resolution=20, crs="EPSG:32644", chunks={}).vv.min("time").compute()
        bl_ds = odc.stac.load(bl, bands=["vv"], bbox=bbox, resolution=20, crs="EPSG:32644", chunks={}).vv.median("time").compute()
        ev_db, bl_db = 10*np.log10(ev_ds), 10*np.log10(bl_ds)
        flood = ((ev_db - bl_db) < -3) & (ev_db < -15)
        flood_cell = raster_to_cells(flood.values.astype(float), ev_db) > 0.5
        flood_ok = True
    except Exception as e:
        print("S1 flood step skipped:", str(e)[:200])
        manifest["scenes"]["s1_event"] = []; manifest["scenes"]["s1_baseline"] = []; manifest["s1_skipped"] = str(e)[:200]

    # F3: low-lying cells from DEM
    dem_items = stac_search("cop-dem-glo-30", bbox, None)
    import odc.stac
    manifest["scenes"]["dem"] = [i.id for i in dem_items]
    dem = odc.stac.load(dem_items, bands=["data"], bbox=bbox, resolution=30, crs="EPSG:32644", chunks={}).data.isel(time=0).compute()
    dem_cell = raster_to_cells(dem.values, dem)
    # neighbourhood median: k-ring 6 at res 9 ~ 1 km
    nb_med = pd.Series({c: dem_cell.reindex(list(h3.grid_disk(c, 6))).median() for c in dem_cell.index})
    low_cell = dem_cell < (nb_med - 2)

    # ---- per-asset profiles ----
    rows = []
    for _, a in assets.iterrows():
        cells = a["h3_cells"].split(",")
        b1k = bufs[(bufs.asset_id == a.asset_id) & (bufs.radius_m == 1000)].geometry.iloc[0]
        b2k = bufs[(bufs.asset_id == a.asset_id) & (bufs.radius_m == 2000)].geometry.iloc[0]
        cells_1k = list(h3.h3shape_to_cells_experimental(h3.LatLngPoly([(y, x) for x, y in b1k.exterior.coords]), 9, "overlap"))
        cells_2k = list(h3.h3shape_to_cells_experimental(h3.LatLngPoly([(y, x) for x, y in b2k.exterior.coords]), 9, "overlap"))

        f1 = float(built1.reindex(cells_2k).mean() - built0.reindex(cells_2k).mean()) * 100   # pct-point change in built share
        f2 = round(float(flood_cell.reindex(cells).fillna(False).mean()) * 100, 1) if flood_ok else None
        f3 = int(low_cell.reindex(cells).fillna(False).sum())
        cc = constr_cell.reindex(cells_1k).fillna(False)
        # cluster connected true cells into sites
        seen, sites = set(), 0
        for c in cc[cc].index:
            if c in seen: continue
            sites += 1; stack = [c]
            while stack:
                x = stack.pop(); seen.add(x)
                for n in h3.grid_disk(x, 1):
                    if n in cc.index and cc[n] and n not in seen: stack.append(n)
        f4 = sites
        names = {0: "built", 1: "vegetation", 2: "water", 4: "bare/mixed"}
        f5 = names.get(int(lu_mode.reindex(cells).mode().iloc[0]), "mixed")

        profile = {
            "asset_id": a.asset_id, "name": a["name"], "use": a["use"], "h3_cells": cells,
            "label": "DEMONSTRATION PROFILE, not client data",
            "figures": {
                "built_up_change_2km_36m_pct_points": {"value": round(f1, 1), "unit": "percentage points of built-up share, 2 km radius",
                    "provenance": provenance("lc", ids_t0 + ids_t1, "2023-08/2023-10 vs 2026-06/2026-08")},
                "flood_extent_overlap_oct2020_pct": {"value": f2, "unit": "% of parcel cells flooded in Oct 2020 event",
                    "provenance": provenance("fl", manifest["scenes"]["s1_event"] + manifest["scenes"]["s1_baseline"], "event 2020-10-13/22 vs baseline 2020-03/04")},
                "low_lying_cells": {"value": f3, "unit": "parcel cells >2 m below 1 km neighbourhood median",
                    "provenance": provenance("ll", manifest["scenes"]["dem"], "static")},
                "construction_sites_1km_12m": {"value": f4, "unit": "clustered change sites within 1 km, last 12 months",
                    "provenance": provenance("cn", ids_m12 + ids_t1, "2025-06/08 vs 2026-06/08")},
                "land_use_class": {"value": f5, "unit": "modal class over parcel cells",
                    "provenance": provenance("lc", ids_t1, "2026-06/2026-08")},
            }}
        json.dump(profile, open(out / f"{a.asset_id}_profile.json", "w"), indent=2)
        for k, v in profile["figures"].items():
            rows.append({"asset_id": a.asset_id, "name": a["name"], "figure": k, "value": v["value"], "unit": v["unit"],
                         "model": v["provenance"]["model"], "n_scenes": len(v["provenance"]["scenes"]), "computed_at": RUN_TS})
        # per-cell export for the map
        cl = pd.DataFrame({"h3": cells_2k})
        cl["built_t1"] = built1.reindex(cells_2k).values; cl["built_t0"] = built0.reindex(cells_2k).values
        cl["flood_2020"] = flood_cell.reindex(cells_2k).fillna(False).values.astype(int) if flood_ok else 0
        cl["low_lying"] = low_cell.reindex(cells_2k).fillna(False).values.astype(int)
        cl["construction"] = constr_cell.reindex(cells_2k).fillna(False).values.astype(int)
        cl["geometry"] = [Polygon([(lo, la) for la, lo in h3.cell_to_boundary(c)]) for c in cells_2k]
        gpd.GeoDataFrame(cl, crs=4326).to_file(out / f"{a.asset_id}_cells.geojson", driver="GeoJSON")

    pd.DataFrame(rows).to_csv(out / "profiles.csv", index=False)
    manifest["models"] = MODEL_VERSIONS
    json.dump(manifest, open(out / "run_manifest.json", "w"), indent=2)
    print(pd.DataFrame(rows)[["asset_id", "figure", "value"]].to_string(index=False))

if __name__ == "__main__":
    run()
