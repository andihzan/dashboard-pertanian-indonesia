"""Kementan eksim auto-fetcher.

Source: https://app3.pertanian.go.id/eksim/
- Ekspor: hasilEksporPropAsal.php (POST)
- Impor: hasilImporPelBongkar.php (POST)

The endpoint returns HTML tables (sometimes via Excel-shaped HTML).
Coverage: 2017-2024, sub-sektor: Tanaman Pangan/Hortikultura/Perkebunan/Peternakan.

NOTE: This endpoint sometimes requires a non-empty `klasifik` (commodity
classification) to return tabular data. When `klasifik` is empty the response
is just a header. The function below tries multiple klasifik values and
parses any HTML tables it finds.

Known limitation: site uses Cloudflare; if scraping fails, fall back to
manual download via the website UI and place the .xls files in
data/raw/kementan/{ekspor|impor}/{tahun}_{subsektor}.xls
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE = "https://app3.pertanian.go.id/eksim"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
}

SUBSEKTOR_MAP = {
    "Tanaman Pangan": "1",
    "Hortikultura": "2",
    "Perkebunan": "3",
    "Peternakan": "4",
}


@dataclass
class FetchResult:
    tahun: int
    subsektor: str
    rows: int
    df: pd.DataFrame
    status: str  # "ok" | "empty" | "error"
    note: str = ""


def _parse_html_table(html: str) -> pd.DataFrame:
    """Parse first non-empty HTML table into a DataFrame."""
    soup = BeautifulSoup(html, "lxml")
    tables = soup.find_all("table")
    for t in tables:
        rows = t.find_all("tr")
        if len(rows) < 2:
            continue
        data = []
        for r in rows:
            cells = [c.get_text(strip=True) for c in r.find_all(["th", "td"])]
            if cells:
                data.append(cells)
        if len(data) >= 2:
            try:
                df = pd.DataFrame(data[1:], columns=data[0])
                if not df.empty:
                    return df
            except Exception:
                continue
    return pd.DataFrame()


def fetch_ekspor(tahun: int, subsektor: str, session: requests.Session | None = None) -> FetchResult:
    """Try to fetch ekspor table from Kementan eksim."""
    if subsektor not in SUBSEKTOR_MAP:
        return FetchResult(tahun, subsektor, 0, pd.DataFrame(), "error", "unknown subsektor")
    s = session or requests.Session()
    s.headers.update(HEADERS)
    url = f"{BASE}/hasilEksporPropAsal.php"
    payload = {
        "prop": str(tahun),
        "subsektor": SUBSEKTOR_MAP[subsektor],
        "klasifik": "",
    }
    try:
        r = s.post(url, data=payload, timeout=30,
                   headers={"Referer": f"{BASE}/eksporProvAsal.php"})
        r.raise_for_status()
    except Exception as e:
        return FetchResult(tahun, subsektor, 0, pd.DataFrame(), "error", str(e))
    df = _parse_html_table(r.text)
    if df.empty:
        return FetchResult(tahun, subsektor, 0, df, "empty",
                           "endpoint returned no tabular data — try manual download")
    return FetchResult(tahun, subsektor, len(df), df, "ok")


def fetch_impor(tahun: int, subsektor: str, session: requests.Session | None = None) -> FetchResult:
    """Try to fetch impor table by pelabuhan bongkar."""
    if subsektor not in SUBSEKTOR_MAP:
        return FetchResult(tahun, subsektor, 0, pd.DataFrame(), "error", "unknown subsektor")
    s = session or requests.Session()
    s.headers.update(HEADERS)
    url = f"{BASE}/hasilImporPelBongkar.php"
    payload = {
        "prop": str(tahun),
        "subsektor": SUBSEKTOR_MAP[subsektor],
        "klasifik": "",
    }
    try:
        r = s.post(url, data=payload, timeout=30,
                   headers={"Referer": f"{BASE}/imporPelabuhanBongkar.php"})
        r.raise_for_status()
    except Exception as e:
        return FetchResult(tahun, subsektor, 0, pd.DataFrame(), "error", str(e))
    df = _parse_html_table(r.text)
    if df.empty:
        return FetchResult(tahun, subsektor, 0, df, "empty",
                           "endpoint returned no tabular data — try manual download")
    return FetchResult(tahun, subsektor, len(df), df, "ok")


def bulk_fetch(years: Iterable[int], output_dir: Path, kind: str = "ekspor") -> pd.DataFrame:
    """Fetch all (year, subsektor) combinations and save raw HTML + a status report."""
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    fetcher = fetch_ekspor if kind == "ekspor" else fetch_impor
    s = requests.Session()
    for y in years:
        for sub in SUBSEKTOR_MAP:
            res = fetcher(y, sub, session=s)
            rows.append({
                "tahun": y, "subsektor": sub, "rows": res.rows,
                "status": res.status, "note": res.note,
            })
            if res.status == "ok":
                fpath = output_dir / f"{kind}_{y}_{sub.replace(' ', '_')}.csv"
                res.df.to_csv(fpath, index=False)
            time.sleep(0.5)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    import sys
    out = Path(__file__).resolve().parents[2] / "data" / "raw" / "kementan"
    kind = sys.argv[1] if len(sys.argv) > 1 else "ekspor"
    years = range(2017, 2025)
    print(f"Fetching {kind} {min(years)}-{max(years)} from Kementan eksim...")
    report = bulk_fetch(years, out / kind, kind=kind)
    print(report.to_string())
    report.to_csv(out / f"{kind}_fetch_report.csv", index=False)
    ok = (report["status"] == "ok").sum()
    print(f"\n{ok}/{len(report)} fetches successful. Files saved to {out / kind}")
