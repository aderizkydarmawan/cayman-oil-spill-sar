"""Tahap 30: penanda hujan per bercak dari GPM IMERG V07 (setengah jam, 0,1°) di GEE.
Aturan dikunci sebelum hasil (18 Okt 2026):
- waktu lintasan = system:time_start citra Sentinel-1 IW pertama yang menutupi pusat bercak pada tanggal itu;
- citra IMERG = slot 30 menit yang memuat waktu itu; nilai = maks 'precipitation' (mm/jam) dalam radius 5 km dari pusat bercak;
- bercak "mungkin hujan" bila >= 1 mm/jam. Hanya PENANDA (tidak membuang bercak). Resolusi IMERG ±11 km: kasar.
- dilaporkan: fraksi bercak hujan pada lintasan bersih vs bercak minyak (label lemah tahap 17).
Keluaran: results_pembeda/hujan_objek.csv, hujan_ringkasan.json
Pemakaian: python scripts/30_hujan_gpm.py            (semua objek fitur_objek.csv)
           fungsi hujan_titik(tanggal, [(lon, lat), ...]) dipakai 26_ekspor_web.py
"""
import json, os
import numpy as np, pandas as pd, rasterio, ee
from rasterio.warp import transform as wtransform

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); OUT = os.path.join(HERE, "results_pembeda")
AMBANG, RADIUS = 1.0, 5000
_init = False


def _ee():
    global _init
    if not _init:
        ee.Initialize(project="bledos"); _init = True


def hujan_titik(tanggal, titik):
    """Kembalikan (waktu_lintasan_iso, daftar mm/jam maks per titik) atau (None, [nan,...]) bila tak ada data."""
    _ee()
    d0 = ee.Date(tanggal); lon, lat = np.mean([t[0] for t in titik]), np.mean([t[1] for t in titik])
    s1 = (ee.ImageCollection("COPERNICUS/S1_GRD").filterDate(d0, d0.advance(1, "day"))
          .filter(ee.Filter.eq("instrumentMode", "IW")).filterBounds(ee.Geometry.Point([lon, lat])))
    if s1.size().getInfo() == 0:
        return None, [np.nan] * len(titik)
    t = ee.Date(s1.first().get("system:time_start"))
    ic = ee.ImageCollection("NASA/GPM_L3/IMERG_V07").filterDate(t.advance(-30, "minute"), t.advance(1, "second"))
    if ic.size().getInfo() == 0:
        return t.format().getInfo(), [np.nan] * len(titik)
    im = ic.sort("system:time_start", False).first()
    fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([x, y]).buffer(RADIUS), {"i": i}) for i, (x, y) in enumerate(titik)])
    r = ee.Image(im).select("precipitation").reduceRegions(fc, ee.Reducer.max(), 1000).getInfo()["features"]  # skala 1 km: radius 5 km < piksel IMERG 11 km
    v = [np.nan] * len(titik)
    for f in r:
        v[f["properties"]["i"]] = f["properties"].get("max", np.nan)
    return t.format().getInfo(), [np.nan if x is None else float(x) for x in v]


if __name__ == "__main__":
    from situs import _S as SITUS
    lok = pd.read_csv(os.path.join(OUT, "fitur_objek.csv"))
    rows = []
    for (s, d), g in lok.groupby(["situs", "date"]):
        cfg = SITUS[s]; f = os.path.join(HERE, cfg["data"], f"s1_vv_db_{d}_20m.tif")
        with rasterio.open(f) as src:
            xs, ys = rasterio.transform.xy(src.transform, g.py.values, g.px_.values)
            lo, la = wtransform(src.crs, "EPSG:4326", xs, ys)
        try:
            tm, v = hujan_titik(str(d), list(zip(lo, la)))
        except Exception as e:
            print("gagal", s, d, e, flush=True); tm, v = None, [np.nan] * len(g)
        for (i, r), mm in zip(g.iterrows(), v):
            rows.append({"situs": s, "date": d, "label": r.label, "km2": r.km2, "waktu": tm, "hujan_mmjam": mm})
        print(s, d, tm, np.nanmax(v) if len(v) and np.isfinite(v).any() else None, flush=True)
    h = pd.DataFrame(rows); h["hujan"] = h.hujan_mmjam >= AMBANG
    h.to_csv(os.path.join(OUT, "hujan_objek.csv"), index=False)
    res = {"objek": len(h), "tanpa_data": int(h.hujan_mmjam.isna().sum()),
           "fraksi_hujan_bersih": round(float(h[h.label == 0].hujan.mean()), 3),
           "fraksi_hujan_minyak": round(float(h[h.label == 1].hujan.mean()), 3),
           "lintasan_dengan_hujan": int(h.groupby(["situs", "date"]).hujan.any().sum()), "lintasan": int(h.groupby(["situs", "date"]).ngroups)}
    json.dump(res, open(os.path.join(OUT, "hujan_ringkasan.json"), "w"), indent=1); print(res)
