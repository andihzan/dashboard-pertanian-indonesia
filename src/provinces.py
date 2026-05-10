"""Master list of Indonesian provinces (38 provinces as of 2024).

Includes BPS province code, official name, ISO code, and region grouping.
Used as the canonical reference across all data sources.
"""

PROVINCES = [
    {"code": "11", "name": "Aceh", "iso": "ID-AC", "region": "Sumatera"},
    {"code": "12", "name": "Sumatera Utara", "iso": "ID-SU", "region": "Sumatera"},
    {"code": "13", "name": "Sumatera Barat", "iso": "ID-SB", "region": "Sumatera"},
    {"code": "14", "name": "Riau", "iso": "ID-RI", "region": "Sumatera"},
    {"code": "15", "name": "Jambi", "iso": "ID-JA", "region": "Sumatera"},
    {"code": "16", "name": "Sumatera Selatan", "iso": "ID-SS", "region": "Sumatera"},
    {"code": "17", "name": "Bengkulu", "iso": "ID-BE", "region": "Sumatera"},
    {"code": "18", "name": "Lampung", "iso": "ID-LA", "region": "Sumatera"},
    {"code": "19", "name": "Kepulauan Bangka Belitung", "iso": "ID-BB", "region": "Sumatera"},
    {"code": "21", "name": "Kepulauan Riau", "iso": "ID-KR", "region": "Sumatera"},
    {"code": "31", "name": "DKI Jakarta", "iso": "ID-JK", "region": "Jawa"},
    {"code": "32", "name": "Jawa Barat", "iso": "ID-JB", "region": "Jawa"},
    {"code": "33", "name": "Jawa Tengah", "iso": "ID-JT", "region": "Jawa"},
    {"code": "34", "name": "DI Yogyakarta", "iso": "ID-YO", "region": "Jawa"},
    {"code": "35", "name": "Jawa Timur", "iso": "ID-JI", "region": "Jawa"},
    {"code": "36", "name": "Banten", "iso": "ID-BT", "region": "Jawa"},
    {"code": "51", "name": "Bali", "iso": "ID-BA", "region": "Bali Nusa Tenggara"},
    {"code": "52", "name": "Nusa Tenggara Barat", "iso": "ID-NB", "region": "Bali Nusa Tenggara"},
    {"code": "53", "name": "Nusa Tenggara Timur", "iso": "ID-NT", "region": "Bali Nusa Tenggara"},
    {"code": "61", "name": "Kalimantan Barat", "iso": "ID-KB", "region": "Kalimantan"},
    {"code": "62", "name": "Kalimantan Tengah", "iso": "ID-KT", "region": "Kalimantan"},
    {"code": "63", "name": "Kalimantan Selatan", "iso": "ID-KS", "region": "Kalimantan"},
    {"code": "64", "name": "Kalimantan Timur", "iso": "ID-KI", "region": "Kalimantan"},
    {"code": "65", "name": "Kalimantan Utara", "iso": "ID-KU", "region": "Kalimantan"},
    {"code": "71", "name": "Sulawesi Utara", "iso": "ID-SA", "region": "Sulawesi"},
    {"code": "72", "name": "Sulawesi Tengah", "iso": "ID-ST", "region": "Sulawesi"},
    {"code": "73", "name": "Sulawesi Selatan", "iso": "ID-SN", "region": "Sulawesi"},
    {"code": "74", "name": "Sulawesi Tenggara", "iso": "ID-SG", "region": "Sulawesi"},
    {"code": "75", "name": "Gorontalo", "iso": "ID-GO", "region": "Sulawesi"},
    {"code": "76", "name": "Sulawesi Barat", "iso": "ID-SR", "region": "Sulawesi"},
    {"code": "81", "name": "Maluku", "iso": "ID-MA", "region": "Maluku Papua"},
    {"code": "82", "name": "Maluku Utara", "iso": "ID-MU", "region": "Maluku Papua"},
    {"code": "91", "name": "Papua Barat", "iso": "ID-PB", "region": "Maluku Papua"},
    {"code": "92", "name": "Papua Barat Daya", "iso": "ID-PD", "region": "Maluku Papua"},
    {"code": "94", "name": "Papua", "iso": "ID-PA", "region": "Maluku Papua"},
    {"code": "95", "name": "Papua Selatan", "iso": "ID-PS", "region": "Maluku Papua"},
    {"code": "96", "name": "Papua Tengah", "iso": "ID-PT", "region": "Maluku Papua"},
    {"code": "97", "name": "Papua Pegunungan", "iso": "ID-PE", "region": "Maluku Papua"},
]

PROVINCE_NAMES = [p["name"] for p in PROVINCES]
PROVINCE_BY_NAME = {p["name"]: p for p in PROVINCES}
PROVINCE_BY_CODE = {p["code"]: p for p in PROVINCES}

NEW_PROVINCES_2022 = {"Papua Barat Daya", "Papua Selatan", "Papua Tengah", "Papua Pegunungan"}
