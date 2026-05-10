"""Dashboard interaktif: Kredit, Ekspor & Impor Sektor Pertanian per Provinsi.

Run:
    streamlit run app.py

Data sources:
    - Kredit pertanian: Bank Indonesia SEKDA (manual download required)
    - Ekspor pertanian: BPS publikasi tahunan + Kementan eksim
    - Impor pertanian: Kementan eksim + BPS impor

Real-data-only mode — semua angka dari sumber resmi:
  - OJK SPI Desember 2015–2024 (kredit)
  - BPS publikasi Ekspor Menurut Provinsi 2014–2024 (ekspor)
  - BPS Statistik Perdagangan Luar Negeri Impor Buku II 2024 (impor)
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.map_utils import make_choropleth
from src.provinces import PROVINCES, PROVINCE_NAMES
from src.transform.loader import (data_status, load_ekspor, load_impor,
                                    load_kredit, load_ntp, load_pdrb,
                                    load_produksi)

st.set_page_config(
    page_title="Dashboard Pertanian Indonesia (2014-2024)",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------- Login Gate ----------
def _get_valid_passwords() -> set:
    """Baca password dari st.secrets (production) atau fallback env var."""
    try:
        raw = st.secrets["auth"]["passwords"]
        # secrets bisa string "FAIDIL,IHZAN" atau list ["FAIDIL","IHZAN"]
        if isinstance(raw, str):
            return {p.strip().upper() for p in raw.split(",") if p.strip()}
        return {p.strip().upper() for p in raw if p.strip()}
    except Exception:
        import os
        fallback = os.environ.get("APP_PASSWORDS", "")
        if fallback:
            return {p.strip().upper() for p in fallback.split(",") if p.strip()}
        return set()

if not st.session_state.get("authenticated", False):
    st.markdown(
        "<h2 style='text-align:center; margin-top:80px;'>🔒 Dashboard Pertanian Indonesia</h2>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p style='text-align:center; color:gray;'>Masukkan password untuk melanjutkan</p>",
        unsafe_allow_html=True,
    )
    col_l, col_m, col_r = st.columns([1, 1, 1])
    with col_m:
        pwd_input = st.text_input("Password", type="password", label_visibility="collapsed",
                                  placeholder="Masukkan password…")
        if st.button("Masuk", use_container_width=True, type="primary"):
            valid = _get_valid_passwords()
            if pwd_input.strip().upper() in valid:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Password salah. Coba lagi.")
    st.stop()
# ---------- End Login Gate ----------


@st.cache_data(ttl=600)
def _load_all():
    return (load_kredit(), load_ekspor(), load_impor(),
            load_pdrb(), load_ntp(), load_produksi(), data_status())


def _kpi(df: pd.DataFrame, value_col: str, label: str, formatter):
    if df.empty:
        st.metric(label, "—")
        return
    total = df[value_col].sum()
    st.metric(label, formatter(total))


def _fmt_rupiah(v):
    """Format nilai dalam Rp Miliar -> Miliar atau Triliun."""
    if pd.isna(v) or v == 0:
        return "—"
    if v >= 1_000:
        return f"Rp {v/1_000:,.1f} T"         # Triliun (1 T = 1.000 Miliar)
    return f"Rp {v:,.1f} M"                    # Miliar


def _fmt_usd(v):
    """Format nilai dalam Juta USD -> Juta/Miliar USD."""
    if pd.isna(v) or v == 0:
        return "—"
    if abs(v) >= 1_000:
        return f"USD {v/1_000:,.2f} B"        # Miliar (Billion)
    return f"USD {v:,.1f} M"                   # Juta (Million)


def main():
    st.title("Dashboard Sektor Pertanian Indonesia")
    st.caption("Kredit • Ekspor • Impor menurut Provinsi (2014–2024)")

    kredit, ekspor, impor, pdrb, ntp, produksi, status = _load_all()

    # ---------- Sidebar Filters ----------
    with st.sidebar:
        st.header("Filter")
        all_years = sorted(set(kredit["tahun"]) | set(ekspor["tahun"]) | set(impor["tahun"]))
        if all_years:
            yr_min, yr_max = int(min(all_years)), int(max(all_years))
            year_range = st.slider("Rentang tahun", yr_min, yr_max, (yr_min, yr_max))
        else:
            year_range = (2014, 2024)

        prov_options = ["(semua)"] + PROVINCE_NAMES
        selected_provs = st.multiselect(
            "Provinsi (kosong = semua)", PROVINCE_NAMES, default=[]
        )

        st.divider()
        st.markdown("**Coverage data resmi**")
        _label_map = {
            "kredit":  ("💳", "Kredit",  "OJK SPI"),
            "ekspor":  ("📤", "Ekspor",  "BPS"),
            "impor":   ("📥", "Impor",   "BPS"),
            "ntp":     ("🌾", "NTP",     "BPS"),
            "padi":    ("🌾", "Padi",    "BPS"),
            "jagung":  ("🌽", "Jagung",  "BPS"),
        }
        for k, v in status.items():
            icon, label, src = _label_map.get(k, ("📊", k.title(), ""))
            total = v.get("total", 0)
            if total == 0:
                st.markdown(f"- {icon} **{label}**: belum ada data")
            else:
                provs = v.get("provinces", 0)
                ymin, ymax = v.get("year_min"), v.get("year_max")
                st.markdown(
                    f"- {icon} **{label}**: {total:,} baris · "
                    f"{provs} prov · {ymin}–{ymax}"
                )

        st.divider()
        st.caption(
            "Sumber: OJK SPI (kredit) · BPS Publikasi (ekspor & impor) · "
            "BPS Tabel Statis (padi, jagung) · BPS via Jabarprov (NTP). "
            "Lihat tab **Sumber Data** untuk detail."
        )

    # ---------- Filter dataframes ----------
    def _flt(df: pd.DataFrame) -> pd.DataFrame:
        out = df[(df["tahun"] >= year_range[0]) & (df["tahun"] <= year_range[1])]
        if selected_provs:
            out = out[out["provinsi"].isin(selected_provs)]
        return out

    kr_f = _flt(kredit)
    ek_f = _flt(ekspor)
    im_f = _flt(impor)

    # ---------- Coverage info banner ----------
    total_rows = sum(s.get("total", 0) for s in status.values())
    if total_rows == 0:
        st.warning(
            "Belum ada data resmi yang ter-load. Jalankan ingestion script "
            "(lihat **Sumber Data**) untuk memulai."
        )
    else:
        gaps = []
        if status["kredit"].get("year_min") and status["kredit"]["year_min"] > 2014:
            gaps.append(f"kredit {status['kredit']['year_min']-1}↓")
        if status["impor"].get("year_min") and status["impor"]["year_min"] > 2014:
            gaps.append(f"impor 2014–{status['impor']['year_min']-1}")
        if gaps:
            st.info(
                f"Data resmi: **{total_rows:,} rows** terload. "
                f"Gap coverage: {', '.join(gaps)}."
            )

    # ---------- KPIs ----------
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        # kredit total: pakai jenis_kredit "Total"
        kr_total_only = kr_f[kr_f["jenis_kredit"] == "Total"]
        _kpi(kr_total_only, "nilai_miliar_rp", "Total Kredit", _fmt_rupiah)
    with c2:
        _kpi(ek_f, "nilai_juta_usd", "Total Ekspor", _fmt_usd)
    with c3:
        _kpi(im_f, "nilai_juta_usd", "Total Impor", _fmt_usd)
    with c4:
        if not ek_f.empty and not im_f.empty:
            net = ek_f["nilai_juta_usd"].sum() - im_f["nilai_juta_usd"].sum()
            st.metric("Surplus/Defisit Perdagangan", _fmt_usd(net))
        else:
            st.metric("Surplus/Defisit Perdagangan", "—")

    st.divider()

    # ---------- Tabs ----------
    tabs = st.tabs(["Ringkasan", "Kredit", "Ekspor", "Impor", "Neraca Perdagangan",
                    "Analytics", "NTP Petani", "Produksi Pangan",
                    "Perbandingan Provinsi", "Data Mentah", "Sumber Data"])

    # ===== TAB: RINGKASAN =====
    with tabs[0]:
        st.subheader("Tren Tahunan Nasional")
        col1, col2 = st.columns(2)

        with col1:
            kr_year = (kr_f[kr_f["jenis_kredit"] == "Total"]
                       .groupby("tahun")["nilai_miliar_rp"].sum().reset_index())
            kr_year["nilai_triliun_rp"] = kr_year["nilai_miliar_rp"] / 1000
            fig = px.line(
                kr_year, x="tahun", y="nilai_triliun_rp",
                markers=True, title="Posisi Kredit Pertanian (Rp Triliun)",
            )
            fig.update_layout(height=350, xaxis_title="Tahun", yaxis_title="Rp Triliun")
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            trade = pd.merge(
                ek_f.groupby("tahun")["nilai_juta_usd"].sum().reset_index().rename(
                    columns={"nilai_juta_usd": "Ekspor"}),
                im_f.groupby("tahun")["nilai_juta_usd"].sum().reset_index().rename(
                    columns={"nilai_juta_usd": "Impor"}),
                on="tahun", how="outer",
            ).fillna(0)
            trade_long = trade.melt(id_vars="tahun", value_vars=["Ekspor", "Impor"],
                                     var_name="jenis", value_name="nilai_juta_usd")
            fig = px.bar(
                trade_long, x="tahun", y="nilai_juta_usd", color="jenis",
                barmode="group", title="Ekspor vs Impor Pertanian (Juta USD)",
            )
            fig.update_layout(height=350, xaxis_title="Tahun", yaxis_title="Juta USD")
            st.plotly_chart(fig, use_container_width=True)

        st.subheader("Top 10 Provinsi (Total dalam Rentang Tahun Terpilih)")
        col1, col2, col3 = st.columns(3)
        with col1:
            top_kr = (kr_f[kr_f["jenis_kredit"] == "Total"]
                      .groupby("provinsi")["nilai_miliar_rp"].sum()
                      .sort_values(ascending=True).tail(10).reset_index())
            fig = px.bar(top_kr, x="nilai_miliar_rp", y="provinsi", orientation="h",
                         title="Kredit (Rp Miliar)", color_discrete_sequence=["#2E7D32"])
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            top_ek = (ek_f.groupby("provinsi")["nilai_juta_usd"].sum()
                      .sort_values(ascending=True).tail(10).reset_index())
            fig = px.bar(top_ek, x="nilai_juta_usd", y="provinsi", orientation="h",
                         title="Ekspor (Juta USD)", color_discrete_sequence=["#1976D2"])
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)
        with col3:
            top_im = (im_f.groupby("provinsi")["nilai_juta_usd"].sum()
                      .sort_values(ascending=True).tail(10).reset_index())
            fig = px.bar(top_im, x="nilai_juta_usd", y="provinsi", orientation="h",
                         title="Impor (Juta USD)", color_discrete_sequence=["#D32F2F"])
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)

        # ----- Top Mover Section -----
        st.subheader("Top Mover — Perubahan YoY Tahun Terakhir")
        st.caption("Perubahan Year-over-Year (%) pada tahun terakhir yang tersedia.")
        col_tm1, col_tm2 = st.columns(2)

        with col_tm1:
            kr_yoy = (kr_f[kr_f["jenis_kredit"] == "Total"]
                      .groupby(["tahun", "provinsi"])["nilai_miliar_rp"].sum().reset_index())
            kr_years_sorted = sorted(kr_yoy["tahun"].unique())
            if len(kr_years_sorted) >= 2:
                last_yr_kr = kr_years_sorted[-1]
                prev_yr_kr = kr_years_sorted[-2]
                kr_last = kr_yoy[kr_yoy["tahun"] == last_yr_kr][["provinsi", "nilai_miliar_rp"]].rename(columns={"nilai_miliar_rp": "curr"})
                kr_prev = kr_yoy[kr_yoy["tahun"] == prev_yr_kr][["provinsi", "nilai_miliar_rp"]].rename(columns={"nilai_miliar_rp": "prev"})
                kr_change = pd.merge(kr_last, kr_prev, on="provinsi")
                kr_change["yoy_pct"] = ((kr_change["curr"] - kr_change["prev"]) / kr_change["prev"].replace(0, float("nan"))) * 100
                kr_change = kr_change.dropna(subset=["yoy_pct"]).sort_values("yoy_pct")
                if not kr_change.empty:
                    fig_tm_kr = px.bar(
                        kr_change, x="yoy_pct", y="provinsi", orientation="h",
                        title=f"YoY Kredit {prev_yr_kr}→{last_yr_kr} (%)",
                        color="yoy_pct",
                        color_continuous_scale="RdYlGn",
                        color_continuous_midpoint=0,
                    )
                    fig_tm_kr.update_layout(height=max(400, len(kr_change) * 18), coloraxis_showscale=False)
                    st.plotly_chart(fig_tm_kr, use_container_width=True)
                else:
                    st.info("Data YoY kredit tidak tersedia.")
            else:
                st.info("Butuh minimal 2 tahun data kredit untuk YoY.")

        with col_tm2:
            ek_yoy = (ek_f.groupby(["tahun", "provinsi"])["nilai_juta_usd"].sum().reset_index())
            ek_years_sorted = sorted(ek_yoy["tahun"].unique())
            if len(ek_years_sorted) >= 2:
                last_yr_ek = ek_years_sorted[-1]
                prev_yr_ek = ek_years_sorted[-2]
                ek_last = ek_yoy[ek_yoy["tahun"] == last_yr_ek][["provinsi", "nilai_juta_usd"]].rename(columns={"nilai_juta_usd": "curr"})
                ek_prev = ek_yoy[ek_yoy["tahun"] == prev_yr_ek][["provinsi", "nilai_juta_usd"]].rename(columns={"nilai_juta_usd": "prev"})
                ek_change = pd.merge(ek_last, ek_prev, on="provinsi")
                ek_change["yoy_pct"] = ((ek_change["curr"] - ek_change["prev"]) / ek_change["prev"].replace(0, float("nan"))) * 100
                ek_change = ek_change.dropna(subset=["yoy_pct"]).sort_values("yoy_pct")
                if not ek_change.empty:
                    fig_tm_ek = px.bar(
                        ek_change, x="yoy_pct", y="provinsi", orientation="h",
                        title=f"YoY Ekspor {prev_yr_ek}→{last_yr_ek} (%)",
                        color="yoy_pct",
                        color_continuous_scale="RdYlGn",
                        color_continuous_midpoint=0,
                    )
                    fig_tm_ek.update_layout(height=max(400, len(ek_change) * 18), coloraxis_showscale=False)
                    st.plotly_chart(fig_tm_ek, use_container_width=True)
                else:
                    st.info("Data YoY ekspor tidak tersedia.")
            else:
                st.info("Butuh minimal 2 tahun data ekspor untuk YoY.")

    # ===== TAB: KREDIT =====
    with tabs[1]:
        st.subheader("Kredit Sektor Pertanian per Provinsi")
        if kr_f.empty:
            st.info("Tidak ada data kredit untuk filter ini.")
        else:
            jenis_options = sorted(kr_f["jenis_kredit"].unique())
            jenis_sel = st.multiselect(
                "Jenis kredit", jenis_options,
                default=[j for j in jenis_options if j != "Total"],
            )
            kr_view = kr_f[kr_f["jenis_kredit"].isin(jenis_sel)]

            # Choropleth map
            map_yr = st.selectbox(
                "Pilih tahun untuk peta",
                sorted(kr_view["tahun"].unique(), reverse=True),
                key="kredit_map_year",
            )
            map_df = (kr_view[kr_view["tahun"] == map_yr]
                      .groupby("provinsi")["nilai_miliar_rp"].sum().reset_index())
            total_nat = map_df["nilai_miliar_rp"].sum()
            map_df["share_pct"] = (map_df["nilai_miliar_rp"] / total_nat * 100).round(2)
            fig = make_choropleth(
                map_df, "nilai_miliar_rp",
                f"Peta Kredit Pertanian per Provinsi ({int(map_yr)}, Rp Miliar)",
                value_label="Rp Miliar",
            )
            st.plotly_chart(fig, use_container_width=True)

            col1, col2 = st.columns(2)
            with col1:
                heat = (kr_view.groupby(["tahun", "provinsi"])["nilai_miliar_rp"].sum()
                        .reset_index())
                fig = px.density_heatmap(
                    heat, x="tahun", y="provinsi", z="nilai_miliar_rp",
                    color_continuous_scale="Greens",
                    title="Heatmap Kredit per Provinsi-Tahun (Rp Miliar)",
                )
                fig.update_layout(height=700)
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                stack = (kr_view.groupby(["tahun", "jenis_kredit"])["nilai_miliar_rp"]
                         .sum().reset_index())
                fig = px.bar(
                    stack, x="tahun", y="nilai_miliar_rp", color="jenis_kredit",
                    title="Komposisi Jenis Kredit per Tahun (Rp Miliar)",
                    barmode="stack",
                )
                fig.update_layout(height=350)
                st.plotly_chart(fig, use_container_width=True)

                pie = (kr_view.groupby("provinsi")["nilai_miliar_rp"].sum()
                       .reset_index().sort_values("nilai_miliar_rp", ascending=False)
                       .head(10))
                pie_total = pie["nilai_miliar_rp"].sum()
                pie["share_pct"] = (pie["nilai_miliar_rp"] / pie_total * 100).round(1)
                fig = px.pie(pie, names="provinsi", values="nilai_miliar_rp",
                             title="Top 10 Provinsi (Pangsa Kredit, %)",
                             hover_data=["share_pct"])
                fig.update_layout(height=350)
                st.plotly_chart(fig, use_container_width=True)

            st.divider()
            st.download_button(
                "Unduh CSV Kredit (filtered)",
                kr_f.to_csv(index=False).encode("utf-8"),
                file_name="kredit_filtered.csv",
                mime="text/csv",
                key="dl_kredit",
            )

    # ===== TAB: EKSPOR =====
    with tabs[2]:
        st.subheader("Ekspor Sektor Pertanian per Provinsi")
        if ek_f.empty:
            st.info("Tidak ada data ekspor untuk filter ini.")
        else:
            sub_options = sorted(ek_f["subsektor"].unique())
            sub_sel = st.multiselect("Subsektor", sub_options, default=sub_options)
            ek_view = ek_f[ek_f["subsektor"].isin(sub_sel)]

            metric_choice = st.radio(
                "Metrik", ["Nilai (Juta USD)", "Volume (Ribu Ton)"],
                horizontal=True,
            )
            value_col = "nilai_juta_usd" if "Nilai" in metric_choice else "volume_ton"
            value_label = "Juta USD" if "Nilai" in metric_choice else "Ton"

            # Choropleth map for ekspor
            map_yr = st.selectbox(
                "Pilih tahun untuk peta",
                sorted(ek_view["tahun"].unique(), reverse=True),
                key="ekspor_map_year",
            )
            map_df = (ek_view[ek_view["tahun"] == map_yr]
                      .groupby("provinsi")[value_col].sum().reset_index())
            total_nat = map_df[value_col].sum()
            map_df["share_pct"] = (map_df[value_col] / total_nat * 100).round(2)
            fig = make_choropleth(
                map_df, value_col,
                f"Peta Ekspor Pertanian per Provinsi Asal ({int(map_yr)}, {value_label})",
                color_scale="Blues", value_label=value_label,
            )
            st.plotly_chart(fig, use_container_width=True)

            col1, col2 = st.columns([2, 1])
            with col1:
                trend = (ek_view.groupby(["tahun", "subsektor"])[value_col]
                         .sum().reset_index())
                fig = px.area(trend, x="tahun", y=value_col, color="subsektor",
                              title=f"Tren Ekspor per Subsektor ({value_label})")
                fig.update_layout(height=400)
                st.plotly_chart(fig, use_container_width=True)

                top = (ek_view.groupby("provinsi")[value_col].sum()
                       .reset_index().sort_values(value_col, ascending=False).head(15))
                fig = px.bar(top, x="provinsi", y=value_col,
                             title=f"Top 15 Provinsi Pengekspor ({value_label})",
                             color_discrete_sequence=["#1976D2"])
                fig.update_layout(height=400, xaxis_tickangle=-45)
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                sub_pie = (ek_view.groupby("subsektor")[value_col].sum().reset_index())
                fig = px.pie(sub_pie, names="subsektor", values=value_col,
                             title=f"Komposisi Subsektor ({value_label})", hole=0.4)
                fig.update_layout(height=350)
                st.plotly_chart(fig, use_container_width=True)

                ek_year_total = ek_view.groupby("tahun")[value_col].sum().reset_index()
                fig = px.line(ek_year_total, x="tahun", y=value_col,
                              markers=True, title=f"Total Tahunan ({value_label})")
                fig.update_layout(height=350)
                st.plotly_chart(fig, use_container_width=True)

            st.divider()
            st.download_button(
                "Unduh CSV Ekspor (filtered)",
                ek_f.to_csv(index=False).encode("utf-8"),
                file_name="ekspor_filtered.csv",
                mime="text/csv",
                key="dl_ekspor",
            )

    # ===== TAB: IMPOR =====
    with tabs[3]:
        st.subheader("Impor Sektor Pertanian per Provinsi (Pelabuhan Bongkar)")
        st.caption(
            "Catatan: data impor BPS dilaporkan menurut **provinsi pelabuhan bongkar**, "
            "bukan provinsi tujuan akhir."
        )
        if im_f.empty:
            st.info("Tidak ada data impor untuk filter ini.")
        else:
            sub_options = sorted(im_f["subsektor"].unique())
            sub_sel = st.multiselect("Subsektor", sub_options, default=sub_options,
                                      key="impor_sub")
            im_view = im_f[im_f["subsektor"].isin(sub_sel)]

            metric_choice = st.radio(
                "Metrik", ["Nilai (Juta USD)", "Volume (Ribu Ton)"],
                horizontal=True, key="impor_metric",
            )
            value_col = "nilai_juta_usd" if "Nilai" in metric_choice else "volume_ton"
            value_label = "Juta USD" if "Nilai" in metric_choice else "Ton"

            # Choropleth map
            map_yr = st.selectbox(
                "Pilih tahun untuk peta",
                sorted(im_view["tahun"].unique(), reverse=True),
                key="impor_map_year",
            )
            map_df = (im_view[im_view["tahun"] == map_yr]
                      .groupby("provinsi")[value_col].sum().reset_index())
            total_nat = map_df[value_col].sum()
            map_df["share_pct"] = (map_df[value_col] / total_nat * 100).round(2)
            fig = make_choropleth(
                map_df, value_col,
                f"Peta Impor Pertanian per Pelabuhan Bongkar ({int(map_yr)}, {value_label})",
                color_scale="Reds", value_label=value_label,
            )
            st.plotly_chart(fig, use_container_width=True)

            col1, col2 = st.columns([2, 1])
            with col1:
                trend = (im_view.groupby(["tahun", "subsektor"])[value_col]
                         .sum().reset_index())
                fig = px.area(trend, x="tahun", y=value_col, color="subsektor",
                              title=f"Tren Impor per Subsektor ({value_label})")
                fig.update_layout(height=400)
                st.plotly_chart(fig, use_container_width=True)

                top = (im_view.groupby("provinsi")[value_col].sum()
                       .reset_index().sort_values(value_col, ascending=False).head(15))
                fig = px.bar(top, x="provinsi", y=value_col,
                             title=f"Top 15 Pelabuhan/Provinsi Bongkar ({value_label})",
                             color_discrete_sequence=["#D32F2F"])
                fig.update_layout(height=400, xaxis_tickangle=-45)
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                sub_pie = (im_view.groupby("subsektor")[value_col].sum().reset_index())
                fig = px.pie(sub_pie, names="subsektor", values=value_col,
                             title=f"Komposisi Subsektor ({value_label})", hole=0.4)
                fig.update_layout(height=350)
                st.plotly_chart(fig, use_container_width=True)

                im_year_total = im_view.groupby("tahun")[value_col].sum().reset_index()
                fig = px.line(im_year_total, x="tahun", y=value_col,
                              markers=True, title=f"Total Tahunan ({value_label})",
                              color_discrete_sequence=["#D32F2F"])
                fig.update_layout(height=350)
                st.plotly_chart(fig, use_container_width=True)

            st.divider()
            st.download_button(
                "Unduh CSV Impor (filtered)",
                im_f.to_csv(index=False).encode("utf-8"),
                file_name="impor_filtered.csv",
                mime="text/csv",
                key="dl_impor",
            )

    # ===== TAB: NERACA PERDAGANGAN =====
    with tabs[4]:
        st.subheader("Neraca Perdagangan Pertanian")
        st.warning("Data impor hanya tersedia 2023-2024. Analisis neraca terbatas pada tahun tersebut.")

        # KPI row
        total_ek_val = ek_f["nilai_juta_usd"].sum()
        total_im_val = im_f["nilai_juta_usd"].sum()
        neraca_surplus = total_ek_val - total_im_val
        kn1, kn2, kn3 = st.columns(3)
        kn1.metric("Total Ekspor (filter)", _fmt_usd(total_ek_val))
        kn2.metric("Total Impor (filter)", _fmt_usd(total_im_val))
        kn3.metric("Surplus / Defisit", _fmt_usd(neraca_surplus))

        st.divider()

        # Bar chart: ekspor vs impor per tahun with balance line
        st.markdown("### Ekspor vs Impor per Tahun")
        ek_yr = (ek_f.groupby("tahun")["nilai_juta_usd"].sum().reset_index()
                 .rename(columns={"nilai_juta_usd": "Ekspor"}))
        im_yr = (im_f.groupby("tahun")["nilai_juta_usd"].sum().reset_index()
                 .rename(columns={"nilai_juta_usd": "Impor"}))
        neraca_yr = pd.merge(ek_yr, im_yr, on="tahun", how="outer").fillna(0)
        neraca_yr["Neraca"] = neraca_yr["Ekspor"] - neraca_yr["Impor"]
        neraca_long = neraca_yr.melt(id_vars="tahun", value_vars=["Ekspor", "Impor"],
                                      var_name="Jenis", value_name="Nilai")
        if not neraca_long.empty:
            fig_neraca = px.bar(
                neraca_long, x="tahun", y="Nilai", color="Jenis",
                barmode="group",
                color_discrete_map={"Ekspor": "#1976D2", "Impor": "#D32F2F"},
                labels={"Nilai": "Juta USD", "tahun": "Tahun"},
                title="Ekspor vs Impor per Tahun (Juta USD)",
            )
            # Add line for balance
            fig_neraca.add_scatter(
                x=neraca_yr["tahun"], y=neraca_yr["Neraca"],
                mode="lines+markers", name="Neraca",
                line=dict(color="#FF9800", width=2, dash="dot"),
            )
            fig_neraca.update_layout(height=420)
            st.plotly_chart(fig_neraca, use_container_width=True)
        else:
            st.info("Tidak ada data ekspor/impor untuk filter ini.")

        st.divider()

        # Heatmap: pivot ekspor-impor per province (overlapping years)
        st.markdown("### Neraca per Provinsi (Tahun Overlap: 2023-2024)")
        overlap_years = sorted(set(ek_f["tahun"]) & set(im_f["tahun"]))
        if overlap_years:
            ek_ovlp = (ek_f[ek_f["tahun"].isin(overlap_years)]
                       .groupby("provinsi")["nilai_juta_usd"].sum()
                       .reset_index().rename(columns={"nilai_juta_usd": "ekspor_juta_usd"}))
            im_ovlp = (im_f[im_f["tahun"].isin(overlap_years)]
                       .groupby("provinsi")["nilai_juta_usd"].sum()
                       .reset_index().rename(columns={"nilai_juta_usd": "impor_juta_usd"}))
            neraca_prov = pd.merge(ek_ovlp, im_ovlp, on="provinsi", how="outer").fillna(0)
            neraca_prov["surplus_juta_usd"] = neraca_prov["ekspor_juta_usd"] - neraca_prov["impor_juta_usd"]
            neraca_prov = neraca_prov.sort_values("surplus_juta_usd", ascending=False)

            col_n1, col_n2 = st.columns([2, 1])
            with col_n1:
                neraca_prov_long = neraca_prov.melt(
                    id_vars="provinsi",
                    value_vars=["ekspor_juta_usd", "impor_juta_usd"],
                    var_name="Jenis", value_name="Nilai",
                )
                neraca_prov_long["Jenis"] = neraca_prov_long["Jenis"].map(
                    {"ekspor_juta_usd": "Ekspor", "impor_juta_usd": "Impor"}
                )
                fig_heat_prov = px.bar(
                    neraca_prov_long,
                    x="Nilai", y="provinsi", color="Jenis",
                    barmode="group", orientation="h",
                    color_discrete_map={"Ekspor": "#1976D2", "Impor": "#D32F2F"},
                    title=f"Ekspor vs Impor per Provinsi ({', '.join(str(y) for y in overlap_years)})",
                    labels={"Nilai": "Juta USD", "provinsi": "Provinsi"},
                )
                fig_heat_prov.update_layout(height=max(500, len(neraca_prov) * 22))
                st.plotly_chart(fig_heat_prov, use_container_width=True)

            with col_n2:
                st.markdown("#### Ranking Surplus/Defisit")
                surplus_display = neraca_prov[["provinsi", "surplus_juta_usd"]].copy()
                surplus_display["surplus_juta_usd"] = surplus_display["surplus_juta_usd"].round(2)
                surplus_display.columns = ["Provinsi", "Surplus (Juta USD)"]
                st.dataframe(surplus_display, use_container_width=True, hide_index=True, height=500)
        else:
            st.info("Tidak ada tahun overlap antara ekspor dan impor pada filter ini.")

    # ===== TAB: ANALYTICS =====
    with tabs[5]:
        from src.analytics import (compute_cagr, compute_correlation,
                                     pearson_corr, per_province_timeseries)
        st.subheader("Analytics — CAGR & Korelasi")

        # ----- CAGR Section -----
        st.markdown("### CAGR per Provinsi")
        st.caption("Compound Annual Growth Rate antara 2 tahun yang dipilih.")

        cagr_years = sorted(set(kr_f["tahun"]) | set(ek_f["tahun"]) | set(im_f["tahun"]))
        if len(cagr_years) < 2:
            st.info("Butuh data minimal 2 tahun untuk hitung CAGR.")
        else:
            c1, c2, c3 = st.columns([1, 1, 2])
            with c1:
                start_y = st.selectbox("Tahun awal", cagr_years, index=0, key="cagr_start")
            with c2:
                end_y = st.selectbox("Tahun akhir", cagr_years,
                                      index=len(cagr_years) - 1, key="cagr_end")
            with c3:
                metric_kind = st.radio(
                    "Indikator", ["Kredit", "Ekspor", "Impor"], horizontal=True,
                    key="cagr_metric",
                )

            if start_y >= end_y:
                st.warning("Tahun awal harus lebih kecil dari tahun akhir.")
            else:
                if metric_kind == "Kredit":
                    src = kr_f[kr_f["jenis_kredit"] == "Total"]
                    cagr_df = compute_cagr(src, "nilai_miliar_rp", start_y, end_y)
                    val_label = "Rp Miliar"
                elif metric_kind == "Ekspor":
                    src = ek_f.groupby(["provinsi", "tahun"])["nilai_juta_usd"].sum().reset_index()
                    cagr_df = compute_cagr(src, "nilai_juta_usd", start_y, end_y)
                    val_label = "Juta USD"
                else:
                    src = im_f.groupby(["provinsi", "tahun"])["nilai_juta_usd"].sum().reset_index()
                    cagr_df = compute_cagr(src, "nilai_juta_usd", start_y, end_y)
                    val_label = "Juta USD"

                if cagr_df.empty:
                    st.info(f"Tidak ada data {metric_kind} untuk {start_y}–{end_y}.")
                else:
                    fig = px.bar(
                        cagr_df, x="cagr_pct", y="provinsi", orientation="h",
                        title=f"CAGR {metric_kind} {start_y}–{end_y} (%)",
                        color="cagr_pct", color_continuous_scale="RdYlGn",
                        color_continuous_midpoint=0,
                        height=max(400, 18 * len(cagr_df)),
                    )
                    fig.update_layout(yaxis={"categoryorder": "total ascending"})
                    st.plotly_chart(fig, use_container_width=True)

                    c1, c2, c3 = st.columns(3)
                    avg_cagr = cagr_df["cagr_pct"].mean()
                    top_prov = cagr_df.iloc[0]
                    bot_prov = cagr_df.iloc[-1]
                    c1.metric("Rata-rata CAGR", f"{avg_cagr:.2f}%")
                    c2.metric(f"Tertinggi: {top_prov['provinsi']}",
                              f"{top_prov['cagr_pct']:.2f}%")
                    c3.metric(f"Terendah: {bot_prov['provinsi']}",
                              f"{bot_prov['cagr_pct']:.2f}%")

                    with st.expander("Lihat tabel CAGR lengkap"):
                        df_show = cagr_df.copy()
                        df_show["cagr_pct"] = df_show["cagr_pct"].round(2)
                        df_show["start"] = df_show["start"].round(1)
                        df_show["end"] = df_show["end"].round(1)
                        df_show.columns = ["Provinsi", f"Nilai {start_y}",
                                           f"Nilai {end_y}", "CAGR (%)"]
                        st.dataframe(df_show, use_container_width=True, hide_index=True)

        st.markdown("---")

        # ----- Correlation Section -----
        st.markdown("### Korelasi Kredit vs Ekspor (per Provinsi)")
        st.caption("Apakah provinsi dengan kredit pertanian lebih besar juga ekspor lebih besar?")

        if kr_f.empty or ek_f.empty:
            st.info("Butuh data kredit & ekspor.")
        else:
            corr_df = compute_correlation(kr_f, ek_f, year_range=year_range)
            if corr_df.empty or len(corr_df) < 3:
                st.info("Data korelasi tidak cukup.")
            else:
                r = pearson_corr(corr_df["avg_kredit_miliar"],
                                 corr_df["avg_ekspor_juta_usd"])
                col1, col2 = st.columns([3, 1])
                with col1:
                    fig = px.scatter(
                        corr_df, x="avg_kredit_miliar", y="avg_ekspor_juta_usd",
                        text="provinsi", trendline="ols",
                        labels={"avg_kredit_miliar": "Rata-rata Kredit (Rp Miliar)",
                                "avg_ekspor_juta_usd": "Rata-rata Ekspor (Juta USD)"},
                        title=f"Pearson r = {r:.3f}" if not pd.isna(r) else "Korelasi",
                    )
                    fig.update_traces(textposition="top center", textfont_size=9)
                    fig.update_layout(height=550)
                    st.plotly_chart(fig, use_container_width=True)
                with col2:
                    st.metric("Pearson r",
                              f"{r:.3f}" if not pd.isna(r) else "—")
                    if not pd.isna(r):
                        if abs(r) > 0.7:
                            st.success("Korelasi kuat")
                        elif abs(r) > 0.4:
                            st.info("Korelasi sedang")
                        else:
                            st.warning("Korelasi lemah")
                    st.caption("Sumbu skala log-friendly. "
                               "Korelasi positif = provinsi dengan kredit "
                               "lebih besar juga ekspor lebih besar.")

        st.markdown("---")

        # ----- Kredit vs PDRB Pertanian -----
        st.markdown("### Kredit vs PDRB Sektor Pertanian")
        st.caption(
            "Rasio kredit pertanian terhadap PDRB sektor pertanian per provinsi — "
            "ukuran intensitas pembiayaan/penetrasi finansial sektor."
        )
        if pdrb is None or pdrb.empty:
            st.info("Data PDRB belum tersedia.")
        elif kr_f.empty:
            st.info("Data kredit belum tersedia untuk filter ini.")
        else:
            jenis_harga = st.radio(
                "Basis PDRB",
                ["Berlaku", "Konstan"],
                horizontal=True,
                key="pdrb_basis",
                help="Berlaku = harga current; Konstan = harga 2010 (real, tanpa inflasi)",
            )
            pdrb_f = pdrb[
                (pdrb["jenis_harga"] == jenis_harga)
                & (pdrb["tahun"] >= year_range[0])
                & (pdrb["tahun"] <= year_range[1])
            ]
            if selected_provs:
                pdrb_f = pdrb_f[pdrb_f["provinsi"].isin(selected_provs)]

            kr_total = kr_f[kr_f["jenis_kredit"] == "Total"][
                ["tahun", "provinsi", "nilai_miliar_rp"]
            ].rename(columns={"nilai_miliar_rp": "kredit_miliar"})
            pdrb_view = pdrb_f[["tahun", "provinsi", "nilai_miliar_rp"]].rename(
                columns={"nilai_miliar_rp": "pdrb_miliar"}
            )
            merged = pd.merge(kr_total, pdrb_view, on=["tahun", "provinsi"], how="inner")

            if merged.empty:
                st.info(
                    f"Tidak ada overlap data kredit & PDRB ({jenis_harga}) "
                    "untuk filter ini."
                )
            else:
                merged["rasio_pct"] = (
                    merged["kredit_miliar"] / merged["pdrb_miliar"] * 100
                )
                # Average ratio per province
                avg_per_prov = (
                    merged.groupby("provinsi")
                    .agg(
                        avg_kredit=("kredit_miliar", "mean"),
                        avg_pdrb=("pdrb_miliar", "mean"),
                        avg_rasio=("rasio_pct", "mean"),
                    )
                    .reset_index()
                    .sort_values("avg_rasio", ascending=False)
                )

                col1, col2 = st.columns([2, 1])
                with col1:
                    fig = px.bar(
                        avg_per_prov,
                        x="avg_rasio",
                        y="provinsi",
                        orientation="h",
                        color="avg_rasio",
                        color_continuous_scale="Viridis",
                        title=f"Rasio Kredit/PDRB (%) — Rata-rata {year_range[0]}–{year_range[1]} ({jenis_harga})",
                        labels={"avg_rasio": "Rasio (%)", "provinsi": "Provinsi"},
                        height=max(400, 18 * len(avg_per_prov)),
                    )
                    fig.update_layout(
                        yaxis={"categoryorder": "total ascending"},
                        coloraxis_showscale=False,
                    )
                    st.plotly_chart(fig, use_container_width=True)
                with col2:
                    avg_nat = avg_per_prov["avg_rasio"].mean()
                    top_p = avg_per_prov.iloc[0]
                    bot_p = avg_per_prov.iloc[-1]
                    st.metric("Rata-rata rasio", f"{avg_nat:.1f}%")
                    st.metric(
                        f"Tertinggi: {top_p['provinsi']}", f"{top_p['avg_rasio']:.1f}%"
                    )
                    st.metric(
                        f"Terendah: {bot_p['provinsi']}", f"{bot_p['avg_rasio']:.1f}%"
                    )
                    st.caption(
                        "Rasio tinggi → kredit relatif besar dibanding output sektor "
                        "(tanda intensitas finansial). Rasio rendah → potensi "
                        "ekspansi kredit."
                    )

                # Trend chart of national ratio
                trend = (
                    merged.groupby("tahun")
                    .agg(
                        kredit=("kredit_miliar", "sum"),
                        pdrb=("pdrb_miliar", "sum"),
                    )
                    .reset_index()
                )
                trend["rasio_pct"] = trend["kredit"] / trend["pdrb"] * 100
                fig = px.line(
                    trend,
                    x="tahun",
                    y="rasio_pct",
                    markers=True,
                    title=f"Tren Nasional Rasio Kredit/PDRB Pertanian (%) — {jenis_harga}",
                    labels={"rasio_pct": "Rasio (%)", "tahun": "Tahun"},
                )
                fig.update_layout(height=350)
                st.plotly_chart(fig, use_container_width=True)

                with st.expander("Lihat tabel detail rasio"):
                    show = avg_per_prov.copy()
                    show["avg_kredit"] = show["avg_kredit"].round(0).astype(int)
                    show["avg_pdrb"] = show["avg_pdrb"].round(0).astype(int)
                    show["avg_rasio"] = show["avg_rasio"].round(2)
                    show.columns = [
                        "Provinsi",
                        "Avg Kredit (Rp Miliar)",
                        "Avg PDRB (Rp Miliar)",
                        "Rasio (%)",
                    ]
                    st.dataframe(show, use_container_width=True, hide_index=True)

        st.markdown("---")

        # ----- Per-province deep dive -----
        st.markdown("### Deep Dive: 1 Provinsi vs 3 Indikator")
        prov_options = sorted(set(kr_f["provinsi"]) | set(ek_f["provinsi"])
                              | set(im_f["provinsi"]))
        if not prov_options:
            st.info("Tidak ada provinsi.")
        else:
            sel_prov = st.selectbox("Pilih provinsi", prov_options,
                                     index=prov_options.index("Jawa Barat")
                                     if "Jawa Barat" in prov_options else 0)
            ts = per_province_timeseries(kr_f, ek_f, im_f, sel_prov)
            if ts.empty:
                st.info("Tidak ada data.")
            else:
                fig = px.line(ts, x="tahun", y="nilai", color="indikator",
                              markers=True, facet_col="indikator", facet_col_wrap=3,
                              title=f"{sel_prov} — tren 3 indikator",
                              labels={"nilai": "Nilai", "tahun": "Tahun"})
                fig.update_yaxes(matches=None)
                fig.update_layout(height=400, showlegend=False)
                st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")

        # ----- YoY Growth Rate Section -----
        st.markdown("### YoY Growth Rate per Provinsi")
        st.caption("Pertumbuhan Year-over-Year (%) untuk tahun yang dipilih.")
        c_yoy1, c_yoy2, c_yoy3 = st.columns([1, 1, 2])
        with c_yoy1:
            yoy_indicator = st.selectbox(
                "Indikator", ["Kredit", "Ekspor", "Impor"], key="analytics_yoy_indicator"
            )
        if yoy_indicator == "Kredit":
            yoy_src = (kr_f[kr_f["jenis_kredit"] == "Total"]
                       .groupby(["tahun", "provinsi"])["nilai_miliar_rp"].sum().reset_index()
                       .rename(columns={"nilai_miliar_rp": "nilai"}))
        elif yoy_indicator == "Ekspor":
            yoy_src = (ek_f.groupby(["tahun", "provinsi"])["nilai_juta_usd"].sum().reset_index()
                       .rename(columns={"nilai_juta_usd": "nilai"}))
        else:
            yoy_src = (im_f.groupby(["tahun", "provinsi"])["nilai_juta_usd"].sum().reset_index()
                       .rename(columns={"nilai_juta_usd": "nilai"}))

        yoy_years_avail = sorted(yoy_src["tahun"].unique())
        if len(yoy_years_avail) < 2:
            st.info("Butuh minimal 2 tahun data untuk hitung YoY.")
        else:
            with c_yoy2:
                yoy_year_sel = st.selectbox(
                    "Tahun", yoy_years_avail[1:], index=len(yoy_years_avail) - 2, key="analytics_yoy_year"
                )
            yoy_curr = yoy_src[yoy_src["tahun"] == yoy_year_sel][["provinsi", "nilai"]].rename(columns={"nilai": "curr"})
            yoy_prev_yr = yoy_years_avail[yoy_years_avail.index(yoy_year_sel) - 1]
            yoy_prev = yoy_src[yoy_src["tahun"] == yoy_prev_yr][["provinsi", "nilai"]].rename(columns={"nilai": "prev"})
            yoy_merged = pd.merge(yoy_curr, yoy_prev, on="provinsi")
            yoy_merged["yoy_pct"] = ((yoy_merged["curr"] - yoy_merged["prev"]) / yoy_merged["prev"].replace(0, float("nan"))) * 100
            yoy_merged = yoy_merged.dropna(subset=["yoy_pct"]).sort_values("yoy_pct")
            if yoy_merged.empty:
                st.info("Tidak ada data YoY untuk pilihan ini.")
            else:
                fig_yoy = px.bar(
                    yoy_merged, x="yoy_pct", y="provinsi", orientation="h",
                    title=f"YoY Growth {yoy_indicator} {yoy_prev_yr}→{yoy_year_sel} (%)",
                    color="yoy_pct",
                    color_continuous_scale="RdYlGn",
                    color_continuous_midpoint=0,
                )
                fig_yoy.update_layout(height=max(400, len(yoy_merged) * 18), coloraxis_showscale=False)
                st.plotly_chart(fig_yoy, use_container_width=True)

        st.markdown("---")

        # ----- Bubble Chart: Produksi vs Ekspor vs Kredit -----
        st.markdown("### Bubble Chart: Produksi Padi vs Ekspor vs Kredit")
        st.caption("X = rata-rata produksi padi (ton), Y = rata-rata ekspor (Juta USD), ukuran gelembung = rata-rata kredit (Rp Miliar).")
        if produksi is None or produksi.empty or ek_f.empty or kr_f.empty:
            st.info("Butuh data produksi, ekspor, dan kredit untuk bubble chart.")
        else:
            prod_padi = (produksi[produksi["komoditas"] == "Padi"]
                         .groupby("provinsi")["produksi_ton"].mean().reset_index()
                         .rename(columns={"produksi_ton": "avg_produksi_ton"}))
            ek_avg = (ek_f.groupby("provinsi")["nilai_juta_usd"].mean().reset_index()
                      .rename(columns={"nilai_juta_usd": "avg_ekspor_juta_usd"}))
            kr_avg = (kr_f[kr_f["jenis_kredit"] == "Total"]
                      .groupby("provinsi")["nilai_miliar_rp"].mean().reset_index()
                      .rename(columns={"nilai_miliar_rp": "avg_kredit_miliar"}))
            bubble_df = prod_padi.merge(ek_avg, on="provinsi").merge(kr_avg, on="provinsi")
            if bubble_df.empty:
                st.info("Tidak ada data overlap untuk bubble chart.")
            else:
                fig_bubble = px.scatter(
                    bubble_df,
                    x="avg_produksi_ton", y="avg_ekspor_juta_usd",
                    size="avg_kredit_miliar", text="provinsi",
                    labels={
                        "avg_produksi_ton": "Rata-rata Produksi Padi (ton)",
                        "avg_ekspor_juta_usd": "Rata-rata Ekspor (Juta USD)",
                        "avg_kredit_miliar": "Rata-rata Kredit (Rp Miliar)",
                    },
                    title="Produksi Padi vs Ekspor vs Kredit per Provinsi",
                    size_max=60,
                )
                fig_bubble.update_traces(textposition="top center", textfont_size=9)
                fig_bubble.update_layout(height=550)
                st.plotly_chart(fig_bubble, use_container_width=True)

        st.markdown("---")

        # ----- NTP vs Produksi Correlation -----
        st.markdown("### Korelasi NTP vs Produksi Padi")
        st.caption("Apakah NTP petani lebih tinggi berkorelasi dengan produksi padi lebih besar?")
        if ntp is None or ntp.empty or produksi is None or produksi.empty:
            st.info("Butuh data NTP dan produksi untuk analisis ini.")
        else:
            ntp_avg = (ntp.groupby("provinsi")["ntp"].mean().reset_index()
                       .rename(columns={"ntp": "avg_ntp"}))
            prod_padi_avg = (produksi[produksi["komoditas"] == "Padi"]
                             .groupby("provinsi")["produksi_ton"].mean().reset_index()
                             .rename(columns={"produksi_ton": "avg_produksi_ton"}))
            ntp_prod_df = pd.merge(ntp_avg, prod_padi_avg, on="provinsi")
            if len(ntp_prod_df) < 3:
                st.info("Data tidak cukup untuk korelasi NTP vs produksi.")
            else:
                r_ntp_prod = ntp_prod_df["avg_ntp"].corr(ntp_prod_df["avg_produksi_ton"])
                col_np1, col_np2 = st.columns([3, 1])
                with col_np1:
                    fig_ntp_prod = px.scatter(
                        ntp_prod_df,
                        x="avg_ntp", y="avg_produksi_ton",
                        text="provinsi", trendline="ols",
                        labels={
                            "avg_ntp": "Rata-rata NTP (2018=100)",
                            "avg_produksi_ton": "Rata-rata Produksi Padi (ton)",
                        },
                        title=f"NTP vs Produksi Padi — Pearson r = {r_ntp_prod:.3f}" if not pd.isna(r_ntp_prod) else "NTP vs Produksi Padi",
                    )
                    fig_ntp_prod.update_traces(textposition="top center", textfont_size=9)
                    fig_ntp_prod.update_layout(height=500)
                    st.plotly_chart(fig_ntp_prod, use_container_width=True)
                with col_np2:
                    st.metric("Pearson r", f"{r_ntp_prod:.3f}" if not pd.isna(r_ntp_prod) else "—")
                    if not pd.isna(r_ntp_prod):
                        if abs(r_ntp_prod) > 0.7:
                            st.success("Korelasi kuat")
                        elif abs(r_ntp_prod) > 0.4:
                            st.info("Korelasi sedang")
                        else:
                            st.warning("Korelasi lemah")

        st.markdown("---")

        # ----- Proyeksi Sederhana (Linear) -----
        import numpy as np
        st.markdown("### Proyeksi Sederhana (Linear 3 Tahun ke Depan)")
        st.caption("⚠️ Proyeksi linear sederhana, bukan model ekonometrik. Gunakan sebagai estimasi awal saja.")

        c_proj1, c_proj2 = st.columns(2)
        with c_proj1:
            proj_indicator = st.selectbox(
                "Indikator", ["Kredit", "Ekspor", "NTP", "Produksi Padi"], key="analytics_proj_indicator"
            )
        if proj_indicator == "Kredit":
            proj_src = (kr_f[kr_f["jenis_kredit"] == "Total"]
                        .groupby(["tahun", "provinsi"])["nilai_miliar_rp"].sum().reset_index()
                        .rename(columns={"nilai_miliar_rp": "nilai"}))
            proj_unit = "Rp Miliar"
        elif proj_indicator == "Ekspor":
            proj_src = (ek_f.groupby(["tahun", "provinsi"])["nilai_juta_usd"].sum().reset_index()
                        .rename(columns={"nilai_juta_usd": "nilai"}))
            proj_unit = "Juta USD"
        elif proj_indicator == "NTP":
            if ntp is None or ntp.empty:
                proj_src = pd.DataFrame()
            else:
                proj_src = ntp[["tahun", "provinsi", "ntp"]].rename(columns={"ntp": "nilai"}).copy()
            proj_unit = "NTP (2018=100)"
        else:
            if produksi is None or produksi.empty:
                proj_src = pd.DataFrame()
            else:
                proj_src = (produksi[produksi["komoditas"] == "Padi"]
                            .groupby(["tahun", "provinsi"])["produksi_ton"].sum().reset_index()
                            .rename(columns={"produksi_ton": "nilai"}))
            proj_unit = "ton"

        if proj_src is None or proj_src.empty:
            st.info(f"Data {proj_indicator} tidak tersedia.")
        else:
            proj_provs = sorted(proj_src["provinsi"].unique())
            with c_proj2:
                proj_prov_sel = st.selectbox(
                    "Provinsi", proj_provs,
                    index=proj_provs.index("Jawa Barat") if "Jawa Barat" in proj_provs else 0,
                    key="analytics_proj_prov",
                )
            proj_prov_data = proj_src[proj_src["provinsi"] == proj_prov_sel].sort_values("tahun")
            if len(proj_prov_data) < 2:
                st.info("Butuh minimal 2 data poin untuk proyeksi.")
            else:
                x_hist = proj_prov_data["tahun"].values.astype(float)
                y_hist = proj_prov_data["nilai"].values.astype(float)
                coef = np.polyfit(x_hist, y_hist, 1)
                poly = np.poly1d(coef)
                last_yr_proj = int(x_hist[-1])
                proj_years = [last_yr_proj + 1, last_yr_proj + 2, last_yr_proj + 3]
                proj_values = [float(poly(y)) for y in proj_years]
                hist_df = pd.DataFrame({"tahun": x_hist.astype(int), "nilai": y_hist, "tipe": "Historis"})
                proj_df = pd.DataFrame({"tahun": proj_years, "nilai": proj_values, "tipe": "Proyeksi"})
                combined_df = pd.concat([hist_df, proj_df], ignore_index=True)
                fig_proj = px.line(
                    combined_df, x="tahun", y="nilai", color="tipe",
                    markers=True,
                    color_discrete_map={"Historis": "#1976D2", "Proyeksi": "#FF9800"},
                    labels={"nilai": proj_unit, "tahun": "Tahun", "tipe": ""},
                    title=f"Proyeksi {proj_indicator} — {proj_prov_sel} (Linear)",
                    line_dash="tipe",
                    line_dash_map={"Historis": "solid", "Proyeksi": "dash"},
                )
                fig_proj.update_layout(height=420)
                st.plotly_chart(fig_proj, use_container_width=True)
                st.caption("Proyeksi linear sederhana, bukan model ekonometrik.")

    # ===== TAB: NTP PETANI =====
    with tabs[6]:
        st.subheader("Nilai Tukar Petani (NTP) per Provinsi")
        st.caption(
            "NTP = Indeks Harga yang Diterima Petani / Indeks Harga yang Dibayar Petani × 100. "
            "Basis 2018=100. NTP > 100 berarti petani surplus (daya beli meningkat). "
            "Sumber: BPS via Jabarprov OpenData, 2019–2024."
        )

        if ntp is None or ntp.empty:
            st.info("Data NTP belum tersedia. Jalankan: python -m src.ingest bps_ntp")
        else:
            # --- NTP filters ---
            ntp_years = sorted(ntp["tahun"].unique())
            ntp_provs = sorted(ntp["provinsi"].unique())

            col_a, col_b = st.columns([1, 2])
            with col_a:
                sel_ntp_year = st.selectbox(
                    "Tahun", ntp_years, index=len(ntp_years) - 1, key="ntp_year"
                )
            with col_b:
                sel_ntp_provs = st.multiselect(
                    "Provinsi (kosong = semua)", ntp_provs, default=[], key="ntp_provs"
                )

            ntp_flt = ntp[ntp["tahun"] == sel_ntp_year]
            if sel_ntp_provs:
                ntp_flt = ntp_flt[ntp_flt["provinsi"].isin(sel_ntp_provs)]

            st.markdown(f"#### NTP {sel_ntp_year} — {len(ntp_flt)} Provinsi")

            # --- Bar chart sorted by NTP ---
            ntp_sorted = ntp_flt.sort_values("ntp", ascending=True)
            fig_ntp_bar = px.bar(
                ntp_sorted,
                x="ntp", y="provinsi", orientation="h",
                color="ntp",
                color_continuous_scale=["#d73027", "#fee08b", "#1a9850"],
                color_continuous_midpoint=100,
                labels={"ntp": "NTP (2018=100)", "provinsi": ""},
                title=f"NTP per Provinsi — {sel_ntp_year}",
            )
            fig_ntp_bar.add_vline(x=100, line_dash="dash", line_color="gray",
                                   annotation_text="NTP=100 (break-even)")
            fig_ntp_bar.update_layout(height=max(400, len(ntp_sorted) * 20),
                                       coloraxis_showscale=False)
            st.plotly_chart(fig_ntp_bar, use_container_width=True)

            st.divider()

            # --- NTP trend lines (multi-province) ---
            st.markdown("#### Tren NTP 2019–2024")
            ntp_trend_provs = sel_ntp_provs if sel_ntp_provs else ntp_provs[:10]
            ntp_trend = ntp[ntp["provinsi"].isin(ntp_trend_provs)].copy()
            if not ntp_trend.empty:
                fig_ntp_trend = px.line(
                    ntp_trend.sort_values(["provinsi", "tahun"]),
                    x="tahun", y="ntp", color="provinsi",
                    markers=True,
                    labels={"ntp": "NTP (2018=100)", "tahun": "Tahun"},
                    title="Tren NTP per Provinsi (2019–2024)",
                )
                fig_ntp_trend.add_hline(y=100, line_dash="dot", line_color="gray",
                                         annotation_text="Break-even")
                fig_ntp_trend.update_layout(height=420)
                st.plotly_chart(fig_ntp_trend, use_container_width=True)
                st.caption(
                    "Pilih provinsi spesifik di filter atas untuk membandingkan. "
                    "Default: 10 provinsi pertama (alphabetical)."
                )

            st.divider()

            # --- Heatmap NTP province × year ---
            st.markdown("#### Heatmap NTP: Provinsi × Tahun")
            ntp_heat = ntp.copy()
            if sel_ntp_provs:
                ntp_heat = ntp_heat[ntp_heat["provinsi"].isin(sel_ntp_provs)]
            ntp_pivot = ntp_heat.pivot_table(
                index="provinsi", columns="tahun", values="ntp"
            ).sort_index()
            if not ntp_pivot.empty:
                fig_heat = px.imshow(
                    ntp_pivot,
                    color_continuous_scale=["#d73027", "#fee08b", "#1a9850"],
                    color_continuous_midpoint=100,
                    aspect="auto",
                    labels={"color": "NTP", "x": "Tahun", "y": "Provinsi"},
                    title="Heatmap NTP (2018=100) — Hijau > 100 (surplus petani)",
                    text_auto=".1f",
                )
                fig_heat.update_layout(height=max(400, len(ntp_pivot) * 22))
                st.plotly_chart(fig_heat, use_container_width=True)

            # --- Summary stats ---
            st.divider()
            st.markdown("#### Statistik NTP Nasional (rata-rata provinsi)")
            ntp_nat = (
                ntp.groupby("tahun")["ntp"]
                .agg(["mean", "min", "max", "std"])
                .rename(columns={"mean": "Rata-rata", "min": "Min", "max": "Max", "std": "Std Dev"})
                .reset_index()
            )
            ntp_nat.columns = ["Tahun", "Rata-rata", "Min", "Max", "Std Dev"]
            for col in ["Rata-rata", "Min", "Max", "Std Dev"]:
                ntp_nat[col] = ntp_nat[col].round(2)
            st.dataframe(ntp_nat, use_container_width=True, hide_index=True)

            st.divider()
            st.download_button(
                "Unduh CSV NTP",
                ntp.to_csv(index=False).encode("utf-8"),
                file_name="ntp_petani.csv",
                mime="text/csv",
                key="dl_ntp",
            )

    # ===== TAB: PRODUKSI PANGAN =====
    with tabs[7]:
        st.subheader("Produksi Tanaman Pangan per Provinsi")
        st.caption(
            "Data produksi padi (2018–2024) dan jagung (2020–2024) per provinsi. "
            "Sumber: BPS Tabel Statis — Luas Panen, Produksi, dan Produktivitas."
        )

        if produksi is None or produksi.empty:
            st.info("Data produksi belum tersedia.")
        else:
            prod_komoditas = sorted(produksi["komoditas"].unique())
            prod_years = sorted(produksi["tahun"].unique())
            prod_provs = sorted(produksi["provinsi"].unique())

            col_a, col_b, col_c = st.columns(3)
            with col_a:
                sel_komoditas = st.selectbox(
                    "Komoditas", prod_komoditas, key="prod_komoditas"
                )
            with col_b:
                sel_prod_year = st.selectbox(
                    "Tahun", prod_years, index=len(prod_years) - 1, key="prod_year"
                )
            with col_c:
                sel_prod_metric = st.radio(
                    "Metrik", ["Produksi (ton)", "Luas Panen (ha)"],
                    horizontal=True, key="prod_metric"
                )

            metric_col = "produksi_ton" if "Produksi" in sel_prod_metric else "luas_panen_ha"
            metric_label = sel_prod_metric

            prod_flt = produksi[
                (produksi["komoditas"] == sel_komoditas) &
                (produksi["tahun"] == sel_prod_year)
            ].copy()

            if prod_flt.empty:
                st.warning(f"Data {sel_komoditas} {sel_prod_year} belum tersedia.")
            else:
                # --- KPI row ---
                kc1, kc2, kc3 = st.columns(3)
                kc1.metric(
                    f"Total {metric_label}",
                    f"{prod_flt[metric_col].sum():,.0f}"
                )
                kc2.metric("Provinsi ter-cover", f"{prod_flt['provinsi'].nunique()}")
                top_prov = prod_flt.loc[prod_flt[metric_col].idxmax(), "provinsi"]
                kc3.metric("Produksi Terbesar", top_prov)

                st.divider()

                # --- Bar chart: top provinces ---
                prod_sorted = prod_flt.sort_values(metric_col, ascending=True).tail(20)
                fig_prod_bar = px.bar(
                    prod_sorted,
                    x=metric_col, y="provinsi", orientation="h",
                    color=metric_col,
                    color_continuous_scale="Greens",
                    labels={metric_col: metric_label, "provinsi": ""},
                    title=f"Top Provinsi — {sel_komoditas} {sel_prod_year} ({metric_label})",
                )
                fig_prod_bar.update_layout(
                    height=max(400, len(prod_sorted) * 22),
                    coloraxis_showscale=False,
                )
                st.plotly_chart(fig_prod_bar, use_container_width=True)

                st.divider()

                # --- Trend line: all years for selected provinces ---
                st.markdown(f"#### Tren {metric_label} — {sel_komoditas}")
                prod_all_years = produksi[produksi["komoditas"] == sel_komoditas]
                top5_provs = (
                    prod_all_years.groupby("provinsi")[metric_col].mean()
                    .nlargest(5).index.tolist()
                )
                sel_trend_provs = st.multiselect(
                    "Pilih provinsi (default: top 5 rata-rata)",
                    prod_provs, default=top5_provs, key="prod_trend_provs"
                )
                if sel_trend_provs:
                    trend_data = prod_all_years[
                        prod_all_years["provinsi"].isin(sel_trend_provs)
                    ].sort_values(["provinsi", "tahun"])
                    fig_prod_trend = px.line(
                        trend_data,
                        x="tahun", y=metric_col, color="provinsi",
                        markers=True,
                        labels={metric_col: metric_label, "tahun": "Tahun"},
                        title=f"Tren {metric_label} — {sel_komoditas}",
                    )
                    fig_prod_trend.update_layout(height=420)
                    st.plotly_chart(fig_prod_trend, use_container_width=True)

                st.divider()

                # --- Comparison: Padi vs Jagung national totals ---
                st.markdown("#### Produksi Nasional: Padi vs Jagung")
                nat_prod = produksi.groupby(["komoditas", "tahun"])["produksi_ton"].sum().reset_index()
                fig_nat = px.line(
                    nat_prod, x="tahun", y="produksi_ton", color="komoditas",
                    markers=True,
                    labels={"produksi_ton": "Produksi (ton)", "tahun": "Tahun",
                            "komoditas": "Komoditas"},
                    title="Total Produksi Nasional: Padi vs Jagung (ton)",
                    color_discrete_map={"Padi": "#2196F3", "Jagung": "#FF9800"},
                )
                fig_nat.update_layout(height=380)
                st.plotly_chart(fig_nat, use_container_width=True)

            st.divider()
            st.download_button(
                "Unduh CSV Produksi Pangan",
                produksi.to_csv(index=False).encode("utf-8"),
                file_name="produksi_pangan.csv",
                mime="text/csv",
                key="dl_produksi",
            )

    # ===== TAB: PERBANDINGAN PROVINSI =====
    with tabs[8]:
        st.subheader("Perbandingan Provinsi — Multi-Indikator")
        st.caption("Bandingkan 2–5 provinsi secara bersamaan di 5 indikator utama.")

        # Default: top 5 provinsi berdasarkan kredit
        if not kr_f.empty:
            top5_default = (kr_f[kr_f["jenis_kredit"] == "Total"]
                            .groupby("provinsi")["nilai_miliar_rp"].sum()
                            .nlargest(5).index.tolist())
        else:
            top5_default = []

        all_provs_cmp = sorted(
            set(kr_f["provinsi"]) | set(ek_f["provinsi"])
            | set((ntp["provinsi"] if ntp is not None and not ntp.empty else pd.Series([], dtype=str)))
            | set((produksi["provinsi"] if produksi is not None and not produksi.empty else pd.Series([], dtype=str)))
            | set((pdrb["provinsi"] if pdrb is not None and not pdrb.empty else pd.Series([], dtype=str)))
        )
        sel_cmp_provs = st.multiselect(
            "Pilih provinsi (2–5)",
            all_provs_cmp,
            default=[p for p in top5_default if p in all_provs_cmp],
            key="cmp_provs",
        )

        if len(sel_cmp_provs) < 2:
            st.info("Pilih minimal 2 provinsi untuk perbandingan.")
        else:
            if len(sel_cmp_provs) > 5:
                st.warning("Maksimal 5 provinsi. Menampilkan 5 pertama.")
                sel_cmp_provs = sel_cmp_provs[:5]

            # Get latest year for each indicator
            latest_kr_yr = int(kr_f["tahun"].max()) if not kr_f.empty else None
            latest_ek_yr = int(ek_f["tahun"].max()) if not ek_f.empty else None
            latest_ntp_yr = int(ntp["tahun"].max()) if ntp is not None and not ntp.empty else None
            latest_prod_yr = int(produksi["tahun"].max()) if produksi is not None and not produksi.empty else None
            latest_pdrb_yr = int(pdrb["tahun"].max()) if pdrb is not None and not pdrb.empty else None

            st.markdown("### Grouped Bar Charts per Indikator")

            # 1. Kredit
            if not kr_f.empty:
                kr_cmp = (kr_f[(kr_f["jenis_kredit"] == "Total") & (kr_f["provinsi"].isin(sel_cmp_provs))]
                          .groupby(["provinsi", "tahun"])["nilai_miliar_rp"].sum().reset_index())
                if not kr_cmp.empty:
                    fig_kr_cmp = px.bar(
                        kr_cmp, x="provinsi", y="nilai_miliar_rp", color="tahun",
                        barmode="group",
                        title="Kredit per Provinsi (Rp Miliar)",
                        labels={"nilai_miliar_rp": "Rp Miliar", "provinsi": "Provinsi", "tahun": "Tahun"},
                        color_continuous_scale="Blues",
                    )
                    fig_kr_cmp.update_layout(height=400)
                    st.plotly_chart(fig_kr_cmp, use_container_width=True)

            # 2. Ekspor
            if not ek_f.empty:
                ek_cmp = (ek_f[ek_f["provinsi"].isin(sel_cmp_provs)]
                          .groupby(["provinsi", "tahun"])["nilai_juta_usd"].sum().reset_index())
                if not ek_cmp.empty:
                    fig_ek_cmp = px.bar(
                        ek_cmp, x="provinsi", y="nilai_juta_usd", color="tahun",
                        barmode="group",
                        title="Ekspor per Provinsi (Juta USD)",
                        labels={"nilai_juta_usd": "Juta USD", "provinsi": "Provinsi", "tahun": "Tahun"},
                        color_continuous_scale="Blues",
                    )
                    fig_ek_cmp.update_layout(height=400)
                    st.plotly_chart(fig_ek_cmp, use_container_width=True)

            # 3. NTP
            if ntp is not None and not ntp.empty:
                ntp_cmp = ntp[ntp["provinsi"].isin(sel_cmp_provs)].copy()
                if not ntp_cmp.empty:
                    fig_ntp_cmp = px.bar(
                        ntp_cmp, x="provinsi", y="ntp", color="tahun",
                        barmode="group",
                        title="NTP per Provinsi (2018=100)",
                        labels={"ntp": "NTP", "provinsi": "Provinsi", "tahun": "Tahun"},
                        color_continuous_scale="Blues",
                    )
                    fig_ntp_cmp.update_layout(height=400)
                    st.plotly_chart(fig_ntp_cmp, use_container_width=True)

            # 4. Produksi Padi
            if produksi is not None and not produksi.empty:
                prod_cmp = (produksi[(produksi["komoditas"] == "Padi") & (produksi["provinsi"].isin(sel_cmp_provs))]
                            .groupby(["provinsi", "tahun"])["produksi_ton"].sum().reset_index())
                if not prod_cmp.empty:
                    fig_prod_cmp = px.bar(
                        prod_cmp, x="provinsi", y="produksi_ton", color="tahun",
                        barmode="group",
                        title="Produksi Padi per Provinsi (ton)",
                        labels={"produksi_ton": "Produksi (ton)", "provinsi": "Provinsi", "tahun": "Tahun"},
                        color_continuous_scale="Greens",
                    )
                    fig_prod_cmp.update_layout(height=400)
                    st.plotly_chart(fig_prod_cmp, use_container_width=True)

            # 5. PDRB
            if pdrb is not None and not pdrb.empty:
                pdrb_cmp = (pdrb[(pdrb["jenis_harga"] == "Berlaku") & (pdrb["provinsi"].isin(sel_cmp_provs))]
                            .groupby(["provinsi", "tahun"])["nilai_miliar_rp"].sum().reset_index())
                if not pdrb_cmp.empty:
                    fig_pdrb_cmp = px.bar(
                        pdrb_cmp, x="provinsi", y="nilai_miliar_rp", color="tahun",
                        barmode="group",
                        title="PDRB per Provinsi (Rp Miliar, Harga Berlaku)",
                        labels={"nilai_miliar_rp": "Rp Miliar", "provinsi": "Provinsi", "tahun": "Tahun"},
                        color_continuous_scale="Purples",
                    )
                    fig_pdrb_cmp.update_layout(height=400)
                    st.plotly_chart(fig_pdrb_cmp, use_container_width=True)

            st.divider()

            # ----- Radar Chart (normalized 0-100) -----
            st.markdown("### Radar Chart — Skor Ternormalisasi (0-100)")
            st.caption("Nilai ternormalisasi: 100 = tertinggi di antara provinsi terpilih, 0 = terendah.")

            radar_data = {}
            indicators_radar = []

            if not kr_f.empty and latest_kr_yr:
                kr_latest = (kr_f[(kr_f["jenis_kredit"] == "Total") & (kr_f["tahun"] == latest_kr_yr) & (kr_f["provinsi"].isin(sel_cmp_provs))]
                             .groupby("provinsi")["nilai_miliar_rp"].sum())
                for p in sel_cmp_provs:
                    radar_data.setdefault(p, {})["Kredit"] = float(kr_latest.get(p, 0))
                indicators_radar.append("Kredit")

            if not ek_f.empty and latest_ek_yr:
                ek_latest = (ek_f[(ek_f["tahun"] == latest_ek_yr) & (ek_f["provinsi"].isin(sel_cmp_provs))]
                             .groupby("provinsi")["nilai_juta_usd"].sum())
                for p in sel_cmp_provs:
                    radar_data.setdefault(p, {})["Ekspor"] = float(ek_latest.get(p, 0))
                indicators_radar.append("Ekspor")

            if ntp is not None and not ntp.empty and latest_ntp_yr:
                ntp_latest = (ntp[(ntp["tahun"] == latest_ntp_yr) & (ntp["provinsi"].isin(sel_cmp_provs))]
                              .set_index("provinsi")["ntp"])
                for p in sel_cmp_provs:
                    radar_data.setdefault(p, {})["NTP"] = float(ntp_latest.get(p, 0))
                indicators_radar.append("NTP")

            if produksi is not None and not produksi.empty and latest_prod_yr:
                prod_latest = (produksi[(produksi["komoditas"] == "Padi") & (produksi["tahun"] == latest_prod_yr) & (produksi["provinsi"].isin(sel_cmp_provs))]
                               .groupby("provinsi")["produksi_ton"].sum())
                for p in sel_cmp_provs:
                    radar_data.setdefault(p, {})["Produksi Padi"] = float(prod_latest.get(p, 0))
                indicators_radar.append("Produksi Padi")

            if pdrb is not None and not pdrb.empty and latest_pdrb_yr:
                pdrb_latest = (pdrb[(pdrb["jenis_harga"] == "Berlaku") & (pdrb["tahun"] == latest_pdrb_yr) & (pdrb["provinsi"].isin(sel_cmp_provs))]
                               .groupby("provinsi")["nilai_miliar_rp"].sum())
                for p in sel_cmp_provs:
                    radar_data.setdefault(p, {})["PDRB"] = float(pdrb_latest.get(p, 0))
                indicators_radar.append("PDRB")

            if indicators_radar and radar_data:
                radar_df = pd.DataFrame(radar_data).T.fillna(0)
                # Normalize each indicator 0-100
                for ind in indicators_radar:
                    if ind in radar_df.columns:
                        col_max = radar_df[ind].max()
                        col_min = radar_df[ind].min()
                        if col_max > col_min:
                            radar_df[ind] = ((radar_df[ind] - col_min) / (col_max - col_min) * 100).round(1)
                        else:
                            radar_df[ind] = 50.0

                fig_radar = go.Figure()
                colors_radar = ["#1976D2", "#D32F2F", "#2E7D32", "#FF9800", "#7B1FA2"]
                for i, prov in enumerate(sel_cmp_provs):
                    if prov in radar_df.index:
                        vals = [radar_df.loc[prov, ind] for ind in indicators_radar]
                        vals_closed = vals + [vals[0]]
                        inds_closed = indicators_radar + [indicators_radar[0]]
                        fig_radar.add_trace(go.Scatterpolar(
                            r=vals_closed, theta=inds_closed,
                            fill="toself", name=prov,
                            line_color=colors_radar[i % len(colors_radar)],
                            opacity=0.7,
                        ))
                fig_radar.update_layout(
                    polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                    showlegend=True, height=500,
                    title="Radar Chart — Skor Ternormalisasi per Indikator",
                )
                st.plotly_chart(fig_radar, use_container_width=True)

            st.divider()

            # ----- Summary Table -----
            st.markdown("### Tabel Ringkasan — Nilai Terbaru per Indikator")
            summary_rows = []
            for p in sel_cmp_provs:
                row = {"Provinsi": p}
                if not kr_f.empty and latest_kr_yr:
                    v = kr_f[(kr_f["jenis_kredit"] == "Total") & (kr_f["tahun"] == latest_kr_yr) & (kr_f["provinsi"] == p)]["nilai_miliar_rp"].sum()
                    row[f"Kredit {latest_kr_yr} (Rp M)"] = round(v, 1)
                if not ek_f.empty and latest_ek_yr:
                    v = ek_f[(ek_f["tahun"] == latest_ek_yr) & (ek_f["provinsi"] == p)]["nilai_juta_usd"].sum()
                    row[f"Ekspor {latest_ek_yr} (Juta USD)"] = round(v, 2)
                if ntp is not None and not ntp.empty and latest_ntp_yr:
                    v_series = ntp[(ntp["tahun"] == latest_ntp_yr) & (ntp["provinsi"] == p)]["ntp"]
                    row[f"NTP {latest_ntp_yr}"] = round(float(v_series.iloc[0]), 2) if not v_series.empty else None
                if produksi is not None and not produksi.empty and latest_prod_yr:
                    v = produksi[(produksi["komoditas"] == "Padi") & (produksi["tahun"] == latest_prod_yr) & (produksi["provinsi"] == p)]["produksi_ton"].sum()
                    row[f"Produksi Padi {latest_prod_yr} (ton)"] = round(v, 0)
                if pdrb is not None and not pdrb.empty and latest_pdrb_yr:
                    v = pdrb[(pdrb["jenis_harga"] == "Berlaku") & (pdrb["tahun"] == latest_pdrb_yr) & (pdrb["provinsi"] == p)]["nilai_miliar_rp"].sum()
                    row[f"PDRB {latest_pdrb_yr} (Rp M)"] = round(v, 1)
                summary_rows.append(row)

            if summary_rows:
                summary_df = pd.DataFrame(summary_rows)
                st.dataframe(summary_df, use_container_width=True, hide_index=True)

    # ===== TAB: DATA MENTAH =====
    with tabs[9]:
        st.subheader("Tabel Data Lengkap")
        ds = st.selectbox("Pilih dataset", ["Kredit", "Ekspor", "Impor", "NTP", "Produksi Pangan"],
                          key="data_mentah_ds")
        df = {"Kredit": kr_f, "Ekspor": ek_f, "Impor": im_f,
              "NTP": ntp if ntp is not None else pd.DataFrame(),
              "Produksi Pangan": produksi if produksi is not None else pd.DataFrame()}[ds]
        st.dataframe(df, use_container_width=True, height=500)
        st.download_button(
            f"Unduh CSV ({ds})",
            df.to_csv(index=False).encode("utf-8"),
            file_name=f"{ds.lower().replace(' ', '_')}_filtered.csv",
            mime="text/csv",
            key="dl_data_mentah",
        )

    # ===== TAB: SUMBER DATA =====
    with tabs[10]:
        st.subheader("Status & Sumber Data Resmi")
        for name, info in status.items():
            with st.container(border=True):
                st.markdown(f"### {name.title()}")
                cols = st.columns(4)
                cols[0].metric("Total rows", f"{info['total']:,}")
                cols[1].metric("Provinsi", f"{info.get('provinces', 0)}")
                cols[2].metric("Tahun ter-cover", f"{info.get('year_count', 0)}")
                cols[3].metric("Periode",
                                f"{info.get('year_min','-')}-{info.get('year_max','-')}")
                if info.get("year_min") is not None:
                    st.caption(f"Periode: {info['year_min']}–{info['year_max']}")

        st.markdown("---")
        st.markdown(
            """
### Sumber Data Resmi yang Sudah Terhubung

**1. Kredit Sektor Pertanian** — `data/raw/bi_sekda_consolidated.csv`
- Sumber: [OJK Statistik Perbankan Indonesia](https://ojk.go.id/id/kanal/perbankan/data-dan-statistik/statistik-perbankan-indonesia/default.aspx) Desember 2015–2024
- Sheet: `Kredit LU per Lok.Dati I_X.X.a.` (kredit menurut lapangan usaha per provinsi)
- Mencakup kolom **Pertanian, Perburuan & Kehutanan** + **Perikanan**
- Coverage: 33 provinsi × 10 tahun (2015–2024). 2014 tidak tersedia di archive OJK; 4 pemekaran 2022 belum dipisah.

**2. Ekspor Pertanian** — `data/raw/bps/ekspor_pertanian_{YYYY}.csv`
- Sumber: [BPS — Ekspor Indonesia Menurut Provinsi Asal Barang](https://www.bps.go.id/id/publication?keyword=ekspor+menurut+provinsi) 2014–2024
- 9 publikasi tahunan (tiap publikasi 3 tahun overlapping, dedup newest-pub-wins)
- Sektor "Pertanian, Kehutanan & Perikanan" per provinsi
- Coverage: 11 tahun (2014–2024), provinsi bertambah dari 11 (2014) → 33–34 (2018–2024)

**3. Impor Pertanian** — `data/raw/bps/impor_pertanian_{YYYY}.csv`
- Sumber: [BPS — Statistik Perdagangan Luar Negeri Impor Buku II](https://www.bps.go.id/id/publication?keyword=Impor+Jilid+II) 2024
- Lampiran 6: Impor Menurut Provinsi dan Golongan Barang (HS) 2 Digit
- Filter HS 01–24 (klasifikasi pertanian WTO/FAO)
- Coverage saat ini: **2023, 2024 saja** (2014–2022 publikasi pakai struktur Lampiran berbeda)

**4. Produksi Tanaman Pangan** — `data/raw/bps/produksi/`
- Sumber: [BPS Tabel Statis — Luas Panen, Produksi, dan Produktivitas](https://www.bps.go.id/id/statistics-table/2/)
- Dua komoditas: **Padi** (2018–2024, 34–38 provinsi/tahun) dan **Jagung** (2020–2024, 33–37 provinsi/tahun)
- Discrape via React fiber traversal dari BPS Tabel Statis (MTQ5OCMy = Padi, MjIwNCMy = Jagung)
- Catatan: 2018 jagung tidak tersedia di BPS Tabel Statis (dropdown hanya 2020–2024)

**5. Nilai Tukar Petani (NTP)** — `data/raw/bps/ntp/ntp_per_provinsi_2019_2024.csv`
- Sumber: [BPS via Jabarprov OpenData](https://opendata.jabarprov.go.id/id/dataset/nilai-tukar-petani-ntp-berdasarkan-provinsi-di-indonesia)
- Basis indeks: **2018=100**
- NTP > 100 = petani surplus (harga jual > harga beli); NTP < 100 = defisit
- Coverage: 34 provinsi 2019–2023, 38 provinsi 2024 (termasuk 4 pemekaran Papua)
- Catatan: 11 data-point dikoreksi (nilai "1.xx" → "101.xx" akibat bug desimal di sumber)

### Re-jalankan Ingestion

```bash
# Ekspor (parse 9 PDF BPS):
python -m src.ingest.bps_pdf_batch

# Impor (parse Lampiran 6 dari Buku II 2024):
python -m src.ingest.bps_impor_batch

# Kredit (parse 10 OJK SPI XLSX):
python -m src.ingest.ojk_batch
```
"""
        )


if __name__ == "__main__":
    main()
