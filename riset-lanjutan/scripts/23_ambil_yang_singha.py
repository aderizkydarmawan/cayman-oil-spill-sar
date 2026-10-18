"""Tahap 23: ambil ulang patch dataset Yang & Singha 2025 (PANGAEA 980773, CC-BY-4.0) dari GEE dengan cara olah aplikasi:
VV & VH dB (median 3x3), masker laut JRC occ>50, grid UTM lokal 20 m, kotak = sudut patch dari metadata.
Kotak objek minyak (lat/lon) dirasterkan jadi masker kotak.
Keluaran: ../data_terbuka/yang_singha/gee/<patch>.npz  (vv, vh, sea, kotak, transform, crs, set)
Pemakaian: python scripts/23_ambil_yang_singha.py
"""
import os, io
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np, pandas as pd, ee
from rasterio.warp import transform as wt

ee.Initialize(project=os.environ["EE_PROJECT"])  # isi dengan project GEE Anda
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "..", "data_terbuka", "yang_singha"); OUT = os.path.join(SRC, "gee"); os.makedirs(OUT, exist_ok=True)
PX = 20
lines = open(os.path.join(SRC, "daftar.tab"), encoding="utf-8").read().split("\n")
k = next(i for i, l in enumerate(lines) if l.startswith("*/"))
df = pd.read_csv(io.StringIO("\n".join(lines[k + 1:])), sep="\t")
df.columns = ["set", "jpg", "xml", "tag", "patch", "t0", "t1", "sid", "w", "h",
              "ul_lon", "ul_lat", "ur_lon", "ur_lat", "br_lon", "br_lat", "bl_lon", "bl_lat",
              "oul_lon", "oul_lat", "our_lon", "our_lat", "obr_lon", "obr_lat", "obl_lon", "obl_lat",
              "xmin", "ymin", "xmax", "ymax", "size"][:len(df.columns)]
df["jpg"] = df.jpg.ffill(); df["set"] = df.set.ffill(); df["sid"] = df.sid.ffill()
for c in ["ul_lon", "ul_lat", "ur_lon", "ur_lat", "br_lon", "br_lat", "bl_lon", "bl_lat"]:
    df[c] = df.groupby("jpg")[c].transform("first")
print(df.set.value_counts().to_dict(), "| patch:", df.jpg.nunique())
# laut = bukan darat (Hansen datamask != 1; laut lepas = 0) ATAU air permanen JRC (teluk/perairan dalam yang Hansen tandai darat).
# v1 hanya memakai JRC -> laut lepas Mediterania tertandai darat (JRC tidak mencakup laut lepas). Diperbaiki 18 Okt 2026.
water = (ee.Image("UMD/hansen/global_forest_change_2025_v1_13").select("datamask").neq(1)
         .Or(ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").gt(50).unmask(0))).rename("sea").toFloat()


def ambil(jpg, g):
    fn = os.path.join(OUT, jpg.replace(".jpg", ".npz"))
    if os.path.exists(fn):
        z = dict(np.load(fn, allow_pickle=True))
        if "sea_v2" in z:
            return jpg, "ada"
        # patch lama: ambil ulang masker laut saja dengan grid yang sama
        x0, y1, px = z["transform"]; ny, nx = z["vv"].shape
        a = ee.data.computePixels({"expression": water, "fileFormat": "NUMPY_NDARRAY", "bandIds": ["sea"],
                                   "grid": {"dimensions": {"width": nx, "height": ny},
                                            "affineTransform": {"scaleX": px, "shearX": 0, "translateX": x0, "shearY": 0, "scaleY": -px, "translateY": y1},
                                            "crsCode": str(z["crs"])}})
        z["sea"] = a["sea"].astype(np.uint8); z["sea_v2"] = True
        np.savez_compressed(fn, **z)
        return jpg, "ok"
    r = g.iloc[0]
    lons = [r.ul_lon, r.ur_lon, r.br_lon, r.bl_lon]; lats = [r.ul_lat, r.ur_lat, r.br_lat, r.bl_lat]
    lon0, lat0 = np.mean(lons), np.mean(lats)
    crs = f"EPSG:{(32600 if lat0 >= 0 else 32700) + int((lon0 + 180) // 6) + 1}"
    x, y = wt("EPSG:4326", crs, lons, lats)
    x0, y1 = np.floor(min(x) / PX) * PX, np.ceil(max(y) / PX) * PX
    nx, ny = int((max(x) - x0) // PX), int((y1 - min(y)) // PX)
    # sebagian patch berasal dari 2 citra bersambung: ID dipisah ';' -> mosaik
    ids = [s.strip().replace(".SAFE", "") for s in str(r.sid).split(";") if s.strip()]
    im = ee.ImageCollection([ee.Image("COPERNICUS/S1_GRD/" + i) for i in ids]).mosaic() if len(ids) > 1 else ee.Image("COPERNICUS/S1_GRD/" + ids[0])
    bands = im.bandNames().getInfo()
    sel = [b for b in ["VV", "VH"] if b in bands]
    st = im.select(sel).focalMedian(1.5, "square", "pixels").addBands(water)
    a = ee.data.computePixels({"expression": st, "fileFormat": "NUMPY_NDARRAY", "bandIds": sel + ["sea"],
                               "grid": {"dimensions": {"width": nx, "height": ny},
                                        "affineTransform": {"scaleX": PX, "shearX": 0, "translateX": x0, "shearY": 0, "scaleY": -PX, "translateY": y1},
                                        "crsCode": crs}})
    kotak = np.zeros((ny, nx), np.uint8)
    if str(r.set).startswith("o"):
        for _, o in g.iterrows():
            if pd.isna(o.oul_lon):
                continue
            ox, oy = wt("EPSG:4326", crs, [o.oul_lon, o.our_lon, o.obr_lon, o.obl_lon], [o.oul_lat, o.our_lat, o.obr_lat, o.obl_lat])
            c0, c1 = int((min(ox) - x0) / PX), int(np.ceil((max(ox) - x0) / PX))
            r0, r1 = int((y1 - max(oy)) / PX), int(np.ceil((y1 - min(oy)) / PX))
            kotak[max(r0, 0):r1, max(c0, 0):c1] = 1
    np.savez_compressed(fn, vv=a["VV"].astype(np.float32), vh=a["VH"].astype(np.float32) if "VH" in sel else np.zeros(0),
                        sea=a["sea"].astype(np.uint8), kotak=kotak, transform=np.array([x0, y1, PX]), crs=crs, set=r.set,
                        n_obj=int(g.oul_lon.notna().sum()), sid=r.sid, sea_v2=True)
    return jpg, "ok"


hasil = {"ok": 0, "ada": 0, "gagal": 0}
with ThreadPoolExecutor(12) as ex:
    fut = [ex.submit(ambil, j, g) for j, g in df.groupby("jpg")]
    for i, f in enumerate(as_completed(fut)):
        try:
            hasil[f.result()[1]] += 1
        except Exception as e:
            hasil["gagal"] += 1
            if hasil["gagal"] <= 5: print("gagal:", str(e)[:120])
        if i % 200 == 0: print(i, hasil, flush=True)
print("selesai", hasil)
