# Dashboard Sektor Pertanian Indonesia (2014–2024)

Dashboard interaktif untuk memvisualisasikan **kredit, ekspor, dan impor sektor pertanian per provinsi** di Indonesia, dengan rentang data 2014–2024 dan **hanya menggunakan sumber resmi**.

## Quick start

```bash
# install dependencies
pip install -r requirements.txt

# generate demo data (sudah di-run sekali — file ada di data/sample/)
python -m src.seed_demo

# jalankan dashboard
streamlit run app.py
```

Buka http://localhost:8501

## Status Data

Saat ini sudah ada **101 baris data riil** dari publikasi BPS 2023 (ekspor 34 provinsi × 3 tahun: 2021, 2022, 2023, sektor "Pertanian, Kehutanan & Perikanan"). Sisanya masih data demo. Dashboard otomatis menggantikan demo dengan riil pada (tahun, provinsi) yang sudah punya data BPS.

### Pilot BPS PDF Parser (sudah jalan)

Workflow yang sudah berhasil ditest:
1. Chrome MCP digunakan untuk mendapat direct URL `web-api.bps.go.id/download.php?f=...` dari halaman publikasi BPS (yang di-gate Cloudflare untuk akses biasa).
2. Download PDF 12 MB (814 halaman) via curl.
3. Parser `src/ingest/bps_pdf_parser.py` mengekstrak tabel "Tabel 3.X Perkembangan Nilai Ekspor Asal Barang [Provinsi] Menurut Sektor" untuk semua 34 provinsi yang ada di publikasi.
4. Hasil disimpan ke `data/raw/bps/ekspor_pertanian_{2021,2022,2023}.csv`.

Untuk replicate dengan tahun lain (2014–2022, 2024):
```bash
# 1. Download via Chrome MCP atau manual dari bps.go.id
# 2. Simpan ke data/raw/bps/source/bps_ekspor_provinsi_{YYYY}.pdf
# 3. Parse:
python -m src.ingest.bps_pdf_parser data/raw/bps/source/bps_ekspor_provinsi_{YYYY}.pdf
```

| Dataset | Sumber resmi | Otomatis? | Catatan |
|---|---|---|---|
| Kredit pertanian | [Bank Indonesia SEKDA](https://www.bi.go.id/id/statistik/ekonomi-keuangan/sekda/default.aspx), [OJK SPI](https://ojk.go.id/id/kanal/perbankan/data-dan-statistik/statistik-perbankan-indonesia/default.aspx), [OJK Portal Data](https://data.ojk.go.id/SJKPublic) | Manual | Anti-scraping; perlu download Excel/PDF |
| Ekspor pertanian | [BPS Ekspor Menurut Provinsi Asal](https://www.bps.go.id/id/publication?keyword=ekspor+menurut+provinsi), [Kementan eksim](https://app3.pertanian.go.id/eksim/) | Sebagian | Kementan auto-fetch (2017–2024); BPS manual |
| Impor pertanian | [BPS Impor per Pelabuhan Bongkar](https://www.bps.go.id/en/exim), [Kementan eksim](https://app3.pertanian.go.id/eksim/) | Sebagian | Sama seperti ekspor |

## Cara mengganti data demo dengan data riil

### 1. Kredit Pertanian per Provinsi

Buat file `data/raw/bi_sekda_consolidated.csv` dengan kolom:

```
tahun,provinsi,jenis_kredit,nilai_miliar_rp,sumber,status
2024,Jawa Barat,Modal Kerja,12345.6,BI SEKDA,real
2024,Jawa Barat,Investasi,9876.5,BI SEKDA,real
...
```

Sumber download:
- BI SEKDA: pilih provinsi → tabel "Posisi Pinjaman Bank Umum menurut Lapangan Usaha"
- OJK SPI: bulanan PDF, ekstrak tabel "Kredit Bank Umum berdasarkan Sektor Lapangan Usaha"

`provinsi` harus persis sesuai nama di [`src/provinces.py`](src/provinces.py).
`jenis_kredit` valid: `Modal Kerja`, `Investasi`, `Konsumsi`, `Total`.

### 2. Ekspor Pertanian per Provinsi

Buat file `data/raw/bps/ekspor_pertanian_{YYYY}.csv` per tahun, dengan kolom:

```
provinsi,subsektor,volume_ton,nilai_juta_usd
Riau,Perkebunan,5234567.0,5821.3
Sumatera Utara,Perkebunan,3456789.0,3982.1
...
```

`subsektor` valid: `Tanaman Pangan`, `Hortikultura`, `Perkebunan`, `Peternakan`.

Sumber download:
- **2014–2016**: [BPS publikasi tahunan](https://www.bps.go.id/id/publication?keyword=ekspor+menurut+provinsi)
- **2017–2024**: [Kementan eksim](https://app3.pertanian.go.id/eksim/eksporProvAsal.php) atau [Portal Statistik Kementan](https://11ap.pertanian.go.id/portalstatistik/ekspor/provinsi)

### 3. Impor Pertanian per Provinsi

Buat file `data/raw/bps/impor_pertanian_{YYYY}.csv` dengan kolom yang sama dengan ekspor. Catatan: data impor BPS dilaporkan menurut **provinsi pelabuhan bongkar**, bukan provinsi tujuan akhir.

### Auto-fetcher Kementan (best effort)

```bash
python -m src.ingest.kementan_eksim ekspor   # fetch 2017-2024
python -m src.ingest.kementan_eksim impor
```

Output akan masuk ke `data/raw/kementan/{ekspor|impor}/`. Cek `*_fetch_report.csv` untuk status. Karena Kementan eksim menggunakan struktur HTML legacy, beberapa kombinasi (tahun, subsektor) mungkin gagal — fallback ke download manual via UI.

## Struktur Project

```
.
├── app.py                       # Streamlit dashboard
├── requirements.txt
├── README.md
├── data/
│   ├── raw/                     # data riil hasil download (kosong di awal)
│   │   ├── bi_sekda_consolidated.csv         # ← isi untuk kredit
│   │   ├── bps/
│   │   │   ├── ekspor_pertanian_{YYYY}.csv   # ← isi per tahun
│   │   │   └── impor_pertanian_{YYYY}.csv
│   │   └── kementan/
│   │       └── ekspor/, impor/               # ← output auto-fetcher
│   ├── sample/                  # data demo (already generated)
│   │   ├── kredit_demo.csv
│   │   ├── ekspor_demo.csv
│   │   └── impor_demo.csv
│   └── processed/               # reserved untuk ETL output
└── src/
    ├── provinces.py             # 38 provinsi canonical
    ├── schema.py                # column schema
    ├── seed_demo.py             # generator demo CSV
    ├── ingest/
    │   ├── kementan_eksim.py    # auto-fetcher Kementan
    │   ├── bi_sekda.py          # loader BI SEKDA (manual download)
    │   └── bps_ekspor.py        # loader BPS (manual download)
    └── transform/
        └── loader.py            # konsolidasi semua sumber
```

## Logic prioritas data

`load_kredit/ekspor/impor()` di [`src/transform/loader.py`](src/transform/loader.py) menggabungkan:
1. **Real** dari `data/raw/...`
2. **Demo** dari `data/sample/...`

Real selalu menggantikan demo pada (tahun, provinsi, kategori) yang sama. Jadi seiring Anda mengisi CSV riil, dashboard otomatis swap.

## Catatan Penting

- Data demo bukan untuk publikasi atau analisis riil — gunakan hanya untuk validasi UI.
- Skema BPS klasifikasi sektor pertanian berubah dari KBLI 2009 ke 2015. Untuk seri 2014–2019 vs 2020–2024 perlu rekonsiliasi konsep.
- Pemekaran provinsi 2022 (Papua Barat Daya, Papua Selatan, Papua Tengah, Papua Pegunungan) menyebabkan data sebelum 2022 tidak punya nilai untuk provinsi-provinsi tersebut — sudah di-handle di seeder.
