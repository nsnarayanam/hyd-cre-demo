import json, pathlib
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="Anvīkṣaṇa CRE", layout="wide")

NAVY, GOLD, INK, MUTED, LINE, TINT = "#1B2A4A", "#C9962E", "#222831", "#6B7280", "#D9DEE7", "#F7F8FB"
GREEN, AMBER, RED = "#2E7D32", "#C9962E", "#B3261E"
OUT = pathlib.Path("out")

st.markdown(f"""
<style>
.block-container {{padding-top: 1.2rem;}}
h1,h2,h3,h4 {{color:{NAVY};}}
.kpi {{border:1px solid {LINE}; border-radius:8px; padding:14px 16px; background:{TINT};}}
.kpi .l {{font-size:12px; color:{MUTED};}}
.kpi .v {{font-size:28px; font-weight:700; color:{NAVY}; line-height:1.1;}}
.kpi .s {{font-size:12px; color:{MUTED};}}
.card {{border:1px solid {LINE}; border-radius:8px; padding:12px 14px; margin-bottom:10px; background:white;}}
.card .t {{font-size:13px; color:{MUTED};}}
.card .n {{font-size:22px; font-weight:700; color:{NAVY};}}
.card .m {{font-size:13px; color:{INK}; margin-top:4px;}}
.card .p {{font-size:11px; color:{GOLD}; margin-top:6px;}}
.chip {{display:inline-block; padding:2px 10px; border-radius:12px; font-size:12px; font-weight:600; color:white;}}
.banner {{border-radius:8px; padding:14px 18px; color:white; margin-bottom:12px;}}
.memo {{border-left:4px solid {GOLD}; background:{TINT}; padding:12px 16px; border-radius:6px; font-size:14px; line-height:1.55;}}
</style>""", unsafe_allow_html=True)

if not (OUT / "profiles.csv").exists():
    st.warning("No results yet. The pipeline writes out/ into this repository when it finishes.")
    st.stop()

manifest = json.load(open(OUT / "run_manifest.json"))
prof = pd.read_csv(OUT / "profiles.csv")
assets = sorted(prof.asset_id.unique())
P = {a: json.load(open(OUT / f"{a}_profile.json")) for a in assets}

def fig(a, k):
    return P[a]["figures"][k]["value"]

def num(v):
    try:
        return float(v)
    except Exception:
        return None

def grade_momentum(growth, constr):
    g = num(growth) or 0; c = num(constr) or 0
    score = g + 3 * c
    if score >= 14: return "High", RED, "Rapid build-out; supply and pricing can move fast"
    if score >= 6: return "Medium", AMBER, "Steady development around the site"
    return "Low", GREEN, "Mature, stable surroundings"

def grade_physical(low, flood):
    l = num(low) or 0; f = num(flood) or 0
    if f > 0 or l >= 2: return "Elevated", RED, "Low-lying ground or recorded flooding on the parcel; ask for drainage and insurance detail"
    if l == 1: return "Watch", AMBER, "One low-lying cell on the parcel; check site levels"
    return "Low", GREEN, "No low-lying ground or flood record on the parcel"

def chip(text, color):
    return f"<span class='chip' style='background:{color}'>{text}</span>"

LABELS = {
    "built_up_change_2km_36m_pct_points": ("Built-up growth nearby", "How much the built-up area within 2 km grew over the last 3 years, in percentage points.", " pp"),
    "construction_sites_1km_12m": ("Active construction sites", "Clusters of new construction within 1 km in the last 12 months, detected from imagery change.", ""),
    "low_lying_cells": ("Low-lying ground on parcel", "Grid cells on the parcel sitting more than 2 m below the surrounding 1 km. Water collects here first.", " cells"),
    "flood_extent_overlap_oct2020_pct": ("Flood record, Oct 2020", "Share of the parcel that radar showed under water during the October 2020 Hyderabad floods.", " %"),
    "land_use_class": ("Dominant land cover", "What the parcel looks like from satellite today: built, vegetation, water, or bare/mixed.", ""),
}
ORDER = ["built_up_change_2km_36m_pct_points", "construction_sites_1km_12m", "flood_extent_overlap_oct2020_pct", "low_lying_cells", "land_use_class"]

def memo_text(a):
    p = P[a]; f = p["figures"]
    g = num(f["built_up_change_2km_36m_pct_points"]["value"]) or 0; c = num(f["construction_sites_1km_12m"]["value"]) or 0
    l = num(f["low_lying_cells"]["value"]) or 0; fl = f["flood_extent_overlap_oct2020_pct"]["value"]; lu = f["land_use_class"]["value"]
    s = [f"{p['name']} sits in an area where built-up cover grew {g:.1f} percentage points over the past 36 months [1],"]
    s.append(f"with {int(c)} active construction cluster{'s' if c != 1 else ''} within 1 km in the last year [2]." if c else "with no new construction cluster detected within 1 km in the last year [2].")
    if fl is None: s.append("Flood exposure could not be computed in this run [3].")
    elif num(fl) > 0: s.append(f"Radar shows {num(fl):.0f}% of the parcel under water during the October 2020 event [3].")
    else: s.append("Radar shows no part of the parcel under water during the October 2020 event [3].")
    s.append(("No low-lying cells sit" if not l else f"{int(l)} low-lying cell{'s' if l > 1 else ''} sit{'s' if l == 1 else ''}") + " on the parcel relative to the surrounding 1 km [4].")
    s.append(f"Dominant land cover today is {lu} [5].")
    return " ".join(s)

def cite_list(a):
    f = P[a]["figures"]; out = []
    for i, k in enumerate(ORDER, 1):
        pv = f[k]["provenance"]
        out.append(f"[{i}] {pv['model']}, {len(pv['scenes'])} scene{'s' if len(pv['scenes']) != 1 else ''}, {pv['window']}, computed {pv['computed_at'][:16]}Z")
    return out

def rows_all():
    rows = []
    for a in assets:
        g = fig(a, "built_up_change_2km_36m_pct_points"); c = fig(a, "construction_sites_1km_12m")
        l = fig(a, "low_lying_cells"); fl = fig(a, "flood_extent_overlap_oct2020_pct")
        rows.append(dict(asset=a, name=P[a]["name"], use=P[a]["use"], growth=g, constr=c, low=l, flood=fl,
                         mom=grade_momentum(g, c), phys=grade_physical(l, fl)))
    return rows

with st.sidebar:
    if pathlib.Path("logo.png").exists():
        st.image("logo.png", width=150)
    st.markdown(f"<h3 style='margin-bottom:0'>Anvīkṣaṇa</h3><div style='color:{MUTED};font-size:13px'>Location intelligence for CRE underwriting</div>", unsafe_allow_html=True)
    st.markdown("---")
    view = st.radio("View", ["Portfolio", "Asset profile", "Audit trail", "How it works"], label_visibility="collapsed")
    st.markdown("---")
    st.caption("Hyderabad western corridor demo. Open Sentinel and Copernicus data. Demonstration parcels, not client data.")
    st.caption(f"Run {manifest['run'][:16]}Z · pipeline {manifest['pipeline_hash']}")

if view == "Portfolio":
    st.markdown("## Portfolio overview")
    st.markdown(f"<div style='color:{MUTED}'>Four demonstration assets in Hyderabad's western office corridor. Grades are read straight from satellite-derived figures; the Audit trail view shows the source behind every number.</div>", unsafe_allow_html=True)
    rows = rows_all()
    k1, k2, k3, k4 = st.columns(4)
    n_phys = sum(1 for r in rows if r["phys"][0] != "Low")
    top = max(rows, key=lambda r: num(r["growth"]) or 0)
    tot_c = int(sum(num(r["constr"]) or 0 for r in rows))
    k1.markdown(f"<div class='kpi'><div class='l'>Assets profiled</div><div class='v'>{len(rows)}</div><div class='s'>Hyderabad, 174 m hexagon grid</div></div>", unsafe_allow_html=True)
    k2.markdown(f"<div class='kpi'><div class='l'>Physical risk flagged</div><div class='v'>{n_phys} of {len(rows)}</div><div class='s'>low-lying ground or flood record</div></div>", unsafe_allow_html=True)
    k3.markdown(f"<div class='kpi'><div class='l'>Fastest-growing surroundings</div><div class='v'>{num(top['growth']):.1f} pp</div><div class='s'>{top['name']}</div></div>", unsafe_allow_html=True)
    k4.markdown(f"<div class='kpi'><div class='l'>Construction sites nearby</div><div class='v'>{tot_c}</div><div class='s'>within 1 km, last 12 months, all assets</div></div>", unsafe_allow_html=True)
    st.markdown("&nbsp;", unsafe_allow_html=True)
    mcol, tcol = st.columns([1.1, 1])
    with mcol:
        m = folium.Map(location=[17.437, 78.36], zoom_start=12, tiles="OpenStreetMap", control_scale=True)
        for r in rows:
            cells = json.load(open(OUT / f"{r['asset']}_cells.geojson"))
            parcel = set(P[r["asset"]]["h3_cells"]); col = r["phys"][1]
            for f in cells["features"]:
                if f["properties"]["h3"] in parcel:
                    folium.GeoJson(f, style_function=lambda x, col=col: {"fillColor": col, "fillOpacity": 0.55, "color": col, "weight": 2},
                                   tooltip=f"{r['asset']} {r['name']}: physical risk {r['phys'][0]}, momentum {r['mom'][0]}").add_to(m)
        st_folium(m, width=None, height=440, returned_objects=[])
        st.caption("Parcel colour is the physical-risk grade: green low, amber watch, red elevated.")
    with tcol:
        html = f"<table style='width:100%;border-collapse:collapse;font-size:13px'><tr style='background:{NAVY};color:white'><th style='text-align:left;padding:8px'>Asset</th><th style='padding:8px'>Growth 3y</th><th style='padding:8px'>Sites 1 km</th><th style='padding:8px'>Physical risk</th><th style='padding:8px'>Momentum</th></tr>"
        for i, r in enumerate(rows):
            bg = TINT if i % 2 else "white"
            html += f"<tr style='background:{bg}'><td style='padding:8px'><b>{r['asset']}</b><br><span style='color:{MUTED}'>{r['name']}</span></td>"
            html += f"<td style='text-align:center;padding:8px'>{num(r['growth']):.1f} pp</td><td style='text-align:center;padding:8px'>{int(num(r['constr']) or 0)}</td>"
            html += f"<td style='text-align:center;padding:8px'>{chip(r['phys'][0], r['phys'][1])}</td><td style='text-align:center;padding:8px'>{chip(r['mom'][0], r['mom'][1])}</td></tr>"
        html += "</table>"
        st.markdown(html, unsafe_allow_html=True)
        st.markdown(f"<div style='font-size:12px;color:{MUTED};margin-top:8px'>Growth: built-up share change within 2 km over 36 months. Sites: construction clusters within 1 km over 12 months. Physical risk: low-lying ground and 2020 flood record on the parcel. Momentum: growth plus construction activity.</div>", unsafe_allow_html=True)

elif view == "Asset profile":
    a = st.selectbox("Asset", assets, format_func=lambda x: f"{x}  ·  {P[x]['name']}")
    p = P[a]
    g = fig(a, "built_up_change_2km_36m_pct_points"); c = fig(a, "construction_sites_1km_12m")
    l = fig(a, "low_lying_cells"); fl = fig(a, "flood_extent_overlap_oct2020_pct")
    mm = grade_momentum(g, c); pr = grade_physical(l, fl)
    st.markdown(f"## {p['name']}")
    st.markdown(f"<div style='color:{MUTED};margin-top:-8px'>{p['use']} · {a} · demonstration parcel</div>", unsafe_allow_html=True)
    b1, b2 = st.columns(2)
    b1.markdown(f"<div class='banner' style='background:{pr[1]}'><div style='font-size:12px;opacity:.85'>PHYSICAL RISK</div><div style='font-size:22px;font-weight:700'>{pr[0]}</div><div style='font-size:13px'>{pr[2]}</div></div>", unsafe_allow_html=True)
    b2.markdown(f"<div class='banner' style='background:{mm[1]}'><div style='font-size:12px;opacity:.85'>MARKET MOMENTUM</div><div style='font-size:22px;font-weight:700'>{mm[0]}</div><div style='font-size:13px'>{mm[2]}</div></div>", unsafe_allow_html=True)
    left, right = st.columns([1.15, 1])
    with left:
        layer = st.radio("Show on map", ["Built-up today", "Growth since 2023", "New construction", "Low-lying ground"], horizontal=True, label_visibility="collapsed")
        cells = json.load(open(OUT / f"{a}_cells.geojson"))
        parcel = set(p["h3_cells"])
        def val(pp):
            b1_ = pp.get("built_t1") or 0.0; b0_ = pp.get("built_t0") or 0.0
            if layer == "Built-up today": return b1_
            if layer == "Growth since 2023": return min(1.0, max(0.0, b1_ - b0_) * 2.5)
            if layer == "New construction": return float(pp.get("construction") or 0)
            return float(pp.get("low_lying") or 0)
        xs = [cc[0] for f in cells["features"] for cc in f["geometry"]["coordinates"][0]]
        ys = [cc[1] for f in cells["features"] for cc in f["geometry"]["coordinates"][0]]
        m = folium.Map(location=[sum(ys) / len(ys), sum(xs) / len(xs)], zoom_start=14, tiles="OpenStreetMap", control_scale=True)
        def style(f):
            v = max(0.0, min(1.0, val(f["properties"])))
            on_parcel = f["properties"]["h3"] in parcel
            return {"fillColor": GOLD, "fillOpacity": 0.08 + 0.72 * v, "color": NAVY if on_parcel else "#8A94A6", "weight": 2.5 if on_parcel else 0.5}
        folium.GeoJson(cells, style_function=style,
                       tooltip=folium.GeoJsonTooltip(fields=["built_t1", "built_t0", "construction", "low_lying"],
                                                     aliases=["Built-up share 2026", "Built-up share 2023", "Construction flag", "Low-lying flag"], localize=True)).add_to(m)
        st_folium(m, width=None, height=470, returned_objects=[])
        st.caption("Dark outline: the parcel. Gold intensity: the selected layer, per 174 m hexagon. Hover for values.")
    with right:
        st.markdown("#### What the satellite shows")
        for i, k in enumerate(ORDER, 1):
            f = p["figures"][k]; t, meaning, unit = LABELS[k]; v = f["value"]
            if v is None: shown = "not computed"
            elif k == "built_up_change_2km_36m_pct_points": shown = f"{num(v):.1f}{unit}"
            elif k == "flood_extent_overlap_oct2020_pct": shown = f"{num(v):.0f}{unit}"
            elif k in ("low_lying_cells", "construction_sites_1km_12m"): shown = f"{int(num(v))}{unit}"
            else: shown = f"{v}"
            pv = f["provenance"]
            st.markdown(f"<div class='card'><div style='display:flex;justify-content:space-between;align-items:baseline'><span class='t'>{t}</span><span class='n'>{shown}</span></div>"
                        f"<div class='m'>{meaning}</div><div class='p'>[{i}] {pv['model']} · {len(pv['scenes'])} satellite scene{'s' if len(pv['scenes']) != 1 else ''} · {pv['window']}</div></div>", unsafe_allow_html=True)
    st.markdown("#### Draft memo paragraph")
    st.markdown(f"<div class='memo'>{memo_text(a)}</div>", unsafe_allow_html=True)
    st.markdown(f"<div style='font-size:12px;color:{MUTED};margin-top:6px'>" + "<br>".join(cite_list(a)) + "</div>", unsafe_allow_html=True)
    st.download_button("Download this profile (JSON, full provenance)", data=json.dumps(p, indent=2), file_name=f"{a}_profile.json", mime="application/json")

elif view == "Audit trail":
    st.markdown("## Audit trail")
    st.markdown(f"<div style='color:{MUTED}'>Every figure traces to named satellite scenes, a versioned rule, and a timestamped run. This is what a credit reviewer or auditor sees.</div>", unsafe_allow_html=True)
    a = st.selectbox("Asset", assets, format_func=lambda x: f"{x}  ·  {P[x]['name']}")
    for k in ORDER:
        f = P[a]["figures"][k]; t = LABELS[k][0]; pv = f["provenance"]
        with st.expander(f"{t}: {f['value']}"):
            st.markdown(f"**Rule applied** ({pv['model']}): {pv['rule']}")
            st.markdown(f"**Time window**: {pv['window']}  \n**Computed at**: {pv['computed_at']}  \n**Pipeline hash**: `{pv['pipeline_hash']}`")
            st.markdown(f"**Source scenes** ({len(pv['scenes'])}):")
            st.code("\n".join(pv["scenes"]) if pv["scenes"] else "(none)", language="text")
    st.markdown("#### Run manifest")
    st.json({k: v for k, v in manifest.items() if k != "scenes"})
    st.download_button("Download run manifest", data=json.dumps(manifest, indent=2), file_name="run_manifest.json", mime="application/json")

else:
    st.markdown("## How it works")
    st.markdown(f"""
<div style='max-width:820px;font-size:15px;line-height:1.6'>
<p><b>What you are looking at.</b> Four commercial parcels in Hyderabad's western corridor, each described by five figures computed from open satellite data: how fast the surroundings are building up, how much construction is active nearby, whether the ground is low-lying, whether the parcel flooded in October 2020, and what the land cover is today.</p>
<p><b>Where the numbers come from.</b> Sentinel-2 optical imagery (10 to 20 m) for built-up cover, change and construction; Sentinel-1 radar for the 2020 flood extent; the Copernicus 30 m elevation model for low-lying ground. Everything is indexed on a fixed hexagonal grid (H3 resolution 9, about 174 m across) so any parcel can be compared with any other, on any deal, at any time.</p>
<p><b>Why the grades.</b> {chip("Low", GREEN)} {chip("Watch / Medium", AMBER)} {chip("Elevated / High", RED)} are simple, published thresholds on those figures. They are meant to be read and argued with, not trusted blindly. The Audit trail view shows the exact rule and the exact scenes behind every number.</p>
<p><b>What this is not.</b> A demonstration build on open data with simple rules. Production deployments use the client's own parcel outlines, commercial imagery where licensed, and calibrated models. The provenance record format does not change.</p>
<p><b>Who built it.</b> Aganitha Space Technologies Pvt. Ltd., Hyderabad. ISO 27001 certified. Member of the OGC and the IEEE P4011 geospatial standards working group.</p>
</div>""", unsafe_allow_html=True)
