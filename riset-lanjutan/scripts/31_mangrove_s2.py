"""Tahap 31: konteks lapangan per lintasan (dipakai 26_ekspor_web.py).
Aturan dikunci sebelum hasil (18 Okt 2026):
- mangrove: jarak pusat bercak ke poligon Global Mangrove Watch v3 2020 (sat-io, GEE), dicari sampai 20 km;
  bercak "dekat mangrove" bila <= 5 km. Penanda prioritas lapangan (pesisir sensitif), bukan bukti minyak.
- Sentinel-2: citra L2A (S2_SR_HARMONIZED) dalam ±1 hari dari lintasan radar, CLOUDY_PIXEL_PERCENTAGE < 60, mosaik warna asli
  (B4/B3/B2, 0–3000); ditampilkan hanya bila menutup >= 25% kotak lintasan. Hanya pembanding visual; beda waktu dan awan dicatat. Tidak ada = tidak ditampilkan.
"""
import os, urllib.request
import numpy as np, ee

MG = "projects/sat-io/open-datasets/GMW/extent/gmw_v3_2020_vec"
DEKAT_KM, CARI_M = 5.0, 20000
_init = False


def _ee():
    global _init
    if not _init:
        ee.Initialize(project="bledos"); _init = True


def mangrove_km(titik):
    """Jarak (km) tiap titik (lon, lat) ke mangrove terdekat; None bila > 20 km."""
    _ee()
    lo = [t[0] for t in titik]; la = [t[1] for t in titik]
    box = ee.Geometry.Rectangle([min(lo), min(la), max(lo), max(la)]).buffer(CARI_M)
    dist = ee.FeatureCollection(MG).filterBounds(box).distance(CARI_M)
    fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([x, y]), {"i": i}) for i, (x, y) in enumerate(titik)])
    r = dist.reduceRegions(fc, ee.Reducer.first(), 30).getInfo()["features"]
    v = [None] * len(titik)
    for f in r:
        d = f["properties"].get("first")
        v[f["properties"]["i"]] = None if d is None else round(d / 1000, 1)
    return v


def s2_overlay(tanggal, bounds, out_png):
    """bounds = [[S, W], [N, E]]. Simpan PNG warna asli bila ada; kembalikan dict info atau None."""
    _ee()
    (S, W), (N, E) = bounds; g = ee.Geometry.Rectangle([W, S, E, N])
    d0 = ee.Date(tanggal)
    c = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(g).filterDate(d0.advance(-1, "day"), d0.advance(2, "day"))
         .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 60)))
    n = c.size().getInfo()
    if n == 0:
        return None
    info = c.aggregate_array("CLOUDY_PIXEL_PERCENTAGE").getInfo(); tgl = c.aggregate_array("system:time_start").getInfo()
    mos = c.mosaic()
    cak = mos.select("B4").mask().gt(0).unmask(0).reduceRegion(ee.Reducer.mean(), g, 500, maxPixels=1e9).get("B4").getInfo() or 0
    if cak < 0.25:
        return {"ditampilkan": False, "cakupan": round(cak, 2)}
    im = mos.select(["B4", "B3", "B2"]).visualize(min=0, max=3000)
    url = im.getThumbURL({"region": g, "dimensions": 1400, "format": "png", "crs": "EPSG:4326"})
    urllib.request.urlretrieve(url, out_png)
    import datetime as dt
    return {"ditampilkan": True, "cakupan": round(cak, 2), "ubin": n, "awan_persen": round(float(np.mean(info)), 0),
            "tanggal": sorted({dt.datetime.utcfromtimestamp(t / 1000).strftime("%Y-%m-%d") for t in tgl})}
