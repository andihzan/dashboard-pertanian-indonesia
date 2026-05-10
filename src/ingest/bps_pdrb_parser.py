"""Parser untuk publikasi BPS PDRB Provinsi-Provinsi Menurut Lapangan Usaha.

Sumber: https://www.bps.go.id/id/publication?keyword=Produk+Domestik+Regional+Bruto

Tiap publikasi cover 5 tahun. 3 publikasi cukup untuk 2014-2024:
  - 2024 publication (2020-2024)
  - 2019 publication (2015-2019)
  - 2018 publication (2014-2018)

Format tabel per provinsi:
    Tabel X. PDRB [Provinsi] Atas Dasar Harga Berlaku Menurut Lapangan Usaha
    Lapangan Usaha             Y1     Y2     Y3     Y4     Y5
    A Pertanian, Kehutanan, dan Perikanan  37.900 37.768 39.005 41.626 42.121
    ...

Kita ambil row "A Pertanian, Kehutanan, dan Perikanan" → nilai_miliar_rp per tahun.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import pdfplumber

from src.provinces import PROVINCE_NAMES

PROVINCE_ALIASES = {
    "DI Yogyakarta": ["DI Yogyakarta", "D.I. Yogyakarta", "D.I Yogyakarta",
                       "Daerah Istimewa Yogyakarta"],
    "DKI Jakarta": ["DKI Jakarta", "D.K.I. Jakarta", "DKI"],
    "Kepulauan Bangka Belitung": ["Kepulauan Bangka Belitung", "Bangka Belitung"],
}

PROVINCE_TABLE_RE = re.compile(
    r"Tabel\s*(?:/Table)?\s*\d+[\.\s]+PDRB\s+(.+?)\s+Atas\s+Dasar\s+Harga\s+(Berlaku|Konstan)",
    re.IGNORECASE,
)


def _normalize_province(s: str) -> str | None:
    s = s.strip().rstrip(",.: ")
    s_lower = s.lower()
    for canonical, aliases in PROVINCE_ALIASES.items():
        for a in aliases:
            if a.lower() == s_lower:
                return canonical
    for p in PROVINCE_NAMES:
        if p.lower() == s_lower:
            return p
    return None


def _clean_number(s: str) -> float | None:
    s = s.strip()
    if s in {"–", "-", "—", "", "..."}:
        return None
    s = s.replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def parse_publication(pdf_path: Path, verbose: bool = True) -> pd.DataFrame:
    """Parse PDRB publication. Returns rows with columns:
        tahun, provinsi, nilai_miliar_rp, jenis_harga ("Berlaku"|"Konstan")
    """
    rows = []
    current_province = None
    current_year_set = None
    current_jenis = None

    with pdfplumber.open(pdf_path) as pdf:
        for pi, page in enumerate(pdf.pages):
            if verbose and pi % 20 == 0:
                print(f"  page {pi+1}/{len(pdf.pages)} | rows so far: {len(rows)}",
                      flush=True)
            t = page.extract_text() or ""
            if not t:
                continue
            # Detect new province table
            for m in PROVINCE_TABLE_RE.finditer(t):
                prov_raw = m.group(1).strip()
                jenis = m.group(2).capitalize()
                canonical = _normalize_province(prov_raw)
                if canonical:
                    current_province = canonical
                    current_jenis = jenis
                    # Find year header — allow optional asterisks for *) provisional / **) very provisional
                    ym = re.search(
                        r"(20\d\d)\*{0,2}\s+(20\d\d)\*{0,2}\s+(20\d\d)\*{0,2}\s+(20\d\d)\*{0,2}\s+(20\d\d)\*{0,2}",
                        t,
                    )
                    if ym:
                        current_year_set = tuple(int(y) for y in ym.groups())
                    break
            if current_province is None or current_year_set is None:
                continue
            # Look for row "A Pertanian, Kehutanan, dan Perikanan ..."
            for line in t.split("\n"):
                stripped = line.strip()
                # Match "A Pertanian" (with leading "A")
                if re.match(r"^A\s+Pertanian[,\s]\s*Kehutanan", stripped, re.IGNORECASE):
                    parts = stripped.split()
                    # Merge space-separated thousand groups (old format):
                    # "121 419" -> "121419". Only when:
                    #   - left token is 1-3 plain digits (no decimal/sign)
                    #   - right token is exactly 3 digits or 3 digits + decimal
                    merged_parts = []
                    i = 0
                    while i < len(parts):
                        cur = parts[i]
                        if (i + 1 < len(parts)
                            and re.match(r"^\d{1,3}$", cur)
                            and re.match(r"^\d{3}(?:[,.][\d,. ]*)?$", parts[i + 1])):
                            merged_parts.append(cur + parts[i + 1])
                            i += 2
                        else:
                            merged_parts.append(cur)
                            i += 1
                    nums = []
                    for tok in merged_parts:
                        v = _clean_number(tok)
                        if v is not None and v > 100:  # filter out small index-like numbers
                            nums.append(v)
                    if len(nums) >= 5:
                        for year, val in zip(current_year_set, nums[:5]):
                            rows.append({
                                "tahun": year,
                                "provinsi": current_province,
                                "nilai_miliar_rp": val,
                                "jenis_harga": current_jenis,
                                "sumber": "BPS PDRB",
                                "status": "real",
                            })
                        # Reset to avoid re-capturing
                        current_province = None
                        break

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.drop_duplicates(subset=["tahun", "provinsi", "jenis_harga"], keep="first")
    return df


if __name__ == "__main__":
    import sys
    pdf = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "data/raw/bps/source/pdrb/pdrb_pub_2024.pdf"
    )
    df = parse_publication(pdf)
    print(f"\nParsed {len(df)} rows")
    print(df.head(15).to_string(index=False))
    print(f"\nProvinsi unik ({df['provinsi'].nunique()}):", sorted(df['provinsi'].unique())[:10])
    print("Tahun:", sorted(df['tahun'].unique()))
    print("Jenis:", df['jenis_harga'].unique())
