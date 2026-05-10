"""Unified data loader (real-data-only mode).

Loads only real data from data/raw/. Demo CSVs di data/sample/ tidak
di-load lagi sejak versi ini — dashboard sekarang murni berbasis data
resmi (BPS, OJK, Bank Indonesia).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.ingest.bi_sekda import load_consolidated as load_bi_kredit
from src.ingest.bps_ekspor import load_ekspor as load_bps_ekspor
from src.ingest.bps_ekspor import load_impor as load_bps_impor
from src.schema import EKSPOR_COLUMNS, IMPOR_COLUMNS, KREDIT_COLUMNS

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"


def load_kredit() -> pd.DataFrame:
    """Kredit pertanian per provinsi (real only).

    Source: data/raw/bi_sekda_consolidated.csv (dari OJK SPI Desember
    2015–2024).
    """
    real = load_bi_kredit(RAW)
    if real.empty:
        return pd.DataFrame(columns=KREDIT_COLUMNS)
    return real[KREDIT_COLUMNS].copy()


def load_ekspor() -> pd.DataFrame:
    """Ekspor pertanian per provinsi (real only).

    Source: data/raw/bps/ekspor_pertanian_{YYYY}.csv (dari publikasi BPS
    "Ekspor Indonesia Menurut Provinsi Asal Barang" 2014–2024).
    """
    bps = load_bps_ekspor(RAW / "bps")
    if bps.empty:
        return pd.DataFrame(columns=EKSPOR_COLUMNS)
    return bps[EKSPOR_COLUMNS].copy()


def load_impor() -> pd.DataFrame:
    """Impor pertanian per provinsi pelabuhan bongkar (real only).

    Source: data/raw/bps/impor_pertanian_{YYYY}.csv (dari Lampiran 6
    BPS "Statistik Perdagangan Luar Negeri Indonesia Impor" Buku II 2024).
    Coverage saat ini: 2023, 2024 only.
    """
    bps = load_bps_impor(RAW / "bps")
    if bps.empty:
        return pd.DataFrame(columns=IMPOR_COLUMNS)
    return bps[IMPOR_COLUMNS].copy()


def load_pdrb() -> pd.DataFrame:
    """PDRB sektor pertanian, kehutanan, perikanan per provinsi.

    Source: data/raw/bps_pdrb_consolidated.csv (dari publikasi BPS PDRB
    Provinsi-Provinsi Menurut Lapangan Usaha 2014-2024).
    Returns DataFrame with columns:
        tahun, provinsi, jenis_harga ("Berlaku"|"Konstan"),
        nilai_miliar_rp, sumber, status
    """
    pdrb_path = RAW / "bps_pdrb_consolidated.csv"
    if not pdrb_path.exists():
        return pd.DataFrame()
    df = pd.read_csv(pdrb_path)
    return df


def load_ntp() -> pd.DataFrame:
    """Nilai Tukar Petani (NTP) per provinsi, basis 2018=100.

    Source: data/raw/bps/ntp/ntp_per_provinsi_2019_2024.csv
    (dari API Jabarprov OpenData, bersumber BPS, 2019-2024).
    Returns DataFrame with columns:
        tahun, provinsi, ntp, sumber, status
    """
    ntp_path = RAW / "bps" / "ntp" / "ntp_per_provinsi_2019_2024.csv"
    if not ntp_path.exists():
        return pd.DataFrame()
    df = pd.read_csv(ntp_path)
    return df


def load_produksi() -> pd.DataFrame:
    """Produksi tanaman pangan (padi & jagung) per provinsi dari BPS.

    Source:
      - data/raw/bps/produksi/produksi_padi_2018_2024.csv   (BPS Tabel Statis)
      - data/raw/bps/produksi/produksi_jagung_2020_2024.csv (BPS Tabel Statis)

    Returns DataFrame with columns:
        tahun, provinsi, komoditas, luas_panen_ha, produksi_ton, sumber, status
    """
    produksi_dir = RAW / "bps" / "produksi"
    frames = []
    commodity_map = {
        "produksi_padi_2018_2024.csv": "Padi",
        "produksi_jagung_2020_2024.csv": "Jagung",
    }
    for fname, komoditas in commodity_map.items():
        fpath = produksi_dir / fname
        if not fpath.exists():
            continue
        df = pd.read_csv(fpath)
        df["komoditas"] = komoditas
        df["sumber"] = "BPS"
        df["status"] = "real"
        frames.append(df)

    if not frames:
        return pd.DataFrame(columns=[
            "tahun", "provinsi", "komoditas", "luas_panen_ha",
            "produksi_ton", "sumber", "status",
        ])

    result = pd.concat(frames, ignore_index=True)
    return result[[
        "tahun", "provinsi", "komoditas", "luas_panen_ha",
        "produksi_ton", "sumber", "status",
    ]]


def data_status() -> dict[str, dict]:
    """Summarize coverage per dataset (all official sources)."""
    out = {}

    # --- Kredit, Ekspor, Impor ---
    for name, loader in [("kredit", load_kredit), ("ekspor", load_ekspor),
                          ("impor", load_impor)]:
        df = loader()
        if df.empty:
            out[name] = {"total": 0, "year_min": None, "year_max": None,
                          "provinces": 0, "year_count": 0}
            continue
        out[name] = {
            "total": len(df),
            "year_min": int(df["tahun"].min()),
            "year_max": int(df["tahun"].max()),
            "year_count": int(df["tahun"].nunique()),
            "provinces": int(df["provinsi"].nunique()),
        }

    # --- NTP ---
    ntp = load_ntp()
    if ntp.empty:
        out["ntp"] = {"total": 0, "year_min": None, "year_max": None,
                       "provinces": 0, "year_count": 0}
    else:
        out["ntp"] = {
            "total": len(ntp),
            "year_min": int(ntp["tahun"].min()),
            "year_max": int(ntp["tahun"].max()),
            "year_count": int(ntp["tahun"].nunique()),
            "provinces": int(ntp["provinsi"].nunique()),
        }

    # --- Produksi per komoditas (Padi, Jagung) ---
    produksi = load_produksi()
    for komoditas in ["Padi", "Jagung"]:
        key = komoditas.lower()
        sub = produksi[produksi["komoditas"] == komoditas] if not produksi.empty else pd.DataFrame()
        if sub.empty:
            out[key] = {"total": 0, "year_min": None, "year_max": None,
                         "provinces": 0, "year_count": 0}
        else:
            out[key] = {
                "total": len(sub),
                "year_min": int(sub["tahun"].min()),
                "year_max": int(sub["tahun"].max()),
                "year_count": int(sub["tahun"].nunique()),
                "provinces": int(sub["provinsi"].nunique()),
            }

    return out
