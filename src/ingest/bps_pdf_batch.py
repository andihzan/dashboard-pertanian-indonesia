"""Batch-parse semua publikasi BPS ekspor menurut provinsi.

Iterasi dari publikasi TERBARU ke terlama. Untuk (tahun, provinsi) yang
overlap, publikasi terbaru menang (data retrospektif lebih akurat
karena revisi).

Run:
  python -m src.ingest.bps_pdf_batch
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from src.ingest.bps_pdf_parser import parse_publication, save_per_year

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data" / "raw" / "bps" / "source"
OUTPUT = ROOT / "data" / "raw" / "bps"

# Process newest-first so newer publications take precedence
PUB_PRIORITY = [2024, 2023, 2022, 2021, 2020, 2019, 2018, 2017, 2015]


def main():
    all_frames = []
    summary = []
    for pub_year in PUB_PRIORITY:
        pdf_path = SOURCE / f"bps_ekspor_provinsi_{pub_year}.pdf"
        if not pdf_path.exists():
            print(f"[SKIP] {pdf_path} not found")
            continue
        print(f"\n==> Parsing {pdf_path.name} ({pdf_path.stat().st_size//1024} KB)")
        try:
            df = parse_publication(pdf_path, verbose=False)
        except Exception as e:
            print(f"[ERROR] {pdf_path.name}: {e}")
            summary.append({"publikasi": pub_year, "rows": 0, "provinces": 0,
                            "years": "", "error": str(e)})
            continue
        if df.empty:
            print(f"   [WARN] empty result — format may differ for this year")
            summary.append({"publikasi": pub_year, "rows": 0, "provinces": 0,
                            "years": "[]", "error": "empty"})
            continue
        df["pub_year"] = pub_year
        years = sorted(df["tahun"].unique().tolist())
        provs = df["provinsi"].nunique()
        print(f"   parsed {len(df)} rows | {provs} provinces | years {years}")
        summary.append({"publikasi": pub_year, "rows": len(df),
                        "provinces": provs, "years": str(years), "error": ""})
        all_frames.append(df)

    if not all_frames:
        print("\nNo data parsed!")
        return

    combined = pd.concat(all_frames, ignore_index=True)
    print(f"\nTotal raw: {len(combined)} rows across all publications")

    # Dedup: keep first occurrence (publications are sorted newest-first,
    # so first occurrence = newest publication's value)
    deduped = combined.drop_duplicates(
        subset=["tahun", "provinsi"], keep="first"
    )
    print(f"After dedup (newest pub wins): {len(deduped)} rows")
    print("\nCoverage by year:")
    print(deduped.groupby("tahun")["provinsi"].nunique().to_string())

    # Save per-year files
    for_save = deduped[["tahun", "provinsi", "subsektor", "volume_ton",
                         "nilai_juta_usd", "sumber", "status"]].copy()
    saved = save_per_year(for_save, OUTPUT)
    print(f"\nSaved {len(saved)} year files:")
    for y, p in saved.items():
        print(f"  {y}: {p}")

    # Print summary
    print("\n=== Summary per publikasi ===")
    print(pd.DataFrame(summary).to_string(index=False))


if __name__ == "__main__":
    main()
