"""Tahap 26: ekspor hasil lintasan pilihan ke situs web statis (../aplikasi-web/data/).
Per lintasan: radar (PNG, diproyeksikan ke EPSG:4326, diperkecil) + GeoJSON bercak (poligon, luas, jarak pantai, skor pembeda tahap 25,
prioritas tinggi/rendah) + entri di kejadian.json. Pembeda = pembeda_vv2.joblib (tahap 28). Tidak ada bercak yang disembunyikan;
skor hanya untuk urutan (pemilah tidak lulus uji Trujillo). Bercak >= 10 km² selalu prioritas tinggi.
Pemakaian: python scripts/26_ekspor_web.py
"""
import csv, json, os, sys
import numpy as np, pandas as pd, rasterio, joblib
from rasterio import features
from rasterio.warp import calculate_default_transform, reproject, Resampling, transform_geom
from shapely.geometry import shape, mapping
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fitur_objek import fitur
from saring import bersihkan
from rasterio.warp import transform as wtransform
import importlib
alasan = importlib.import_module("29_shap_pembeda").alasan
hujan_titik = importlib.import_module("30_hujan_gpm").hujan_titik
_m31 = importlib.import_module("31_mangrove_s2")

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(HERE, "..", "aplikasi-web", "data"); os.makedirs(WEB, exist_ok=True)
P = joblib.load(os.path.join(HERE, "results_pembeda", "pembeda_vv2.joblib"))
KK = {r["id"]: r for r in csv.DictReader(open(os.path.join(HERE, "kejadian_kandidat.csv"), encoding="utf-8"))}
# (kunci, data dir, results dir, tanggal, judul, jenis, keterangan)
PILIH = [
    ("balikpapan_2018", "data", "results", "2018-04-01", "Teluk Balikpapan", "kejadian",
     "Pipa minyak mentah putus 31 Mar 2018; citra ±1 hari kemudian. Teluk tertutup, angin lemah."),
    ("karawang_2019", "data_karawang", "results_karawang", "2019-07-30", "Pesisir Karawang", "kejadian",
     "Kebocoran sumur YYA-1 (12 Jul 2019); citra 18 hari kemudian."),
    ("karawang_2019_biasa", "data_karawang", "results_karawang", "2019-01-19", "Pesisir Karawang (hari biasa)", "biasa",
     "Tanpa kejadian tercatat: contoh alarm palsu sehari-hari."),
    ("karawang_2021", "data_kejadian/karawang_2021", "results_kejadian/karawang_2021", "2021-04-26", None, "kejadian", None),
    ("seribu_2020a", "data_kejadian/seribu_2020a", "results_kejadian/seribu_2020a", "2020-08-13", None, "kejadian", None),
    ("seribu_2020b", "data_kejadian/seribu_2020b", "results_kejadian/seribu_2020b", "2020-10-12", None, "kejadian", None),
    ("singapura_2024", "data_kejadian/singapura_2024", "results_kejadian/singapura_2024", "2024-06-14", None, "kejadian", None),
    ("batam_2022_tenang", "data_kejadian/batam_2022", "results_kejadian/batam_2022", "2022-12-10", None, "tenang",
     "Lintasan didominasi laut tenang: hampir semua bercak tidak bisa dinilai."),
]
BESAR_KM2 = 10
idx = []
for key, dd, rd, d, judul, jenis, ket in PILIH:
    kid = key.rsplit("_", 1)[0] if key.endswith(("_biasa", "_tenang")) else key
    k = KK.get(kid, {})
    f = os.path.join(HERE, dd, f"s1_vv_db_{d}_20m.tif")
    run = os.path.join(HERE, rd, f"s1_vv_db_{d}_20m_fixed-32_-17")
    if not (os.path.exists(f) and os.path.exists(os.path.join(run, "mask_unet_lite.tif"))):
        print("lewati", key); continue
    with rasterio.open(f) as s:
        db, sea, tr, crs = s.read(1).astype(float), s.read(2) > 0, s.transform, s.crs
    mk = rasterio.open(os.path.join(run, "mask_unet_lite.tif")).read(1) > 0
    _, fl = bersihkan(db, sea, mk, tr.a)
    rows, lab = fitur(db, sea, mk, tr.a)
    df = pd.DataFrame(rows)
    feats = []
    if len(df):
        df["skor"] = P["model"].predict_proba(df[P["fitur"]])[:, 1]
        df["tinggi"] = (df.skor >= P["ambang"]) | (df.km2 >= BESAR_KM2)
        df["alasan"] = alasan(df)
        xs, ys = rasterio.transform.xy(tr, df.py.values, df.px_.values); lo, la = wtransform(crs, "EPSG:4326", xs, ys)
        _, df["hujan_mmjam"] = hujan_titik(d, list(zip(lo, la)))
        df["mangrove_km"] = _m31.mangrove_km(list(zip(lo, la)))
        df = df.sort_values(["tinggi", "skor"], ascending=False).reset_index(drop=True)
        for i, r in df.iterrows():
            reg = (lab == r.label_id).astype(np.uint8)
            g = shape(next(gg for gg, v in features.shapes(reg, mask=reg.astype(bool), transform=tr) if v == 1)).simplify(tr.a)
            g = transform_geom(crs, "EPSG:4326", mapping(g), precision=5)
            feats.append({"type": "Feature", "geometry": g, "properties": {
                "id": i + 1, "luas_km2": round(float(r.km2), 2), "jarak_pantai_km": round(float(r.jarak_pantai_km), 1),
                "kontras_db": round(float(r.kontras_db), 1), "skor": round(float(r.skor), 3),
                "status": "prioritas tinggi" if r.tinggi else "prioritas rendah", "alasan": r.alasan,
                "hujan_mmjam": None if pd.isna(r.hujan_mmjam) else round(float(r.hujan_mmjam), 1),
                "mangrove_km": None if r.mangrove_km is None or pd.isna(r.mangrove_km) else float(r.mangrove_km)}})
    json.dump({"type": "FeatureCollection", "features": feats}, open(os.path.join(WEB, f"{key}.geojson"), "w"))
    # radar -> EPSG:4326, maks 1600 px sisi panjang; darat dibuat transparan
    dst_t, w, h = calculate_default_transform(crs, "EPSG:4326", db.shape[1], db.shape[0], *rasterio.transform.array_bounds(*db.shape, tr)[::-1][::-1] if False else rasterio.transform.array_bounds(db.shape[0], db.shape[1], tr))
    sc = max(w, h) / 1600; w2, h2 = int(w / max(sc, 1)), int(h / max(sc, 1))
    dst_t2 = dst_t * dst_t.scale(w / w2, h / h2)
    out = np.full((h2, w2), np.nan, np.float32)
    reproject(np.where(np.isfinite(db) & (db != 0) & sea, db, np.nan).astype(np.float32), out, src_transform=tr, src_crs=crs,
              dst_transform=dst_t2, dst_crs="EPSG:4326", resampling=Resampling.average, src_nodata=np.nan, dst_nodata=np.nan)
    v = np.clip((out + 32) / 15, 0, 1); a = np.isfinite(out)
    rgba = np.dstack([np.nan_to_num(v * 255)] * 3 + [a * 255]).astype(np.uint8)
    Image.fromarray(rgba, "RGBA").save(os.path.join(WEB, f"{key}.png"), optimize=True)
    W_, N_ = dst_t2.c, dst_t2.f; E_, S_ = W_ + dst_t2.a * w2, N_ + dst_t2.e * h2
    s2 = _m31.s2_overlay(d, [[S_, W_], [N_, E_]], os.path.join(WEB, f"{key}_s2.png"))
    if not (s2 and s2.get("ditampilkan")):
        s2 = None
        if os.path.exists(os.path.join(WEB, f"{key}_s2.png")): os.remove(os.path.join(WEB, f"{key}_s2.png"))
    n_mg = int(sum(1 for x in feats if (x["properties"]["mangrove_km"] or 99) <= _m31.DEKAT_KM))
    n_cek = int(sum(1 for x in feats if x["properties"]["status"] == "prioritas tinggi"))
    idx.append({"kunci": key, "judul": judul or k.get("lokasi", key), "tanggal": d, "jenis": jenis,
                "keterangan": ket or k.get("jenis", ""), "sumber": k.get("sumber", ""),
                "bounds": [[S_, W_], [N_, E_]], "n_bercak": len(feats), "n_perlu_dicek": n_cek,
                "luas_total_km2": round(float(df.km2.sum()) if len(df) else 0, 1),
                "laut_tenang": bool(fl["tenang"]), "s2": s2, "n_dekat_mangrove": n_mg, "cakupan_laut": fl["cakupan_laut"]})
    print(key, len(feats), "bercak,", n_cek, "prioritas tinggi", flush=True)
json.dump({"ambang": round(P["ambang"], 3), "lintasan": idx}, open(os.path.join(WEB, "kejadian.json"), "w"), indent=1)
