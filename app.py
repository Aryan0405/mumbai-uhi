import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

GEOJSON_PATH = Path(__file__).resolve().parent / "data" / "app" / "cells_app_r2.geojson"

VIEWS = ["Zone map", "Index map", "Month view", "Cell detail"]

INDEX_VARIANTS = [
    "Primary (0.4 H + 0.4 S + 0.2 E)",
    "No exposure (0.5 H + 0.5 S)",
]


@st.cache_data
def load_data():
    gj = json.loads(GEOJSON_PATH.read_text(encoding="utf-8"))
    df = pd.DataFrame([f["properties"] for f in gj["features"]])
    # CRS84 lon/lat already; do not reproject.
    df["cell_id"] = df["cell_id"].astype(str)
    return gj, df


gj, df = load_data()

# Zone category computed exactly as stored; never recomputed.
df["zone_category"] = "Outside zone"
df.loc[df["zone_fragile"].astype(int) == 1, "zone_category"] = "Fragile zone"
df.loc[df["zone_robust"].astype(int) == 1, "zone_category"] = "Robust zone"

zone_counts = {
    "Robust zone": int(df["zone_robust"].astype(int).sum()),
    "Fragile zone": int(df["zone_fragile"].astype(int).sum()),
    "Outside zone": int((df["zone_primary"].astype(int) == 0).sum()),
}
df["zone_label"] = df["zone_category"].map(
    lambda c: f"{c} ({zone_counts[c]})"
)

# Month class label: null cells are outside the primary zone.
df["month_label"] = df["month_class"].fillna("Not in primary zone")

# Round floats for display only; zone flags / ranks / indices stay full precision.
for col in ["lst_mean", "ndvi_mean", "ndbi_mean", "pop_density_land",
            "index_primary", "index_noexp"]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce").round(3)

HOVER_FIELDS = [
    "lst_mean", "ndvi_mean", "ndbi_mean", "pop", "pop_density_land",
    "index_primary", "rank_primary", "thin_obs", "zone_category",
]

# Plain-word labels for tooltips, legends and colourbars.
LABELS = {
    "lst_mean": "LST (C)",
    "ndvi_mean": "NDVI",
    "ndbi_mean": "NDBI",
    "pop": "Population",
    "pop_density_land": "Pop density (per km2)",
    "index_primary": "Index (primary)",
    "index_noexp": "Index (no exposure)",
    "rank_primary": "Rank (primary)",
    "thin_obs": "Thin observations",
    "zone_category": "Zone",
    "zone_label": "Zone legend",
    "month_label": "Month class",
}

ZONE_COLORS = {
    f"Robust zone ({zone_counts['Robust zone']})": "#8B0000",
    f"Fragile zone ({zone_counts['Fragile zone']})": "#FF8C00",
    f"Outside zone ({zone_counts['Outside zone']})": "#D3D3D3",
}

MONTH_COLORS = {
    "BOTH": "#1f77b4",
    "ONLY_MARCH": "#ff7f0e",
    "ONLY_APRMAY": "#2ca02c",
    "NEITHER": "#d62728",
    "Not in primary zone": "#D3D3D3",
}

CENTER = {"lat": 19.07, "lon": 72.88}


def base_map(df_in, color_col, color_discrete_map=None,
             color_continuous_scale=None, range_color=None):
    hover_data = {f: True for f in HOVER_FIELDS}
    # Hide the active colour column from the hover rows on the Zone map only.
    if color_col == "zone_label":
        hover_data[color_col] = False
    fig = px.choropleth_map(
        df_in,
        geojson=gj,
        locations="cell_id",
        featureidkey="properties.cell_id",
        color=color_col,
        map_style="carto-positron",
        center=CENTER,
        zoom=10,
        opacity=0.75,
        color_discrete_map=color_discrete_map,
        color_continuous_scale=color_continuous_scale,
        range_color=range_color,
        hover_name="cell_id",
        hover_data=hover_data,
        labels=LABELS,
    )
    # Grid outlines.
    fig.update_traces(marker_line_width=0.3, marker_line_color="rgba(90,90,90,0.5)")
    # Legend and colourbar titles read from the labels; the Zone map legend
    # title is set explicitly so it still reads "Zone".
    color_label = LABELS.get(color_col, color_col)
    if color_col == "zone_label":
        color_label = "Zone"
    if color_discrete_map is not None:
        fig.update_layout(legend_title_text=color_label)
    else:
        fig.update_layout(coloraxis_colorbar=dict(title=color_label))
    return fig


st.sidebar.radio("View", key="view", options=VIEWS)
view = st.session_state["view"]

if view == "Cell detail":
    cell_ids = sorted(df["cell_id"].unique())
    pick = st.selectbox("Cell", key="cell_pick", options=cell_ids)
    props = None
    for f in gj["features"]:
        if str(f["properties"].get("cell_id")) == pick:
            props = f["properties"]
            break
    if props is not None:
        rows = []
        for k, v in props.items():
            if k in ("zone_category", "zone_label", "month_label"):
                continue
            if k == "month_class" and v is None:
                v = "Not in primary zone"
            s = str(v)
            rows.append({"Property": str(k), "Value": s})
        table = pd.DataFrame(rows, columns=["Property", "Value"])
        st.table(table)
else:
    if view == "Zone map":
        fig = base_map(
            df,
            color_col="zone_label",
            color_discrete_map=ZONE_COLORS,
        )
    elif view == "Index map":
        st.sidebar.radio("Index variant", key="index_variant",
                         options=INDEX_VARIANTS)
        variant = st.session_state["index_variant"]
        color_col = "index_primary" if variant.startswith("Primary") else "index_noexp"
        cmin = float(df[color_col].min())
        cmax = float(df[color_col].max())
        fig = base_map(
            df,
            color_col=color_col,
            color_continuous_scale="Viridis",
            range_color=[cmin, cmax],
        )
    elif view == "Month view":
        fig = base_map(
            df,
            color_col="month_label",
            color_discrete_map=MONTH_COLORS,
        )
    st.plotly_chart(fig, width="stretch")

# Honesty panel on every view.
with st.expander("How to read this map", expanded=True):
    st.markdown("Hazard and exposure map, not a vulnerability map. There is no social or income data. S is land cover only.")
    st.markdown("LST is land surface temperature from Landsat, not air temperature.")
    st.markdown("The composite uses a few clear days (24 effective dates, March heavy). April-May is about 2.1 C warmer than March.")
    st.markdown("Landsat thermal data is natively 100 m. Cells are 500 m. Population is WorldPop 2020.")
    st.markdown("The zone is the top 180 cells (about 10 percent of 1794 core cells) by an index. Weights are judgment calls, and the zone is a threshold, not a natural class.")
    st.markdown("Robust means in the zone under all five exposure weight schemes. Fragile means in the zone under only some of them.")
    st.markdown("thin_obs cells have fewer clear observations and sit in one eastern band.")
    st.markdown("Shown values are rounded. Zone flags come from full precision data.")
    if view == "Zone map":
        st.markdown("The zone with no exposure and the zone with 50 percent exposure overlap only weakly (Jaccard 0.423).")
    elif view == "Index map":
        st.markdown("H and S correlate at 0.825, so the index is largely one heat and built-up axis.")
    elif view == "Month view":
        st.markdown("S and E are held at all-date values and each month's LST is standardised separately. This says nothing about S or E stability across months, or about seasons outside March to May.")
