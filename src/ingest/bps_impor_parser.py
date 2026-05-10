"""Parser untuk Lampiran 6 publikasi BPS Impor Jilid II.

Format yang ditangani:
    Lampiran 6 - "Impor Menurut Provinsi dan Golongan Barang (HS) 2 Digit"

Struktur tabel:
    Aceh  [berat_y1]  [nilai_y1]  [berat_y2]  [nilai_y2]      ← provinsi total
    07 Vegetables           50          26          –          –
    08 Edible fruits        101         48          –          –
    10 Cereals       93.566.850   53.764.066  76.602.400  46.481.271
    ...

Pertanian = HS 01-24 (live animals -> tobacco).
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import pdfplumber

from src.provinces import PROVINCE_NAMES

# HS codes 01-24 dianggap pertanian (klasifikasi WTO/FAO)
PERTANIAN_HS_CODES = {f"{i:02d}" for i in range(1, 25)}

PROVINCE_ALIASES = {
    "DI Yogyakarta": ["DI Yogyakarta", "D.I. Yogyakarta", "Daerah Istimewa Yogyakarta"],
    "DKI Jakarta": ["DKI Jakarta", "D.K.I. Jakarta", "Dki Jakarta"],
    "Kepulauan Bangka Belitung": ["Kepulauan Bangka Belitung", "Bangka Belitung"],
}


def _normalize_province_name(raw: str) -> str | None:
    raw = raw.strip().rstrip(",.: ")
    raw_lower = raw.lower()
    for canonical, aliases in PROVINCE_ALIASES.items():
        for a in aliases:
            if a.lower() == raw_lower:
                return canonical
    for p in PROVINCE_NAMES:
        if p.lower() == raw_lower:
            return p
    return None


def _clean_number(s: str) -> float | None:
    s = s.strip()
    if s in {"–", "-", "—", "", "..."}:
        return None
    if s == "~0":
        return 0.0
    s = s.replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


# Province header pattern: "Aceh 378.096.488 156.435.520 935.460.851 469.767.014"
# Should be: 1-3 word province name followed by 4 numbers
PROV_LINE_RE = re.compile(
    r"^([A-Z][A-Za-z]+(?:\s[A-Z][A-Za-z]+){0,3})\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s*$"
)
# HS line: "07 Vegetables 50 26 – –"
HS_LINE_RE = re.compile(
    r"^(\d{2})\s+(.+?)\s+([\d.,–\-—~]+)\s+([\d.,–\-—~]+)\s+([\d.,–\-—~]+)\s+([\d.,–\-—~]+)\s*$"
)


def find_lampiran6_range(pdf) -> tuple[int, int]:
    """Locate page range containing Lampiran 6.

    Returns (start_page_idx, end_page_idx). end is exclusive.
    """
    start = None
    end = len(pdf.pages)
    for pi, page in enumerate(pdf.pages):
        t = page.extract_text() or ""
        if start is None:
            # Heading marker
            if "Lampiran/Appendix 6" in t and "2 Digit" in t and "Provinsi" in t:
                start = pi
                continue
        else:
            # Stop when next lampiran (7) starts
            if "Lampiran/Appendix 7" in t:
                end = pi
                break
    return start, end


def parse_year_set(pdf, start: int) -> tuple[int, int] | None:
    """Find year set from header on first lampiran page."""
    t = pdf.pages[start].extract_text() or ""
    m = re.search(r"(20\d\d)\s+(?:dan|and)\s+(20\d\d)", t)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"(20\d\d)\s+(20\d\d)", t)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


def parse_publication(pdf_path: Path, verbose: bool = True) -> pd.DataFrame:
    """Parse Lampiran 6 from BPS Impor Jilid II publication."""
    rows = []
    with pdfplumber.open(pdf_path) as pdf:
        start, end = find_lampiran6_range(pdf)
        if start is None:
            if verbose:
                print(f"  [WARN] Lampiran 6 not found in {pdf_path.name}")
            return pd.DataFrame()
        years = parse_year_set(pdf, start)
        if not years:
            if verbose:
                print(f"  [WARN] year set not detected in {pdf_path.name}")
            return pd.DataFrame()
        if verbose:
            print(f"  Lampiran 6: pages {start+1}-{end} | years {years}")

        current_province = None
        prov_pertanian_total = {0: 0.0, 1: 0.0}  # nilai per year (juta USD)
        prov_pertanian_volume = {0: 0.0, 1: 0.0}  # volume per year (kg→ton)

        def flush_province():
            nonlocal current_province
            if current_province is None:
                return
            for yr_idx, yr in enumerate(years):
                nilai = prov_pertanian_total[yr_idx]
                vol_kg = prov_pertanian_volume[yr_idx]
                if nilai > 0 or vol_kg > 0:
                    rows.append({
                        "tahun": yr,
                        "provinsi": current_province,
                        "subsektor": "Pertanian (BPS HS01-24)",
                        "volume_ton": vol_kg / 1000.0,  # kg → ton
                        "nilai_juta_usd": nilai / 1_000_000.0,  # USD → juta USD
                        "sumber": "BPS",
                        "status": "real",
                    })

        for pi in range(start, end):
            t = pdf.pages[pi].extract_text() or ""
            if verbose and pi % 50 == 0:
                print(f"    page {pi+1}/{end}", flush=True)
            for line in t.split("\n"):
                stripped = line.strip()
                if not stripped or len(stripped) < 5:
                    continue
                # Try province header line first
                pm = PROV_LINE_RE.match(stripped)
                if pm:
                    raw_prov = pm.group(1)
                    canonical = _normalize_province_name(raw_prov)
                    if canonical:
                        # flush previous, start new
                        flush_province()
                        current_province = canonical
                        prov_pertanian_total = {0: 0.0, 1: 0.0}
                        prov_pertanian_volume = {0: 0.0, 1: 0.0}
                        continue
                # HS line
                hm = HS_LINE_RE.match(stripped)
                if hm and current_province:
                    hs_code = hm.group(1)
                    if hs_code in PERTANIAN_HS_CODES:
                        # year 1: groups 3,4 = berat, nilai; year 2: groups 5,6 = berat, nilai
                        for yr_idx, (vol_g, val_g) in enumerate([(3, 4), (5, 6)]):
                            vol = _clean_number(hm.group(vol_g))
                            val = _clean_number(hm.group(val_g))
                            if val is not None:
                                prov_pertanian_total[yr_idx] += val
                            if vol is not None:
                                prov_pertanian_volume[yr_idx] += vol

        # final flush
        flush_province()

    return pd.DataFrame(rows)


def save_per_year(df: pd.DataFrame, output_dir: Path) -> dict[int, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    result = {}
    for year, sub in df.groupby("tahun"):
        out_cols = ["provinsi", "subsektor", "volume_ton", "nilai_juta_usd"]
        path = output_dir / f"impor_pertanian_{int(year)}.csv"
        sub[out_cols].to_csv(path, index=False)
        result[int(year)] = path
    return result


if __name__ == "__main__":
    import sys
    pdf = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "data/raw/bps/source/impor/bps_impor_jilid_ii_2024.pdf"
    )
    df = parse_publication(pdf)
    print(f"\nParsed {len(df)} rows")
    print(df.head(10).to_string(index=False))
    print(f"\nProvinsi unik ({df['provinsi'].nunique()}):", sorted(df["provinsi"].unique())[:10])
    print("Tahun unik:", sorted(df["tahun"].unique()))
