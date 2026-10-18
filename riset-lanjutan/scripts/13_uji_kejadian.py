"""Tahap 13: jalankan alat yang sama (tanpa mengubah aturan) pada kejadian tambahan di kejadian_kandidat.csv.
Pemakaian (dari folder uji-gee-balikpapan): python scripts/13_uji_kejadian.py [id ...]
Per kejadian: maks. 3 citra Sentinel-1 dalam jendela kejadian (tersebar rata) -> unduh 20 m (paralel) -> inferensi
skala tetap -32..-17 dB -> angin per objek (CMOD5.N, cincin 1-3 km; jam & arah lintas dari metadata citra) -> laporan.
Ringkasan: results_kejadian/ringkasan_kejadian.csv
"""
import csv, json, os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
import numpy as np, pandas as pd, rasterio, ee
from scipy import ndimage as ndi
from rasterio.warp import transform as warp_xy

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SC = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SC); import cmod5n
from saring import bersihkan
ee.Initialize(project="bledos")
MIN_KM2, R_IN, R_OUT, WIND_LOW, MAX_SCENES, WORKERS = 0.1, 1000, 3000, 3.0, 3, 8
MODEL = "unet_lite_bersih"   # mask U-Net setelah saring.py
SKIP = {"balikpapan_2018", "karawang_2019"}      # sudah diuji di tahap 1-10
ev = [r for r in csv.DictReader(open(os.path.join(HERE, "kejadian_kandidat.csv"), encoding="utf-8")) if r["id"] not in SKIP]
if len(sys.argv) > 1:
    ev = [r for r in ev if r["id"] in sys.argv[1:]]


def env(i):
    return dict(os.environ, SITUS=f"kejadian:{i}", PYTHONIOENCODING="utf-8")


def scenes(r):
    b = [float(r[k]) for k in ["lon_min", "lat_min", "lon_max", "lat_max"]]
    c = (ee.ImageCollection("COPERNICUS/S1_GRD").filterBounds(ee.Geometry.Rectangle(b))
         .filterDate(r["tgl_mulai"], ee.Date(r["tgl_akhir"]).advance(1, "day"))
         .filter(ee.Filter.eq("instrumentMode", "IW")).filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV")))
    info = c.reduceColumns(ee.Reducer.toList(2), ["system:time_start", "orbitProperties_pass"]).get("list").getInfo()
    by = {}
    for t, p in sorted(info):
        d = pd.Timestamp(t, unit="ms").strftime("%Y-%m-%d"); by.setdefault(d, (t, p))
    ds = sorted(by)
    pick = [ds[int(round(k))] for k in np.linspace(0, len(ds) - 1, min(MAX_SCENES, len(ds)))] if ds else []
    return b, [(d, *by[d]) for d in dict.fromkeys(pick)]


plan = []
for r in ev:
    b, sc = scenes(r)
    for d, t, p in sc:
        plan.append((r, b, d, t, p))
print(f"{len(ev)} kejadian, {len(plan)} citra", flush=True)


def download(job):
    r, b, d, t, p = job
    from situs import _S  # noqa: F401  (hanya untuk memastikan modul bisa dimuat)
    dd = os.path.join(HERE, "data_kejadian", r["id"])
    if os.path.exists(os.path.join(dd, f"s1_vv_db_{d}_20m.tif")):
        return job, "ada"
    out = subprocess.run([sys.executable, os.path.join(SC, "02_unduh_citra.py"), d, "20"], env=env(r["id"]),
                         capture_output=True, text=True, encoding="utf-8")
    return job, "ok" if out.returncode == 0 else "GAGAL " + out.stderr[-300:]


from concurrent.futures import as_completed
GD = 0.01
rows_sum = []
ex = ThreadPoolExecutor(WORKERS)
futs = [ex.submit(download, j) for j in plan]
def done_jobs():          # proses tiap citra begitu unduhannya selesai (unduhan lain tetap berjalan)
    for f in as_completed(futs):
        job, st = f.result(); print("unduh", job[0]["id"], job[2], st, flush=True); yield job
for r, b, d, t, p in done_jobs():
    i = r["id"]; DATA = os.path.join(HERE, "data_kejadian", i); RES = os.path.join(HERE, "results_kejadian", i)
    tif = os.path.join(DATA, f"s1_vv_db_{d}_20m.tif")
    if not os.path.exists(tif):
        continue
    od = os.path.join(RES, f"s1_vv_db_{d}_20m_fixed-32_-17")
    if not os.path.exists(os.path.join(od, "mask_unet_lite.tif")):
        subprocess.run([sys.executable, os.path.join(SC, "03_inferensi.py"), tif, "fixed:-32:-17"], env=env(i),
                       capture_output=True, check=True)
    # angin per objek (logika sama dengan tahap 9; jam ERA5 = jam lintas dibulatkan, arah pandang dari arah orbit)
    look_az = 78.0 if p == "ASCENDING" else 282.0
    t0 = pd.Timestamp(t, unit="ms").round("h")
    with rasterio.open(tif) as s:
        db, sea, tr, crs = s.read(1), s.read(2) > 0, s.transform, s.crs
    with rasterio.open(os.path.join(od, "mask_unet_lite.tif")) as s:
        mk0, prof = s.read(1) > 0, s.profile
    mk, flag = bersihkan(db, sea, mk0, tr.a)          # tahap 13b: buang tepi sapuan, tandai lintasan laut tenang
    with rasterio.open(os.path.join(od, f"mask_{MODEL}.tif"), "w", **dict(prof, dtype="uint8", nodata=None)) as dst:
        dst.write(mk.astype("uint8"), 1)
    json.dump(flag, open(os.path.join(od, f"saring_{MODEL}.json"), "w"))
    W_, S_, E_, N_ = b
    s1 = (ee.ImageCollection("COPERNICUS/S1_GRD").filterBounds(ee.Geometry.Rectangle(b)).filterDate(d, ee.Date(d).advance(1, "day"))
          .filter(ee.Filter.eq("instrumentMode", "IW")).select("angle").mosaic())
    era = ee.ImageCollection("ECMWF/ERA5/HOURLY").filterDate(t0.strftime("%Y-%m-%dT%H:00"), (t0 + pd.Timedelta(hours=1)).strftime("%Y-%m-%dT%H:00")).first()
    img = era.select(["u_component_of_wind_10m", "v_component_of_wind_10m"], ["u", "v"]).resample("bilinear").addBands(s1.rename("angle"))
    nx, ny = int(round((E_ - W_) / GD)), int(round((N_ - S_) / GD))
    a = ee.data.computePixels({"expression": img, "fileFormat": "NUMPY_NDARRAY", "bandIds": ["u", "v", "angle"],
                               "grid": {"dimensions": {"width": nx, "height": ny},
                                        "affineTransform": {"scaleX": GD, "shearX": 0, "translateX": W_, "shearY": 0, "scaleY": -GD, "translateY": N_},
                                        "crsCode": "EPSG:4326"}})
    g = {k: a[k].astype(float) for k in ["u", "v", "angle"]}
    smp = lambda k, lon, lat: g[k][min(max(int((N_ - lat) / GD), 0), ny - 1), min(max(int((lon - W_) / GD), 0), nx - 1)]
    lin = np.where(np.isfinite(db), 10 ** (db / 10), np.nan); px = tr.a
    lab, n = ndi.label(mk, structure=np.ones((3, 3))); rows = []
    for k, sl in enumerate(ndi.find_objects(lab) if n else [], start=1):
        area = (lab[sl] == k).sum() * px ** 2 / 1e6
        if area < MIN_KM2:
            continue
        pad = int(np.ceil(R_OUT / px)) + 1
        y0, y1 = max(sl[0].start - pad, 0), min(sl[0].stop + pad, mk.shape[0]); x0, x1 = max(sl[1].start - pad, 0), min(sl[1].stop + pad, mk.shape[1])
        ob = lab[y0:y1, x0:x1] == k
        ring = (ndi.distance_transform_edt(~ob) * px > R_IN) & (ndi.distance_transform_edt(~ob) * px <= R_OUT) & sea[y0:y1, x0:x1] & ~mk[y0:y1, x0:x1]
        cy, cx = np.argwhere(ob).mean(0) + [y0, x0]
        lon, lat = (v[0] for v in warp_xy(crs, "EPSG:4326", [tr.c + px * (cx + .5)], [tr.f - px * (cy + .5)]))
        u, v, inc = smp("u", lon, lat), smp("v", lon, lat), smp("angle", lon, lat)
        wdir = (np.degrees(np.arctan2(-u, -v)) + 360) % 360
        ws = float(cmod5n.invert(float(np.nanmedian(lin[y0:y1, x0:x1][ring])), inc, (wdir - look_az) % 360)[0]) \
            if ring.sum() >= 50 and np.isfinite(inc) else np.nan
        rows.append({"date": d, "model": MODEL, "obj": k, "km2": area, "lon": lon, "lat": lat,
                     "era5_ws": float(np.hypot(u, v)), "sar_ws_ring": round(ws, 2) if np.isfinite(ws) else np.nan})
    oc = os.path.join(RES, "objek_angin.csv")
    old = pd.read_csv(oc) if os.path.exists(oc) and os.path.getsize(oc) > 2 else pd.DataFrame()
    pd.concat([old[~((old.date == d) & (old.model == MODEL))] if len(old) else old, pd.DataFrame(rows)]).to_csv(oc, index=False)
    o = pd.DataFrame(rows)
    ok = o[o.sar_ws_ring >= WIND_LOW] if len(o) else o
    rows_sum.append({"id": i, "lokasi": r["lokasi"], "jenis": r["jenis"], "tgl_citra": d, "lintas": p,
                     "jam_utc": pd.Timestamp(t, unit="ms").strftime("%H:%M"),
                     "n_bercak": len(o), "luas_km2": round(o.km2.sum(), 2) if len(o) else 0,
                     "n_bercak_angin_cukup": len(ok), "luas_angin_cukup_km2": round(ok.km2.sum(), 2) if len(ok) else 0,
                     "bercak_terbesar_km2": round(o.km2.max(), 2) if len(o) else 0,
                     "angin_era5_median": round(o.era5_ws.median(), 1) if len(o) else np.nan, **flag})
    if len(o):
        subprocess.run([sys.executable, os.path.join(SC, "10_laporan_lintasan.py"), d, MODEL], env=env(i), capture_output=True)
    pd.DataFrame(rows_sum).to_csv(os.path.join(HERE, "results_kejadian", "ringkasan_kejadian_v2.csv"), index=False)   # simpan bertahap
    print("selesai", i, d, rows_sum[-1]["n_bercak"], "bercak", rows_sum[-1]["luas_km2"], "km2", flush=True)

out = os.path.join(HERE, "results_kejadian", "ringkasan_kejadian_v2.csv")
pd.DataFrame(rows_sum).to_csv(out, index=False); print("->", out)
