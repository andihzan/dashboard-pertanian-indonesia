"""Batch parse 3 PDRB publications untuk cover 2014-2024."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.ingest.bps_pdrb_parser import parse_publication

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data" / "raw" / "bps" / "source" / "pdrb"
OUTPUT = ROOT / "data" / "raw"

PUB_FILES = [
    ("pdrb_pub_2024.pdf", 2024),  # 2020-2024
    ("pdrb_pub_2019.pdf", 2019),  # 2015-2019
    ("pdrb_pub_2018.pdf", 2018),  # 2014-2018
]


def main():
    all_frames = []
    for fname, pub_year in PUB_FILES:
        path = SOURCE / fname
        if not path.exists():
            print(f"[SKIP] {fname}")
            continue
        print(f"\n==> Parsing {fname}")
        df = parse_publication(path, verbose=False)
        if df.empty:
            print(f"  [WARN] empty")
            continue
        df["pub_year"] = pub_year
        provs = df["provinsi"].nunique()
        years = sorted(df["tahun"].unique().tolist())
        print(f"  parsed {len(df)} rows | {provs} provinces | years {years}")
        all_frames.append(df)

    if not all_frames:
        print("\nNo data parsed!")
        return

    combined = pd.concat(all_frames, ignore_index=True)
    print(f"\nTotal raw: {len(combined)}")
    deduped = combined.drop_duplicates(
        subset=["tahun", "provinsi", "jenis_harga"], keep="first"
    )
    print(f"After dedup (newest pub wins): {len(deduped)}")
    print("\nCoverage by year:")
    print(deduped[deduped["jenis_harga"] == "Berlaku"]
          .groupby("tahun")["provinsi"].nunique().to_string())

    out_path = OUTPUT / "bps_pdrb_consolidated.csv"
    cols = ["tahun", "provinsi", "jenis_harga", "nilai_miliar_rp", "sumber", "status"]
    deduped[cols].to_csv(out_path, index=False)
    print(f"\nSaved {out_path}")


if __name__ == "__main__":
    main()
