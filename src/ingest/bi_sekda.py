"""BI SEKDA loader (manual download required).

Source: https://www.bi.go.id/id/statistik/ekonomi-keuangan/sekda/default.aspx

The BI website blocks automated scraping. Users must:
  1. Visit the URL above
  2. Pick each province > download the "Posisi Pinjaman Bank Umum
     menurut Lapangan Usaha" Excel files (one per period)
  3. Save the Excel files into data/raw/bi_sekda/ with naming pattern:
        {provinsi_slug}_{YYYY}.xlsx
     e.g. jawa_barat_2023.xlsx

This loader reads those Excel files and produces a normalized DataFrame
matching the kredit schema.

It also accepts a single consolidated CSV at
data/raw/bi_sekda_consolidated.csv with columns:
    tahun, provinsi, jenis_kredit, nilai_miliar_rp
which is much easier to maintain manually if you only need annual data.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.provinces import PROVINCE_NAMES

CONSOLIDATED_FILE = "bi_sekda_consolidated.csv"


def load_consolidated(raw_dir: Path) -> pd.DataFrame:
    """Load the user-maintained consolidated CSV if it exists."""
    f = raw_dir / CONSOLIDATED_FILE
    if not f.exists():
        return pd.DataFrame(columns=[
            "tahun", "provinsi", "jenis_kredit", "nilai_miliar_rp",
            "sumber", "status",
        ])
    df = pd.read_csv(f)
    required = {"tahun", "provinsi", "jenis_kredit", "nilai_miliar_rp"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{CONSOLIDATED_FILE} missing columns: {missing}")
    df["sumber"] = df.get("sumber", "BI SEKDA")
    df["status"] = df.get("status", "real")
    df["provinsi"] = df["provinsi"].str.strip()
    unknown = set(df["provinsi"]) - set(PROVINCE_NAMES)
    if unknown:
        print(f"[bi_sekda] WARNING — unknown provinces in CSV: {unknown}")
    return df


def template_csv(raw_dir: Path, years: range, jenis: list[str]) -> Path:
    """Create an empty template CSV with all (tahun, provinsi, jenis_kredit) keys."""
    rows = []
    for y in years:
        for prov in PROVINCE_NAMES:
            for jk in jenis:
                rows.append({
                    "tahun": y, "provinsi": prov, "jenis_kredit": jk,
                    "nilai_miliar_rp": "", "sumber": "BI SEKDA", "status": "kosong",
                })
    df = pd.DataFrame(rows)
    out = raw_dir / "bi_sekda_TEMPLATE.csv"
    raw_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    return out
