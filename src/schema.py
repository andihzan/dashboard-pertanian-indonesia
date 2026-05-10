"""Canonical data schemas for all three datasets.

All processed CSVs in data/processed/ MUST match these column sets.
"""
from dataclasses import dataclass

KREDIT_COLUMNS = [
    "tahun",            # int, 2014-2024
    "provinsi",         # str, must match provinces.PROVINCE_NAMES
    "jenis_kredit",     # str: "Modal Kerja" | "Investasi" | "Konsumsi" | "Total"
    "nilai_miliar_rp",  # float, posisi akhir tahun
    "sumber",           # str: "BI SEKDA" | "OJK SPI" | "BPS"
    "status",           # str: "real" | "estimasi" | "kosong"
]

EKSPOR_COLUMNS = [
    "tahun",
    "provinsi",         # provinsi asal barang
    "subsektor",        # "Tanaman Pangan" | "Hortikultura" | "Perkebunan" | "Peternakan" | "Total Pertanian"
    "volume_ton",
    "nilai_juta_usd",
    "sumber",           # "Kementan eksim" | "BPS"
    "status",
]

IMPOR_COLUMNS = [
    "tahun",
    "provinsi",         # provinsi pelabuhan bongkar
    "subsektor",
    "volume_ton",
    "nilai_juta_usd",
    "sumber",
    "status",
]

SUBSEKTOR_PERTANIAN = [
    "Tanaman Pangan",
    "Hortikultura",
    "Perkebunan",
    "Peternakan",
]

JENIS_KREDIT = ["Modal Kerja", "Investasi", "Konsumsi", "Total"]
