"""Tahap 1: cari citra Sentinel-1 GRD di Teluk Balikpapan sekitar tumpahan 31 Mar 2018.
Keluaran: data/daftar_citra_s1.csv
"""
import csv, os, ee

ee.Initialize(project=os.environ["EE_PROJECT"])  # isi dengan project GEE Anda
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# AOI: Teluk Balikpapan + mulut teluk ke Selat Makassar
AOI = ee.Geometry.Rectangle([116.70, -1.45, 117.10, -1.05])
START, END = "2018-03-20", "2018-05-01"

col = (ee.ImageCollection("COPERNICUS/S1_GRD")
       .filterBounds(AOI).filterDate(START, END)
       .filter(ee.Filter.eq("instrumentMode", "IW")))

props = ["system:index", "platform_number", "orbitProperties_pass",
         "relativeOrbitNumber_start", "transmitterReceiverPolarisation", "resolution_meters"]
info = col.map(lambda im: ee.Feature(None, {
    "id": im.get("system:index"),
    "time": im.date().format("YYYY-MM-dd HH:mm"),
    "platform": im.get("platform_number"),
    "pass": im.get("orbitProperties_pass"),
    "rel_orbit": im.get("relativeOrbitNumber_start"),
    "pol": ee.List(im.get("transmitterReceiverPolarisation")).join("+"),
    "aoi_cover_frac": im.geometry().intersection(AOI, 100).area(100).divide(AOI.area(100)),
})).getInfo()["features"]

rows = sorted([f["properties"] for f in info], key=lambda r: r["time"])
out = os.path.join(HERE, "data", "daftar_citra_s1.csv")
with open(out, "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=["time", "id", "platform", "pass", "rel_orbit", "pol", "aoi_cover_frac"])
    w.writeheader(); w.writerows(rows)
for r in rows:
    print(r["time"], r["platform"], r["pass"], r["rel_orbit"], r["pol"], round(r["aoi_cover_frac"], 2), r["id"])
print("total:", len(rows), "->", out)
