"""Konfigurasi lokasi. Pilih dengan variabel lingkungan SITUS (bawaan: balikpapan, agar hasil lama tetap sama).
Aturan model (skala -32..-17 dB, ambang, objek >=0,1 km², cincin 1-3 km, ambang angin) TIDAK diatur di sini: sama untuk semua lokasi.
"""
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_S = {
    "balikpapan": dict(
        bbox=[116.70, -1.45, 117.10, -1.05], crs="EPSG:32750", orbit=32, era5_hour="22:00",
        look_az=282.0,  # menurun: heading ~192° + 90° (right-looking)
        spill_ref="2018-04-01", spill=("2018-03-31", "2018-05-01"), years=("2017-01-01", "2020-01-01"),
        data="data", results="results",
        inner=lambda E_km, N_km: (N_km > 9862) & (E_km < 482)),   # Teluk Balikpapan bagian dalam
    "karawang": dict(
        # koordinat sumur YYA-1 tidak ditemukan; AOI lebar perairan utara Karawang (sumur ±2 km dari pantai)
        bbox=[106.90, -6.20, 107.90, -5.60], crs="EPSG:32748", orbit=98, era5_hour="11:00",
        look_az=78.0,   # naik: heading ~348° + 90° (right-looking)
        # acuan 30 Jul 2019: dipilih sebelum uji alarm palsu (lapisan jelas; disebut terluas di satu sumber, belum diverifikasi)
        spill_ref="2019-07-30", spill=("2019-07-12", "2019-10-31"), years=("2017-01-01", "2020-01-01"),
        data="data_karawang", results="results_karawang",
        inner=lambda E_km, N_km: E_km < -1e9),                     # tidak ada zona teluk dalam
}
NAME = os.environ.get("SITUS", "balikpapan")
if NAME.startswith("kejadian:"):
    # kejadian tambahan dari kejadian_kandidat.csv; orbit, jam lintas & arah pandang dihitung per citra (tahap 13)
    import csv, math
    _id = NAME.split(":", 1)[1]
    _r = next(r for r in csv.DictReader(open(os.path.join(HERE, "kejadian_kandidat.csv"), encoding="utf-8")) if r["id"] == _id)
    _b = [float(_r[k]) for k in ["lon_min", "lat_min", "lon_max", "lat_max"]]
    _lon, _lat = (_b[0] + _b[2]) / 2, (_b[1] + _b[3]) / 2
    _S[NAME] = dict(bbox=_b, crs=f"EPSG:{(32600 if _lat >= 0 else 32700) + int((_lon + 180) // 6) + 1}", orbit=None,
                    era5_hour=None, look_az=None, spill_ref=_r["tgl_mulai"], spill=(_r["tgl_mulai"], _r["tgl_akhir"]),
                    years=None, data=os.path.join("data_kejadian", _id), results=os.path.join("results_kejadian", _id),
                    inner=lambda E_km, N_km: E_km < -1e9, label=_r["lokasi"])
S = _S[NAME]
LABEL = S.get("label", NAME.capitalize())
BBOX, CRS, ORBIT, ERA5_HOUR, LOOK_AZ = S["bbox"], S["crs"], S["orbit"], S["era5_hour"], S["look_az"]
SPILL, YEARS, INNER, SPILL_REF = S["spill"], S["years"], S["inner"], S["spill_ref"]
DATA, RESULTS = os.path.join(HERE, S["data"]), os.path.join(HERE, S["results"])
os.makedirs(DATA, exist_ok=True); os.makedirs(RESULTS, exist_ok=True)
