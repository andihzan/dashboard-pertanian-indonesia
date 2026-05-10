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
    tabs = st.tabs(["Ringkasan", "Kredit", "Ekspor", "Impor", "Analytics",
                    "NTP Petani", "Produksi Pangan", "Data Mentah", "Sumber Data"])

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

    # ===== TAB: ANALYTICS =====
    with tabs[4]:
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

    # ===== TAB: NTP PETANI =====
    with tabs[5]:
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

    # ===== TAB: PRODUKSI PANGAN =====
    with tabs[6]:
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

    # ===== TAB: DATA MENTAH =====
    with tabs[7]:
        st.subheader("Tabel Data Lengkap")
        ds = st.selectbox("Pilih dataset", ["Kredit", "Ekspor", "Impor", "Produksi Pangan"])
        df = {"Kredit": kr_f, "Ekspor": ek_f, "Impor": im_f,
              "Produksi Pangan": produksi}[ds]
        st.dataframe(df, use_container_width=True, height=500)
        st.download_button(
            f"Unduh CSV ({ds})",
            df.to_csv(index=False).encode("utf-8"),
            file_name=f"{ds.lower()}_filtered.csv",
            mime="text/csv",
        )

    # ===== TAB: SUMBER DATA =====
    with tabs[8]:
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
