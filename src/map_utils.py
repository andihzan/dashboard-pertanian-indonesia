"""Indonesia choropleth map helpers."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.express as px

ROOT = Path(__file__).resolve().parents[1]
GEO_PATH = ROOT / "data" / "geo" / "indonesia_provinces_38.geojson"

# Map GeoJSON PROVINSI property to canonical province name
GEO_TO_CANONICAL = {
    "Daerah Istimewa Yogyakarta": "DI Yogyakarta",
    # Others match directly
}


_geojson_cache: dict | None = None


def load_geojson() -> dict:
    """Load Indonesia 38-province GeoJSON (cached)."""
    global _geojson_cache
    if _geojson_cache is None:
        with open(GEO_PATH) as f:
            geo = json.load(f)
        # Add "id" property = canonical province name for plotly matching
        for feat in geo["features"]:
            raw_name = feat["properties"]["PROVINSI"]
            canonical = GEO_TO_CANONICAL.get(raw_name, raw_name)
            feat["id"] = canonical
        _geojson_cache = geo
    return _geojson_cache


def make_choropleth(df: pd.DataFrame, value_col: str, title: str,
                     color_scale: str = "Greens",
                     value_label: str | None = None,
                     height: int = 500):
    """Create choropleth of Indonesia by province.

    df must have columns ['provinsi', value_col].
    """
    geo = load_geojson()
    fig = px.choropleth_mapbox(
        df,
        geojson=geo,
        locations="provinsi",
        color=value_col,
        featureidkey="id",
        center={"lat": -2.5, "lon": 118},
        mapbox_style="carto-positron",
        zoom=3.4,
        opacity=0.75,
        color_continuous_scale=color_scale,
        title=title,
        labels={value_col: value_label or value_col},
        hover_data={value_col: ":,.1f"},
    )
    fig.update_layout(
        height=height,
        margin={"l": 0, "r": 0, "t": 40, "b": 0},
    )
    return fig
