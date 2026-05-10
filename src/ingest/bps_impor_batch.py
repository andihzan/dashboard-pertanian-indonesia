"""Batch-parse semua publikasi BPS Impor Jilid II 2014-2024.

Setiap PDF cover 2 tahun. Order newest-first untuk dedup.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.ingest.bps_impor_parser import parse_publication, save_per_year

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data" / "raw" / "bps" / "source" / "impor"
OUTPUT = ROOT / "data" / "raw" / "bps"

PUB_YEARS = [2024, 2023, 2022, 2021, 2020, 2019, 2018, 2017, 2016, 2015, 2014]


def main():
    all_frames = []
    summary = []
    for pub_year in PUB_YEARS:
        pdf_path = SOURCE / f"bps_impor_jilid_ii_{pub_year}.pdf"
        if not pdf_path.exists():
            print(f"[SKIP] {pdf_path}")
            continue
        size_kb = pdf_path.stat().st_size // 1024
        print(f"\n==> Parsing {pdf_path.name} ({size_kb} KB)")
        try:
            df = parse_publication(pdf_path, verbose=False)
        except Exception as e:
            print(f"  [ERROR] {e}")
            summary.append({"pub": pub_year, "rows": 0, "provinces": 0,
                            "years": "", "error": str(e)})
            continue
        if df.empty:
            print(f"  [WARN] empty")
            summary.append({"pub": pub_year, "rows": 0, "provinces": 0,
                            "years": "", "error": "empty"})
            continue
        df["pub_year"] = pub_year
        years = sorted(df["tahun"].unique().tolist())
        provs = df["provinsi"].nunique()
        print(f"  parsed {len(df)} rows | {provs} provinces | years {years}")
        summary.append({"pub": pub_year, "rows": len(df),
                        "provinces": provs, "years": str(years), "error": ""})
        all_frames.append(df)

    if not all_frames:
        print("\nNo data parsed")
        return

    combined = pd.concat(all_frames, ignore_index=True)
    print(f"\nTotal raw: {len(combined)}")
    deduped = combined.drop_duplicates(subset=["tahun", "provinsi"], keep="first")
    print(f"After dedup: {len(deduped)}")
    print("\nCoverage by year:")
    print(deduped.groupby("tahun")["provinsi"].nunique().to_string())

    cols = ["tahun", "provinsi", "subsektor", "volume_ton",
            "nilai_juta_usd", "sumber", "status"]
    saved = save_per_year(deduped[cols], OUTPUT)
    print(f"\nSaved {len(saved)} year files")

    print("\n=== Summary ===")
    print(pd.DataFrame(summary).to_string(index=False))


if __name__ == "__main__":
    main()
