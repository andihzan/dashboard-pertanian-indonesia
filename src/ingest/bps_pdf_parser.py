"""Parser untuk publikasi BPS "Ekspor Menurut Provinsi Asal Barang".

Format yang ditangani: PDF tahunan BPS dengan tabel "Tabel 3.X
Perkembangan Nilai Ekspor Asal Barang [Provinsi] Menurut Sektor".

Cara kerja:
  1. Iterasi semua halaman PDF
  2. Identifikasi halaman dengan judul tabel sektor per provinsi
  3. Ekstrak baris "Pertanian" + total provinsi per tahun
  4. Output DataFrame schema BPS: provinsi, subsektor, volume_ton, nilai_juta_usd

Catatan: Sektor "Pertanian" pada publikasi BPS mencakup
"Pertanian, Kehutanan, dan Perikanan" — lebih luas daripada subsektor
Kementan (Tanaman Pangan/Hortikultura/Perkebunan/Peternakan).
Sub-kategori "Pertanian" pada BPS:
  - Pertanian Tanaman Tahunan (perkebunan-like)
  - Pemungutan Hasil Hutan Bukan Kayu
  - Perikanan Tangkap
  - dll.
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
    "Kepulauan Riau": ["Kepulauan Riau"],
    "Nusa Tenggara Barat": ["Nusa Tenggara Barat"],
    "Nusa Tenggara Timur": ["Nusa Tenggara Timur"],
    "Kalimantan Utara": ["Kalimantan Utara", "Kalimwantan Utara", "Kalimantan Utara"],
}

# Section header: any multi-level number (3.3.1, 4.3.1, 6.3.2, 8.3.4, …)
# Also tolerates: double "Ekspor Ekspor", trailing period, trailing single-letter watermark.
# Note: trailing watermark chars are stripped in _clean_province_raw(), NOT here.
SECTION_HEADER_RE = re.compile(
    r"^\s*\d+(?:\.\d+)+\.?\s+Ekspor\s+(?:Ekspor\s+)?Provinsi\s+Asal\s+(?:Barang\s+)?"
    r"([A-Za-z][A-Za-z .]+?)\s*\.?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
# Modern table title (2020+): "Tabel 3.X Perkembangan Nilai Ekspor Asal [Barang] [Prov]..."
TABLE_TITLE_RE = re.compile(
    r"Tabel\s+3\s*\.\s*\d+\s*\.?\s+(?:Tabel\s+)?Perkembangan\s+Nilai\s+Ekspor\s+Asal\s+"
    r"(?:B[\.\s]*arang\s+)?([A-Za-z][A-Za-z .]+?)\s+(?:Menurut\s+Sektor|,\s*20\d\d)",
    re.IGNORECASE | re.DOTALL,
)
# OLD format (2015-2019): "Tabel N. Perkembangan Nilai Ekspor Asal [g]Barang [Prov]
#   Menurut Sektor Tahun YYYY–YYYY"
# Tolerates: OCR in "Nilai" (N:ilai, N.ilai, Nilwai), "Ekspor" (Ekpsor),
#            leading watermark before Barang (gBarang), trailing watermark in province name.
OLD_TABLE_TITLE_RE = re.compile(
    r"Tab[a-z]{0,3}\s+\d+\s*\.?\s+"
    r"Perkembangan\s+N[a-z:./]{0,3}il[a-z]{0,2}i\s+Eks?[^\s]{0,3}por\s+Asal\s+"
    r"(?:[a-z]?\s*B[\.\s]*arang\s+)?"
    r"([A-Za-z][A-Za-z .]+?)\s+Menurut\s+Sektor\s+(?:Tahun\s+)?(20\d\d)\s*[–\-]\s*(20\d\d)",
    re.IGNORECASE | re.DOTALL,
)
# Kalimantan-style sector table: "Tabel N. Ekxpor Sektor Pertanian Asal [Barang] [Prov]"
# Has explicit PERTANIAN total row (uppercase) with 5 years of values.
PERTANIAN_SECTOR_RE = re.compile(
    r"Tab[a-z]{0,3}\s+\d+\s*[\.:]?\s*Ek[^\s]{0,5}por\s+Sektor\s+Pertanian\s+Asal\s+"
    r"(?:Barang\s+)?([A-Za-z][A-Za-z .]+?)(?:\n|$)",
    re.IGNORECASE,
)
# Detect unit from header. "US$ juta" / "Juta US$" → 1, "US$ ribu" / "Ribu US$" → 0.001
UNIT_JUTA_RE = re.compile(r"(juta|million)\s*US\$|US\$\s*(juta|million)", re.IGNORECASE)
UNIT_RIBU_RE = re.compile(r"(ribu|thousand)\s*US\$|US\$\s*(ribu|thousand)", re.IGNORECASE)

NUMBER_RE = re.compile(r"^[~\-\d.,\s]+$")


def _clean_number(s: str) -> float | None:
    """Convert BPS-formatted number string to float.

    BPS formats:
      - Modern: "1.234,56" (period thousands, comma decimal)
      - Old: "1 234,56" (space thousands, comma decimal)
      - "~0" = approximately zero
      - "–" / "-" / "—" = no data
    """
    s = s.strip()
    if s in {"–", "-", "—", ""}:
        return None
    if s == "~0":
        return 0.0
    # Remove space thousand separators and period thousand separators
    s = s.replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _clean_province_raw(raw: str) -> str:
    """Strip trailing watermark single-letters and punctuation from raw province string.

    Examples:
      "Sumatera Barat b" → "Sumatera Barat"
      "Jawa Timur b"     → "Jawa Timur"
      "Sulawesi Selatan i" → "Sulawesi Selatan"
      "Kalimantan Barat." → "Kalimantan Barat"
      "Kalimwantan Utara" → kept as-is (alias handles it)
    """
    raw = raw.strip()
    # Strip trailing single lowercase/uppercase letter (watermark artifacts)
    raw = re.sub(r"\s+[a-zA-Z]\.?\s*$", "", raw).strip()
    # Strip trailing punctuation
    return raw.rstrip(".,;:").strip()


def _normalize_province_name(raw: str) -> str | None:
    """Map raw province string from PDF to canonical name."""
    raw = _clean_province_raw(raw)
    raw_lower = raw.lower()
    for canonical, aliases in PROVINCE_ALIASES.items():
        for a in aliases:
            if a.lower() == raw_lower:
                return canonical
    for p in PROVINCE_NAMES:
        if p.lower() == raw_lower:
            return p
    return None


def _is_charspaced_page(text: str) -> bool:
    """Detect if page uses char-by-char layout (multiple lines of single chars).

    True if many text lines have ≥3 tokens with most being 1-2 chars each.
    """
    lines = [ln for ln in text.split("\n") if ln.strip()]
    char_lines = 0
    for ln in lines:
        tokens = ln.split()
        if len(tokens) >= 3 and sum(1 for t in tokens if len(t) <= 2) >= len(tokens) * 0.7:
            char_lines += 1
    return char_lines >= 5


def _extract_pertanian_charspaced(page) -> dict[int, float] | None:
    """Coordinate-based extraction for char-spaced pages.

    Returns {year: nilai_juta_usd} for years 2022, 2023, 2024 (or other 3
    year set inferred from column headers). Empty dict if no Pertanian found.
    """
    from collections import defaultdict
    try:
        words = page.extract_words(x_tolerance=2, y_tolerance=2)
    except Exception:
        return None
    if not words:
        return None

    # Detect year header row to find year column X positions
    year_x_map: dict[int, float] = {}  # year -> x_center
    rows: dict[int, list] = defaultdict(list)
    for w in words:
        y_key = round(w["top"] / 5) * 5
        rows[y_key].append(w)

    # Find year row: look for rows with "20XX" patterns
    year_re = re.compile(r"20\d\d")
    for y, ws in sorted(rows.items()):
        ws_sorted = sorted(ws, key=lambda w: w["x0"])
        # Concat consecutive single-char words to detect "2 0 2 4" → "2024"
        # Use fixed sliding window
        joined_str = "".join(w["text"] for w in ws_sorted)
        year_matches = list(year_re.finditer(joined_str))
        if len(year_matches) >= 3:
            # Find x position for each year
            cumlen = 0
            year_starts = {}
            cur_idx = 0
            for w in ws_sorted:
                # which year does this position correspond to?
                if cur_idx < len(year_matches):
                    target_start = year_matches[cur_idx].start()
                    target_end = year_matches[cur_idx].end()
                    if cumlen >= target_start and cumlen < target_end:
                        if cur_idx not in year_starts:
                            year_starts[cur_idx] = w["x0"]
                cumlen += len(w["text"])
                # advance cur_idx if past this match
                if cur_idx < len(year_matches) and cumlen >= year_matches[cur_idx].end():
                    cur_idx += 1
            if len(year_starts) >= 3:
                for idx in sorted(year_starts.keys())[:3]:
                    yr = int(year_matches[idx].group())
                    year_x_map[yr] = year_starts[idx]
                break

    if len(year_x_map) < 3:
        return None

    # Define x-band per year (mid +/- 25)
    sorted_years = sorted(year_x_map.items(), key=lambda kv: kv[1])
    year_bands = {}
    for i, (yr, x) in enumerate(sorted_years):
        next_x = sorted_years[i + 1][1] if i + 1 < len(sorted_years) else x + 50
        year_bands[yr] = (x - 8, next_x - 5)

    def col_text(ws, x_min, x_max):
        chars = sorted([w for w in ws if x_min <= w["x0"] <= x_max], key=lambda w: w["x0"])
        return "".join(w["text"] for w in chars)

    # Find row with label exactly "Pertanian" (in label band x ≤ 200)
    for y, ws in sorted(rows.items()):
        label = col_text(ws, 60, 200).strip()
        # Filter watermark fragments
        label_clean = re.sub(r"[^A-Za-z]", "", label)
        if label_clean == "Pertanian":
            result = {}
            for yr, (x_min, x_max) in year_bands.items():
                raw = col_text(ws, x_min, x_max).strip()
                # Clean watermark contamination (single chars at edge)
                raw_cleaned = re.sub(r"[a-z]$", "", raw)  # strip trailing watermark letter
                v = _clean_number(raw_cleaned)
                if v is not None:
                    result[yr] = v
            return result if result else None
    return None


def parse_publication(pdf_path: Path, verbose: bool = True,
                      max_pages: int | None = None) -> pd.DataFrame:
    """Parse BPS provincial export publication into a long-format DataFrame.

    Args:
        pdf_path: path to BPS publication PDF
        verbose: print progress every 20 pages
        max_pages: stop after N pages (None = all)

    Returns rows with columns:
        tahun, provinsi, subsektor, nilai_juta_usd, sumber, status
    """
    rows = []
    current_province = None
    current_year_set = None  # (y1, y2, y3) — kolom yang ada di tabel
    seen_provinces: set[str] = set()

    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages) if max_pages is None else min(max_pages, len(pdf.pages))
        for page_idx, page in enumerate(pdf.pages):
            if max_pages is not None and page_idx >= max_pages:
                break
            if verbose and page_idx % 20 == 0:
                print(f"  page {page_idx+1}/{total} | provinces found: {len(seen_provinces)}",
                      flush=True)
            # Skip TOC pages (typically before page 20). Allow up to page 280 to
            # cover publications with 38 provinces (2024+).
            if page_idx < 18 or page_idx > 280:
                continue
            text = page.extract_text() or ""
            if not text:
                continue
            # Some 2024 BPS pages render table cells with single-char spacing,
            # e.g. "P e r t a n ia n" / "1 0 4 ,0". Detect such lines and
            # collapse spaces between 1-2 char tokens.
            def _maybe_join_charspaced(ln: str) -> str:
                tokens = ln.split()
                if len(tokens) >= 5 and sum(1 for t in tokens if len(t) <= 2) >= len(tokens) * 0.7:
                    return "".join(tokens)
                return ln
            text = "\n".join(_maybe_join_charspaced(ln) for ln in text.split("\n"))
            # Normalize text: replace single-char watermark line "d\ni\n.\no\n..." patterns
            # by collapsing very-short lines into a space.
            normalized = "\n".join(
                ln if len(ln.strip()) > 2 else "" for ln in text.split("\n")
            )
            # For title matching, also try a flat version (newlines -> space)
            flat = re.sub(r"\s+", " ", normalized)

            # Detect unit on this page (juta vs ribu)
            unit_multiplier = 1.0
            if UNIT_RIBU_RE.search(flat) and not UNIT_JUTA_RE.search(flat):
                unit_multiplier = 0.001  # ribu -> juta

            # Try matching: modern section header → modern table → old table → pertanian sector
            # For SECTION_HEADER_RE: use finditer to skip non-canonical matches
            # (e.g. "3.3 ... di Kawasan Sumatera" on same page as "3.3.1 ... Aceh")
            found_match = None
            old_match = None
            for m_candidate in SECTION_HEADER_RE.finditer(text):
                prov_raw_c = m_candidate.group(1).strip()
                if _normalize_province_name(prov_raw_c):
                    found_match = m_candidate
                    break
            if not found_match:
                found_match = TABLE_TITLE_RE.search(flat)
            if not found_match:
                old_match = OLD_TABLE_TITLE_RE.search(flat)
                found_match = old_match
            if not found_match:
                sector_m = PERTANIAN_SECTOR_RE.search(flat)
                found_match = sector_m
            if found_match:
                prov_raw = found_match.group(1).strip()
                canonical = _normalize_province_name(prov_raw)
                if canonical and canonical not in seen_provinces:
                    current_province = canonical
                # Determine year set
                if old_match and old_match is found_match:
                    # Old format: years are part of title regex group(2), group(3)
                    y_start = int(old_match.group(2))
                    y_end = int(old_match.group(3))
                    current_year_set = tuple(range(y_start, y_end + 1))
                else:
                    # Try 5-year sequence first (Kalimantan sector tables + some others)
                    # Allow optional dot/punct after first year: "2011. - 2015" edge case
                    ym5 = re.search(
                        r"(20\d\d)\s+(20\d\d)\s+(20\d\d)\s+(20\d\d)\s+(20\d\d)", text
                    )
                    if ym5:
                        current_year_set = tuple(int(y) for y in ym5.groups())
                    else:
                        ym3 = re.search(r"(20\d\d)[^0-9]{0,5}(20\d\d)[^0-9]{0,5}(20\d\d)", text)
                        if ym3:
                            current_year_set = tuple(int(y) for y in ym3.groups())

            if current_province is None or current_year_set is None:
                continue

            # Char-spaced fallback: untuk 2024 PDF dengan layout char-by-char,
            # gunakan coordinate-based extraction.
            if _is_charspaced_page(text):
                cs_result = _extract_pertanian_charspaced(page)
                if cs_result:
                    for year, val in cs_result.items():
                        if val is not None:
                            rows.append({
                                "tahun": year,
                                "provinsi": current_province,
                                "subsektor": "Pertanian (BPS Sektor)",
                                "volume_ton": None,
                                "nilai_juta_usd": val * unit_multiplier,
                                "sumber": "BPS",
                                "status": "real",
                            })
                    seen_provinces.add(current_province)
                    current_province = None
                    continue

            # Cari baris "Pertanian" / "PERTANIAN" — bisa title sektor atau row agregat.
            # Kalimantan pubs: "PERTANIAN" (uppercase) diikuti angka 5 tahun.
            # Sumatera/Jawa pubs: "Pertanian" (titlecase) diikuti angka 3-5 tahun.
            # Kita skip sub-rows seperti "Pertanian Tanaman...", "Perikanan Tangkap", dll.
            _PERTANIAN_SKIP_RE = re.compile(
                r"^pertanian\s+(tanaman|buah|obat|dan\s|,\s*kehutanan)",
                re.IGNORECASE,
            )
            for line in normalized.split("\n"):
                stripped = line.strip()
                stripped_upper = stripped.upper()
                # Match both titlecase and uppercase "Pertanian/PERTANIAN" followed by numbers
                if not (stripped_upper.startswith("PERTANIAN ")
                        or stripped.startswith("Pertanian ")):
                    continue
                if _PERTANIAN_SKIP_RE.match(stripped):
                    continue
                parts = stripped.split()
                # Merge space-separated thousand groups: "13 200,1" → "13200,1"
                merged_parts: list[str] = []
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
                # first token = "Pertanian"/"PERTANIAN", rest = numbers + growth cols
                nums = [p for p in merged_parts[1:] if NUMBER_RE.match(p)]
                # Need at least as many values as years in current_year_set (up to 5)
                n_years = len(current_year_set)
                if len(nums) >= min(3, n_years):
                    for year, val in zip(current_year_set, nums[:n_years]):
                        v = _clean_number(val)
                        if v is not None:
                            rows.append({
                                "tahun": year,
                                "provinsi": current_province,
                                "subsektor": "Pertanian (BPS Sektor)",
                                "volume_ton": None,
                                "nilai_juta_usd": v * unit_multiplier,
                                "sumber": "BPS",
                                "status": "real",
                            })
                    seen_provinces.add(current_province)
                    current_province = None  # reset, hindari duplikasi multi-page
                    break

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.drop_duplicates(subset=["tahun", "provinsi", "subsektor"])
    return df


def save_per_year(df: pd.DataFrame, output_dir: Path) -> dict[int, Path]:
    """Split parsed DataFrame into per-year CSV files matching loader convention.

    Returns mapping {year: csv_path}.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    result = {}
    for year, sub in df.groupby("tahun"):
        out_cols = ["provinsi", "subsektor", "volume_ton", "nilai_juta_usd"]
        path = output_dir / f"ekspor_pertanian_{int(year)}.csv"
        sub[out_cols].to_csv(path, index=False)
        result[int(year)] = path
    return result


if __name__ == "__main__":
    import sys
    pdf = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "data/raw/bps/source/bps_ekspor_provinsi_2023.pdf"
    )
    df = parse_publication(pdf)
    print(f"\nParsed {len(df)} rows from {pdf}")
    print(df.head(10).to_string(index=False))
    print(f"\nProvinsi unik ({df['provinsi'].nunique()}):", sorted(df["provinsi"].unique()))
    print("Tahun unik:", sorted(df["tahun"].unique()))

    # Save per-year files
    out_dir = Path(__file__).resolve().parents[2] / "data" / "raw" / "bps"
    saved = save_per_year(df, out_dir)
    print(f"\nSaved {len(saved)} per-year files:")
    for y, p in saved.items():
        print(f"  {y}: {p}")
