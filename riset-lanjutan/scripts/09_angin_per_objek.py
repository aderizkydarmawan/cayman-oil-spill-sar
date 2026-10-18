"""Tahap 9: angin per objek alarm. Aturan dikunci sebelum melihat hasil:
- objek = komponen terhubung (8-tetangga) mask U-Net Lite / DeepLabV3+ >= 0,1 km² (sama dgn tahap 7)
- angin SAR lokal: cincin laut 1-3 km di sekeliling objek (tanpa darat & tanpa objek alarm lain),
  median sigma0 VV linear + median sudut datang (GEE band 'angle'), dibalik dengan CMOD5.N (scripts/cmod5n.py)
- arah angin dari ERA5 22:00 UTC; arah pandang radar orbit 32 menurun ~282° (heading ~192° + 90°, right-looking);
  phi = arah_asal_angin - arah_pandang (0 = upwind)
- pembanding: ERA5 (bilinear) di sentroid objek
- objek dengan angin SAR lokal < 3 m/s = kepercayaan rendah; 2 dan 4 m/s = kepekaan
Keluaran: results/objek_angin.csv, results/objek_angin_ringkasan.json, results/objek_angin.png
"""
import glob, json, os, sys, numpy as np, pandas as pd, rasterio, ee
from scipy import ndimage as ndi
from rasterio.warp import transform as warp_xy
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import cmod5n

ee.Initialize(project="bledos")
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from situs import BBOX, CRS, ORBIT, ERA5_HOUR, LOOK_AZ, SPILL, YEARS, INNER, DATA, RESULTS, NAME as SITUS, SPILL_REF
W_, S_, E_, N_ = BBOX
AOI = ee.Geometry.Rectangle([W_, S_, E_, N_])
MIN_KM2, R_IN, R_OUT = 0.1, 1000, 3000
MAIN, SENS = 3.0, [2.0, 4.0]
GD = 0.01  # grid lon/lat untuk ERA5 & sudut datang


def grid_ll(img, bands):
    nx, ny = int(round((E_ - W_) / GD)), int(round((N_ - S_) / GD))
    a = ee.data.computePixels({"expression": img, "fileFormat": "NUMPY_NDARRAY", "bandIds": bands,
                               "grid": {"dimensions": {"width": nx, "height": ny},
                                        "affineTransform": {"scaleX": GD, "shearX": 0, "translateX": W_,
                                                            "shearY": 0, "scaleY": -GD, "translateY": N_},
                                        "crsCode": "EPSG:4326"}})
    return {b: a[b].astype(float) for b in bands}


def sample(g, lon, lat):
    j = np.clip(((lon - W_) / GD).astype(int), 0, g.shape[1] - 1)
    i = np.clip(((N_ - lat) / GD).astype(int), 0, g.shape[0] - 1)
    return g[i, j]


rows = []
CSV = os.path.join(RESULTS, "objek_angin.csv")
REUSE = "--reuse" in sys.argv and os.path.exists(CSV)   # hanya hitung ulang ringkasan dari CSV per objek
for od in [] if REUSE else sorted(glob.glob(os.path.join(RESULTS, "s1_vv_db_*_20m_fixed-32_-17"))):
    date = os.path.basename(od).split("_")[3]
    with rasterio.open(os.path.join(DATA, f"s1_vv_db_{date}_20m.tif")) as s:
        db, sea, tr, crs = s.read(1), s.read(2) > 0, s.transform, s.crs
    px = tr.a; px_km2 = px ** 2 / 1e6
    d0 = ee.Date(date); t = ee.Date(date + "T" + ERA5_HOUR + ":00")
    s1 = (ee.ImageCollection("COPERNICUS/S1_GRD").filterBounds(AOI).filterDate(d0, d0.advance(1, "day"))
          .filter(ee.Filter.eq("instrumentMode", "IW")).select("angle").mosaic())
    era = ee.ImageCollection("ECMWF/ERA5/HOURLY").filterDate(t, t.advance(1, "hour")).first()
    uv = era.select(["u_component_of_wind_10m", "v_component_of_wind_10m"], ["u", "v"]).resample("bilinear")
    g = grid_ll(uv.addBands(s1.rename("angle")), ["u", "v", "angle"])
    lin = np.where(np.isfinite(db), 10 ** (db / 10), np.nan)
    masks = {}
    for m in ["unet_lite", "deeplabv3p"]:
        with rasterio.open(os.path.join(od, f"mask_{m}.tif")) as s:
            masks[m] = s.read(1) > 0
    for m, mk in masks.items():
        lab, n = ndi.label(mk, structure=np.ones((3, 3)))
        if not n:
            continue
        objs = ndi.find_objects(lab)
        pad = int(np.ceil(R_OUT / px)) + 1
        for k, sl in enumerate(objs, start=1):
            area = (lab[sl] == k).sum() * px_km2
            if area < MIN_KM2:
                continue
            y0, y1 = max(sl[0].start - pad, 0), min(sl[0].stop + pad, mk.shape[0])
            x0, x1 = max(sl[1].start - pad, 0), min(sl[1].stop + pad, mk.shape[1])
            ob = lab[y0:y1, x0:x1] == k
            dist = ndi.distance_transform_edt(~ob) * px
            ring = (dist > R_IN) & (dist <= R_OUT) & sea[y0:y1, x0:x1] & ~mk[y0:y1, x0:x1]
            cy, cx = np.argwhere(ob).mean(0) + [y0, x0]
            ex, ny_ = tr.c + px * (cx + .5), tr.f - px * (cy + .5)
            lon, lat = (v[0] for v in warp_xy(crs, "EPSG:4326", [ex], [ny_]))
            u, v, inc = (float(sample(g[b], np.array([lon]), np.array([lat]))[0]) for b in ["u", "v", "angle"])
            era_ws = float(np.hypot(u, v)); wdir_from = (np.degrees(np.arctan2(-u, -v)) + 360) % 360
            phi = (wdir_from - LOOK_AZ) % 360
            if ring.sum() >= 50 and np.isfinite(inc):
                s0 = float(np.nanmedian(lin[y0:y1, x0:x1][ring]))
                sar_ws = float(cmod5n.invert(s0, inc, phi)[0])
                s0_db_obj = float(np.nanmedian(db[y0:y1, x0:x1][ob]))
                ring_db = 10 * np.log10(s0)
            else:
                sar_ws = ring_db = s0_db_obj = np.nan
            rows.append({"date": date, "model": m, "obj": k, "km2": area, "lon": lon, "lat": lat,
                         "spill_period": SPILL[0] <= date <= SPILL[1], "inc": inc, "era5_ws": era_ws,
                         "era5_dir_from": wdir_from, "phi": phi, "ring_px": int(ring.sum()),
                         "ring_db": ring_db, "obj_db": s0_db_obj, "contrast_db": ring_db - s0_db_obj,
                         "sar_ws_ring": sar_ws})
    print(date, len(rows), flush=True)

if REUSE:
    df = pd.read_csv(CSV)
else:
    df = pd.DataFrame(rows); df.to_csv(CSV, index=False)
df["sar_ws_ring"] = df.sar_ws_ring.round(2)          # kisi CMOD 0,05 m/s; konsisten antar jalur

summ = {"aturan": {"cincin_m": [R_IN, R_OUT], "look_az": LOOK_AZ, "gmf": "CMOD5.N (xsarsea 2.1.2, port tervalidasi 0 dB)",
                   "ambang_utama_ms": MAIN, "kepekaan_ms": SENS, "min_obj_km2": MIN_KM2}, "hasil": {}}
for m, g in df.groupby("model"):
    clean, spill = g[~g.spill_period], g[g.date == SPILL_REF].sort_values("km2", ascending=False)
    n_sc = clean.date.nunique()
    r = {"n_obj_tanpa_insiden": int(len(clean)), "n_citra": int(n_sc),
         "sar_ws_median_tanpa_insiden": float(clean.sar_ws_ring.median()),
         "spearman_sar_vs_era5": float(g[["sar_ws_ring", "era5_ws"]].corr("spearman").iloc[0, 1]),
         "objek_1apr_top5": spill.head(5)[["km2", "sar_ws_ring", "era5_ws", "contrast_db"]].round(2).to_dict("records")}
    # semua 82 citra tanpa insiden (termasuk yang tanpa objek sama sekali), dari tahap 7
    ap = pd.read_csv(os.path.join(RESULTS, "alarm_per_citra.csv"))
    all_scenes = sorted(ap[~ap.spill_period].date.unique())
    r["n_citra"] = len(all_scenes)
    for thr in [MAIN] + SENS:
        keep = clean[clean.sar_ws_ring >= thr]
        per = keep.groupby("date").size().reindex(all_scenes, fill_value=0)
        sp_keep = spill[spill.sar_ws_ring >= thr]
        r[f"{thr:g}ms"] = {"obj_tersisa": int(len(keep)), "frac_obj_tersisa": len(keep) / max(len(clean), 1),
                           "obj_per_citra_median": float(per.median()), "obj_per_citra_mean": float(per.mean()),
                           "frac_citra_tanpa_alarm": float((per == 0).mean()), "km2_per_citra_mean": float(keep.km2.sum() / len(all_scenes)),
                           "objek_1apr_lolos": int(len(sp_keep)), "km2_1apr_lolos": float(sp_keep.km2.sum()),
                           "km2_1apr_total": float(spill.km2.sum()),
                           "n_citra_km2_lolos_gt_1apr": int((keep.groupby("date").km2.sum() > sp_keep.km2.sum()).sum())}
    summ["hasil"][m] = r
json.dump(summ, open(os.path.join(RESULTS, "objek_angin_ringkasan.json"), "w"), indent=1, default=float)
print(json.dumps(summ, indent=1, default=float))

u = df[df.model == "unet_lite"]
fig, ax = plt.subplots(1, 2, figsize=(13, 5), constrained_layout=True)
c = u[~u.spill_period]; s = u[u.date == SPILL_REF]
ax[0].scatter(c.era5_ws, c.sar_ws_ring, s=8, alpha=.5, label="objek, citra tanpa insiden")
ax[0].scatter(s.era5_ws, s.sar_ws_ring, s=np.clip(s.km2 * 4, 20, 300), color="red", marker="*", label=f"objek {SPILL_REF}")
ax[0].plot([0, 8], [0, 8], "k:", lw=1); ax[0].set_xlabel("ERA5 di sentroid (m/s)"); ax[0].set_ylabel("angin SAR cincin 1–3 km (m/s)")
ax[1].scatter(c.sar_ws_ring, c.km2, s=8, alpha=.5); ax[1].scatter(s.sar_ws_ring, s.km2, s=60, color="red", marker="*")
ax[1].set_yscale("log"); ax[1].set_xlabel("angin SAR cincin 1–3 km (m/s)"); ax[1].set_ylabel("luas objek (km²)")
for a in ax: a.axvline(MAIN, color="k", ls="--", lw=1) if a is ax[1] else a.axhline(MAIN, color="k", ls="--", lw=1); a.grid(alpha=.3)
ax[0].legend(fontsize=8); fig.suptitle(f"U-Net Lite: angin per objek alarm, {SITUS.capitalize()} 2017–2019")
fig.savefig(os.path.join(RESULTS, "objek_angin.png"), dpi=110)
