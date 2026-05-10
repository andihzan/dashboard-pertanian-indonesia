"""BPS Ekspor/Impor Pertanian loader (manual download required).

Source: BPS publication "Ekspor Indonesia Menurut Provinsi Asal Barang"
        (annual, 2014-2024) — https://www.bps.go.id

For 2014-2016 there is NO Kementan portal coverage, so BPS publications
are the only official provincial-level source.

Workflow:
  1. Download the annual publications from BPS for years 2014-2016.
  2. From each PDF/Excel, extract the table "Nilai/Volume Ekspor Sektor
     Pertanian Menurut Provinsi Asal".
  3. Save as data/raw/bps/ekspor_pertanian_{YYYY}.csv with columns:
        provinsi, subsektor, volume_ton, nilai_juta_usd

This loader reads those CSVs and concatenates them.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.provinces import PROVINCE_NAMES


def load_ekspor(raw_dir: Path) -> pd.DataFrame:
    files = sorted(raw_dir.glob("ekspor_pertanian_*.csv"))
    frames = []
    for f in files:
        try:
            year = int(f.stem.split("_")[-1])
        except ValueError:
            continue
        df = pd.read_csv(f)
        df["tahun"] = year
        df["sumber"] = "BPS"
        df["status"] = "real"
        frames.append(df)
    if not frames:
        return pd.DataFrame(columns=[
            "tahun", "provinsi", "subsektor", "volume_ton",
            "nilai_juta_usd", "sumber", "status",
        ])
    return pd.concat(frames, ignore_index=True)


def load_impor(raw_dir: Path) -> pd.DataFrame:
    files = sorted(raw_dir.glob("impor_pertanian_*.csv"))
    frames = []
    for f in files:
        try:
            year = int(f.stem.split("_")[-1])
        except ValueError:
            continue
        df = pd.read_csv(f)
        df["tahun"] = year
        df["sumber"] = "BPS"
        df["status"] = "real"
        frames.append(df)
    if not frames:
        return pd.DataFrame(columns=[
            "tahun", "provinsi", "subsektor", "volume_ton",
            "nilai_juta_usd", "sumber", "status",
        ])
    return pd.concat(frames, ignore_index=True)
