"""Batch parse OJK SPI Desember 2015-2024."""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from src.ingest.ojk_spi_parser import parse_ojk_spi

ROOT = Path(__file__).resolve().parents[2]
OJK_DIR = ROOT / "data" / "raw" / "ojk"
RAW = ROOT / "data" / "raw"


def _find_xlsx_for_year(year: int) -> Path | None:
    """Locate the OJK SPI XLSX file for a given year."""
    candidates = [
        OJK_DIR / f"spi_des_{year}.xlsx",
        OJK_DIR / f"spi_des_{year}_extracted",
    ]
    for c in candidates:
        if c.is_file() and c.suffix == ".xlsx":
            return c
        if c.is_dir():
            for f in c.iterdir():
                if f.suffix == ".xlsx":
                    return f
    return None


def main():
    all_frames = []
    summary = []
    for year in range(2015, 2025):
        path = _find_xlsx_for_year(year)
        if not path:
            print(f"[SKIP] {year}")
            summary.append({"year": year, "rows": 0, "provs": 0, "error": "file_not_found"})
            continue
        print(f"==> {year}: {path.name}")
        try:
            df = parse_ojk_spi(path, year)
        except Exception as e:
            print(f"  [ERROR] {e}")
            summary.append({"year": year, "rows": 0, "provs": 0, "error": str(e)})
            continue
        if df.empty:
            print(f"  [WARN] empty")
            summary.append({"year": year, "rows": 0, "provs": 0, "error": "empty"})
            continue
        provs = df["provinsi"].nunique()
        print(f"  parsed {len(df)} rows | {provs} provinces")
        summary.append({"year": year, "rows": len(df), "provs": provs, "error": ""})
        all_frames.append(df)

    if not all_frames:
        print("No data parsed!")
        return

    combined = pd.concat(all_frames, ignore_index=True)
    print(f"\nTotal: {len(combined)} rows")
    print("\nCoverage:")
    print(combined.groupby("tahun")["provinsi"].nunique().to_string())

    # Save consolidated CSV (as expected by bi_sekda loader)
    out_path = RAW / "bi_sekda_consolidated.csv"
    cols = ["tahun", "provinsi", "jenis_kredit", "nilai_miliar_rp", "sumber", "status"]
    combined[cols].to_csv(out_path, index=False)
    print(f"\nSaved {out_path} ({len(combined)} rows)")

    print("\n=== Summary ===")
    print(pd.DataFrame(summary).to_string(index=False))


if __name__ == "__main__":
    main()
