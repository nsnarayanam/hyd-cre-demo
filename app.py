import json, pathlib
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="Anvīkṣaṇa CRE demo, Hyderabad", layout="wide")

OUT = pathlib.Path("out")
NAVY, GOLD = "#1B2A4A", "#C9962E"

st.markdown(
    f"<h2 style='color:{NAVY};margin-bottom:0'>Anvīkṣaṇa for Commercial Real Estate</h2>"
    f"<p style='color:#6B7280;margin-top:2px'>Hyderabad western corridor. Demonstration profiles on open Sentinel and Copernicus data, not client data. "
    f"Every figure carries its source scenes, model version and run time.</p>", unsafe_allow_html=True)

if not (OUT / "profiles.csv").exists():
    st.warning("No results yet. The GitHub Actions run writes out/profiles.csv into this repository when it finishes.")
    st.stop()

prof = pd.read_csv(OUT / "profiles.csv")
manifest = json.load(open(OUT / "run_manifest.json"))
assets = sorted(prof.asset_id.unique())
profiles = {a: json.load(open(OUT / f"{a}_profile.json")) for a in assets}

# ---------- portfolio strip ----------
c1, c2, c3, c4 = st.columns(4)
def pick(a, fig):
    r = prof[(prof.asset_id == a) & (prof.figure == fig)]
    if not len(r): return None
    v = pd.to_numeric(r.value.iloc[0], errors="coerce")
    return None if pd.isna(v) else float(v)
built = [pick(a, "built_up_change_2km_36m_pct_points") for a in assets]
constr = [pick(a, "construction_sites_1km_12m") for a in assets]
low = [pick(a, "low_lying_cells") for a in assets]
c1.metric("Assets profiled", len(assets))
c2.metric("Highest built-up change, 2 km, 36 months", f"{max(v for v in built if v is not None):.1f} pp")
c3.metric("Construction sites within 1 km, total", int(sum(v for v in constr if v is not None)))
c4.metric("Assets with low-lying cells", int(sum(1 for v in low if v)))

left, right = st.columns([3, 2])

# ---------- map ----------
with left:
    sel = st.selectbox("Asset", assets, format_func=lambda a: f"{a}  {profiles[a]['name']}")
    layer_choice = st.radio("Layer", ["Built-up share 2026", "Built-up change", "Construction (12 months)", "Low-lying cells"], horizontal=True)
    cells = json.load(open(OUT / f"{sel}_cells.geojson"))
    for f in cells["features"]:
        p = f["properties"]
        b1 = p.get("built_t1") or 0.0; b0 = p.get("built_t0") or 0.0
        if layer_choice == "Built-up share 2026":
            v = b1
        elif layer_choice == "Built-up change":
            v = max(0.0, b1 - b0) * 2
        elif layer_choice.startswith("Construction"):
            v = float(p.get("construction") or 0)
        else:
            v = float(p.get("low_lying") or 0)
        v = max(0.0, min(1.0, v))
        p["fill"] = [201, 150, 46, int(30 + 200 * v)]
        p["line"] = [27, 42, 74, 90]
    parcel_cells = set(profiles[sel]["h3_cells"])
    for f in cells["features"]:
        if f["properties"]["h3"] in parcel_cells:
            f["properties"]["line"] = [27, 42, 74, 255]
    xs = [c[0] for f in cells["features"] for c in f["geometry"]["coordinates"][0]]
    ys = [c[1] for f in cells["features"] for c in f["geometry"]["coordinates"][0]]
    m = folium.Map(location=[sum(ys) / len(ys), sum(xs) / len(xs)], zoom_start=14, tiles="OpenStreetMap", control_scale=True)
    def style(f):
        p = f["properties"]
        r, g, b, a = p["fill"]; lr, lg, lb, la = p["line"]
        return {"fillColor": f"#{r:02x}{g:02x}{b:02x}", "fillOpacity": a / 255, "color": f"#{lr:02x}{lg:02x}{lb:02x}", "weight": 2 if la == 255 else 0.6, "opacity": la / 255}
    folium.GeoJson(cells, style_function=style,
                   tooltip=folium.GeoJsonTooltip(fields=["h3", "built_t1", "built_t0", "construction", "low_lying"],
                                                 aliases=["cell", "built 2026", "built 2023", "construction", "low-lying"], localize=True)).add_to(m)
    folium.TileLayer("CartoDB positron", name="Light").add_to(m)
    folium.LayerControl().add_to(m)
    st_folium(m, width=None, height=520, returned_objects=[])
    st.caption("H3 resolution 9 cells, 2 km around the asset. Dark outline: parcel cells. Gold intensity: selected layer.")

# ---------- asset panel ----------
with right:
    pr = profiles[sel]
    st.markdown(f"<h4 style='color:{NAVY};margin-bottom:0'>{pr['name']}</h4><p style='color:#6B7280'>{pr['use']}</p>", unsafe_allow_html=True)
    labels = {
        "built_up_change_2km_36m_pct_points": "Built-up change, 2 km, 36 months",
        "flood_extent_overlap_oct2020_pct": "Flood extent overlap, Oct 2020",
        "low_lying_cells": "Low-lying parcel cells",
        "construction_sites_1km_12m": "Construction sites, 1 km, 12 months",
        "land_use_class": "Land-use class, 2026",
    }
    units = {"built_up_change_2km_36m_pct_points": " pp", "flood_extent_overlap_oct2020_pct": " %"}
    for k, fig in pr["figures"].items():
        v = fig["value"]
        shown = "not computed" if v is None else f"{v}{units.get(k, '')}"
        pv = fig["provenance"]
        st.markdown(
            f"<div style='border:1px solid #D9DEE7;border-radius:6px;padding:8px 12px;margin-bottom:8px;background:#F7F8FB'>"
            f"<div style='display:flex;justify-content:space-between'><span>{labels.get(k, k)}</span>"
            f"<b style='color:{NAVY}'>{shown}</b></div>"
            f"<div style='font-size:11px;color:{GOLD}'>{pv['model']} · {len(pv['scenes'])} scenes · {pv['window']} · {pv['computed_at'][:16]}Z</div>"
            f"</div>", unsafe_allow_html=True)
    with st.expander("Provenance detail for this asset"):
        for k, fig in pr["figures"].items():
            st.markdown(f"**{labels.get(k, k)}**  \nRule: {fig['provenance']['rule']}  \nPipeline hash: `{fig['provenance']['pipeline_hash']}`")
            st.code("\n".join(fig["provenance"]["scenes"][:12]) + ("\n..." if len(fig["provenance"]["scenes"]) > 12 else ""), language="text")
    if manifest.get("s1_skipped"):
        st.info("Sentinel-1 flood step was skipped in this run (requester-pays archive). Flood overlap shows as not computed.")

st.divider()
st.caption(f"Run {manifest['run']}  ·  pipeline {manifest['pipeline_hash']}  ·  AOI {manifest['aoi_bbox']}  ·  Aganitha Space Technologies Pvt. Ltd., Hyderabad")
