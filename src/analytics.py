"""Analytics functions: CAGR, korelasi kredit-ekspor, dll."""
from __future__ import annotations

import numpy as np
import pandas as pd


def compute_cagr(df: pd.DataFrame, value_col: str,
                  start_year: int, end_year: int,
                  group_col: str = "provinsi") -> pd.DataFrame:
    """Compute CAGR per group between start_year and end_year.

    CAGR = (end/start)^(1/n) - 1
    """
    sub = df[df["tahun"].isin([start_year, end_year])]
    pivot = sub.pivot_table(index=group_col, columns="tahun", values=value_col, aggfunc="sum")
    if start_year not in pivot.columns or end_year not in pivot.columns:
        return pd.DataFrame()
    pivot = pivot.dropna(subset=[start_year, end_year])
    n = end_year - start_year
    pivot["start"] = pivot[start_year]
    pivot["end"] = pivot[end_year]
    valid = (pivot["start"] > 0) & (pivot["end"] > 0)
    pivot = pivot[valid].copy()
    if pivot.empty:
        return pd.DataFrame()
    pivot["cagr_pct"] = ((pivot["end"] / pivot["start"]) ** (1 / n) - 1) * 100
    pivot = pivot.reset_index()[[group_col, "start", "end", "cagr_pct"]]
    pivot = pivot.sort_values("cagr_pct", ascending=False)
    return pivot


def compute_correlation(kredit: pd.DataFrame, ekspor: pd.DataFrame,
                         year_range: tuple[int, int] | None = None) -> pd.DataFrame:
    """Compute per-province average kredit & ekspor for correlation analysis.

    Returns DataFrame with columns: provinsi, avg_kredit_miliar, avg_ekspor_juta_usd.
    """
    kr = kredit[kredit["jenis_kredit"] == "Total"].copy()
    if year_range:
        kr = kr[(kr["tahun"] >= year_range[0]) & (kr["tahun"] <= year_range[1])]
        ekspor = ekspor[(ekspor["tahun"] >= year_range[0]) & (ekspor["tahun"] <= year_range[1])]
    kr_avg = kr.groupby("provinsi")["nilai_miliar_rp"].mean().reset_index()
    kr_avg = kr_avg.rename(columns={"nilai_miliar_rp": "avg_kredit_miliar"})
    ek_avg = ekspor.groupby("provinsi")["nilai_juta_usd"].sum().groupby(level=0).mean().reset_index()
    # Sum across subsektor per (provinsi, tahun), then average over tahun
    ek_per_year = ekspor.groupby(["provinsi", "tahun"])["nilai_juta_usd"].sum().reset_index()
    ek_avg = ek_per_year.groupby("provinsi")["nilai_juta_usd"].mean().reset_index()
    ek_avg = ek_avg.rename(columns={"nilai_juta_usd": "avg_ekspor_juta_usd"})
    merged = pd.merge(kr_avg, ek_avg, on="provinsi", how="inner")
    return merged


def pearson_corr(x: pd.Series, y: pd.Series) -> float:
    """Compute Pearson correlation coefficient (handles edge cases)."""
    if len(x) < 2:
        return float("nan")
    xa, ya = x.values, y.values
    if np.std(xa) == 0 or np.std(ya) == 0:
        return float("nan")
    return float(np.corrcoef(xa, ya)[0, 1])


def per_province_timeseries(kredit: pd.DataFrame, ekspor: pd.DataFrame,
                             impor: pd.DataFrame, provinsi: str) -> pd.DataFrame:
    """Build a long-format DataFrame for one province across all 3 datasets.

    Output columns: tahun, indikator, nilai
    """
    rows = []
    if kredit is not None and not kredit.empty:
        kr = kredit[(kredit["provinsi"] == provinsi)
                     & (kredit["jenis_kredit"] == "Total")]
        for _, r in kr.iterrows():
            rows.append({
                "tahun": r["tahun"], "indikator": "Kredit (Rp Miliar)",
                "nilai": r["nilai_miliar_rp"],
            })
    if ekspor is not None and not ekspor.empty:
        ek = (ekspor[ekspor["provinsi"] == provinsi]
                .groupby("tahun")["nilai_juta_usd"].sum().reset_index())
        for _, r in ek.iterrows():
            rows.append({
                "tahun": r["tahun"], "indikator": "Ekspor (Juta USD)",
                "nilai": r["nilai_juta_usd"],
            })
    if impor is not None and not impor.empty:
        im = (impor[impor["provinsi"] == provinsi]
                .groupby("tahun")["nilai_juta_usd"].sum().reset_index())
        for _, r in im.iterrows():
            rows.append({
                "tahun": r["tahun"], "indikator": "Impor (Juta USD)",
                "nilai": r["nilai_juta_usd"],
            })
    return pd.DataFrame(rows)
