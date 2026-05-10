"""Generate demo reference CSVs with plausible (NOT real) provincial numbers.

These are clearly marked status="demo" so they can be distinguished from
real data and replaced as the user fills in real CSVs.

Why demo data?
  - The dashboard needs to render meaningfully on first run
  - The structure mirrors the real schema exactly
  - Magnitudes are anchored to publicly known national totals from BPS &
    BI press releases, distributed via plausible provincial weights
  - Province-level numbers are NOT verified — replace with real data
    from BI SEKDA, OJK, BPS publications, or Kementan eksim

Run:  python -m src.seed_demo
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from src.provinces import NEW_PROVINCES_2022, PROVINCES, PROVINCE_NAMES
from src.schema import SUBSEKTOR_PERTANIAN

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "sample"
SAMPLE.mkdir(parents=True, exist_ok=True)

YEARS = list(range(2014, 2025))

# Plausible relative weights per province for kredit pertanian
# (rough proxy for PDRB sektor pertanian — not exact)
KREDIT_WEIGHT = {
    "Sumatera Utara": 9.5, "Riau": 8.0, "Sumatera Selatan": 6.5,
    "Lampung": 5.5, "Jambi": 3.0, "Aceh": 2.5, "Sumatera Barat": 3.0,
    "Bengkulu": 1.0, "Kepulauan Bangka Belitung": 1.0, "Kepulauan Riau": 0.4,
    "DKI Jakarta": 1.5, "Jawa Barat": 8.5, "Jawa Tengah": 7.5,
    "DI Yogyakarta": 0.6, "Jawa Timur": 9.0, "Banten": 1.8,
    "Bali": 1.2, "Nusa Tenggara Barat": 2.0, "Nusa Tenggara Timur": 1.5,
    "Kalimantan Barat": 4.5, "Kalimantan Tengah": 4.0,
    "Kalimantan Selatan": 3.5, "Kalimantan Timur": 2.5, "Kalimantan Utara": 0.6,
    "Sulawesi Utara": 1.5, "Sulawesi Tengah": 2.0, "Sulawesi Selatan": 4.5,
    "Sulawesi Tenggara": 1.5, "Gorontalo": 0.7, "Sulawesi Barat": 0.6,
    "Maluku": 0.7, "Maluku Utara": 0.5,
    "Papua Barat": 0.5, "Papua Barat Daya": 0.3, "Papua": 1.0,
    "Papua Selatan": 0.3, "Papua Tengah": 0.3, "Papua Pegunungan": 0.2,
}

# Ekspor weights — heavily concentrated on CPO/coffee/cocoa producers
EKSPOR_WEIGHT = {
    "Riau": 18.0, "Sumatera Utara": 12.0, "Sumatera Selatan": 7.0,
    "Lampung": 5.5, "Jambi": 4.5, "Aceh": 1.0, "Sumatera Barat": 2.0,
    "Bengkulu": 0.8, "Kepulauan Bangka Belitung": 0.8, "Kepulauan Riau": 0.5,
    "DKI Jakarta": 0.5, "Jawa Barat": 5.0, "Jawa Tengah": 3.5,
    "DI Yogyakarta": 0.3, "Jawa Timur": 5.5, "Banten": 1.0,
    "Bali": 1.2, "Nusa Tenggara Barat": 0.6, "Nusa Tenggara Timur": 0.5,
    "Kalimantan Barat": 5.0, "Kalimantan Tengah": 6.5,
    "Kalimantan Selatan": 4.0, "Kalimantan Timur": 3.5, "Kalimantan Utara": 0.6,
    "Sulawesi Utara": 1.5, "Sulawesi Tengah": 2.5, "Sulawesi Selatan": 3.5,
    "Sulawesi Tenggara": 1.0, "Gorontalo": 0.4, "Sulawesi Barat": 0.7,
    "Maluku": 0.4, "Maluku Utara": 0.3,
    "Papua Barat": 0.3, "Papua Barat Daya": 0.2, "Papua": 0.5,
    "Papua Selatan": 0.2, "Papua Tengah": 0.2, "Papua Pegunungan": 0.1,
}

# Impor pertanian — concentrated on major loading ports
IMPOR_WEIGHT = {
    "DKI Jakarta": 35.0, "Jawa Timur": 25.0, "Sumatera Utara": 12.0,
    "Banten": 8.0, "Jawa Barat": 5.0, "Jawa Tengah": 3.5,
    "Sulawesi Selatan": 3.0, "Sumatera Selatan": 1.5, "Riau": 1.5,
    "Kepulauan Riau": 1.0, "Lampung": 1.0, "Kalimantan Timur": 0.8,
    "Bali": 0.6, "Sumatera Barat": 0.4, "Kalimantan Selatan": 0.4,
    "Aceh": 0.3, "Papua": 0.2, "Maluku": 0.2,
}

# National total kredit pertanian (Rp triliun) — approximate from BI/OJK reports
KREDIT_TOTAL_NASIONAL_TRIL = {
    2014: 195, 2015: 215, 2016: 235, 2017: 265, 2018: 305,
    2019: 335, 2020: 365, 2021: 405, 2022: 460, 2023: 525, 2024: 595,
}

# National total ekspor pertanian (juta USD) — from BPS releases (CPO included)
EKSPOR_TOTAL_NASIONAL_JUTA_USD = {
    2014: 33000, 2015: 28000, 2016: 27000, 2017: 32500, 2018: 28800,
    2019: 27200, 2020: 30500, 2021: 41000, 2022: 49100, 2023: 39900, 2024: 44500,
}

# National total impor pertanian (juta USD)
IMPOR_TOTAL_NASIONAL_JUTA_USD = {
    2014: 15500, 2015: 14000, 2016: 14300, 2017: 17500, 2018: 18000,
    2019: 16500, 2020: 17800, 2021: 22500, 2022: 25800, 2023: 22300, 2024: 24700,
}

JENIS_KREDIT_SHARE = {"Modal Kerja": 0.52, "Investasi": 0.41, "Konsumsi": 0.07}

SUBSEKTOR_EKSPOR_SHARE = {
    "Perkebunan": 0.78, "Tanaman Pangan": 0.06,
    "Hortikultura": 0.10, "Peternakan": 0.06,
}
SUBSEKTOR_IMPOR_SHARE = {
    "Tanaman Pangan": 0.55, "Peternakan": 0.18,
    "Hortikultura": 0.15, "Perkebunan": 0.12,
}


def _is_active_year(prov: str, year: int) -> bool:
    return not (prov in NEW_PROVINCES_2022 and year < 2022)


def _normalize(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.values())
    return {k: v / total for k, v in weights.items()}


def _seasonal_noise(seed: int) -> float:
    rng = np.random.default_rng(seed)
    return float(rng.normal(1.0, 0.08))


def gen_kredit() -> pd.DataFrame:
    w = _normalize(KREDIT_WEIGHT)
    rows = []
    for year in YEARS:
        nat = KREDIT_TOTAL_NASIONAL_TRIL[year] * 1000  # to miliar
        for prov in PROVINCE_NAMES:
            if not _is_active_year(prov, year):
                continue
            share = w.get(prov, 0)
            base = nat * share
            for jk, frac in JENIS_KREDIT_SHARE.items():
                noise = _seasonal_noise(hash((year, prov, jk)) & 0xFFFFFFFF)
                val = base * frac * noise
                rows.append({
                    "tahun": year, "provinsi": prov, "jenis_kredit": jk,
                    "nilai_miliar_rp": round(val, 1),
                    "sumber": "DEMO (BI SEKDA proxy)", "status": "demo",
                })
            total = sum(r["nilai_miliar_rp"] for r in rows[-3:])
            rows.append({
                "tahun": year, "provinsi": prov, "jenis_kredit": "Total",
                "nilai_miliar_rp": round(total, 1),
                "sumber": "DEMO (BI SEKDA proxy)", "status": "demo",
            })
    return pd.DataFrame(rows)


def gen_ekspor() -> pd.DataFrame:
    w = _normalize(EKSPOR_WEIGHT)
    rows = []
    for year in YEARS:
        nat = EKSPOR_TOTAL_NASIONAL_JUTA_USD[year]
        for prov in PROVINCE_NAMES:
            if not _is_active_year(prov, year):
                continue
            share = w.get(prov, 0)
            base = nat * share
            for sub, frac in SUBSEKTOR_EKSPOR_SHARE.items():
                noise = _seasonal_noise(hash((year, prov, sub, "ek")) & 0xFFFFFFFF)
                val_usd = base * frac * noise
                # implied price ~ 800 USD/ton untuk pangan, 600 untuk hortikultura,
                # 1000 untuk perkebunan, 3000 untuk peternakan
                price = {"Tanaman Pangan": 800, "Hortikultura": 600,
                         "Perkebunan": 1000, "Peternakan": 3000}[sub]
                vol = (val_usd * 1_000_000) / price
                rows.append({
                    "tahun": year, "provinsi": prov, "subsektor": sub,
                    "volume_ton": round(vol, 1),
                    "nilai_juta_usd": round(val_usd, 2),
                    "sumber": "DEMO (BPS proxy)", "status": "demo",
                })
    return pd.DataFrame(rows)


def gen_impor() -> pd.DataFrame:
    w = _normalize(IMPOR_WEIGHT)
    rows = []
    for year in YEARS:
        nat = IMPOR_TOTAL_NASIONAL_JUTA_USD[year]
        for prov in PROVINCE_NAMES:
            if not _is_active_year(prov, year):
                continue
            share = w.get(prov, 0)
            if share == 0:
                continue
            base = nat * share
            for sub, frac in SUBSEKTOR_IMPOR_SHARE.items():
                noise = _seasonal_noise(hash((year, prov, sub, "im")) & 0xFFFFFFFF)
                val_usd = base * frac * noise
                price = {"Tanaman Pangan": 400, "Hortikultura": 700,
                         "Perkebunan": 1500, "Peternakan": 2500}[sub]
                vol = (val_usd * 1_000_000) / price
                rows.append({
                    "tahun": year, "provinsi": prov, "subsektor": sub,
                    "volume_ton": round(vol, 1),
                    "nilai_juta_usd": round(val_usd, 2),
                    "sumber": "DEMO (Kementan proxy)", "status": "demo",
                })
    return pd.DataFrame(rows)


def main():
    print("Generating demo reference CSVs...")
    kredit = gen_kredit()
    ekspor = gen_ekspor()
    impor = gen_impor()
    kredit.to_csv(SAMPLE / "kredit_demo.csv", index=False)
    ekspor.to_csv(SAMPLE / "ekspor_demo.csv", index=False)
    impor.to_csv(SAMPLE / "impor_demo.csv", index=False)
    print(f"Kredit:  {len(kredit):>5} rows -> {SAMPLE / 'kredit_demo.csv'}")
    print(f"Ekspor:  {len(ekspor):>5} rows -> {SAMPLE / 'ekspor_demo.csv'}")
    print(f"Impor:   {len(impor):>5} rows -> {SAMPLE / 'impor_demo.csv'}")
    print("\nDONE. All rows marked status='demo'. Replace with real data from\n"
          "BI SEKDA / OJK / BPS / Kementan to override per (year, provinsi, key).")


if __name__ == "__main__":
    main()
