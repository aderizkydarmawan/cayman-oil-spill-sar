"""Tahap 7: rekap alarm per citra dari hasil skala tetap (fixed-32_-17, 20 m).
Objek = komponen terhubung (8-tetangga) dengan luas >= MIN_KM2.
Zona: 'teluk_dalam' (utara garis UTM N 9862 km dan barat E 482 km = Teluk Balikpapan bagian dalam + sungai),
      'pantai' (< 1 km dari darat, di luar teluk dalam), 'laut_lepas' (sisanya).
Objek dihitung pada zona tempat sentroidnya berada.
Keluaran: results/alarm_per_citra.csv, results/alarm_ringkasan.json, results/alarm_timeseries.png
"""
import sys
import glob, json, os, numpy as np, rasterio, pandas as pd
from scipy import ndimage as ndi
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from situs import BBOX, CRS, ORBIT, ERA5_HOUR, LOOK_AZ, SPILL, YEARS, INNER, DATA, RESULTS, NAME as SITUS, SPILL_REF
MIN_KM2 = 0.1
rows = []
zone = None
for od in sorted(glob.glob(os.path.join(RESULTS, "s1_vv_db_*_20m_fixed-32_-17"))):
    date = os.path.basename(od).split("_")[3]
    with rasterio.open(os.path.join(DATA, f"s1_vv_db_{date}_20m.tif")) as s:
        sea, tr = s.read(2) > 0, s.transform
    px_km2 = tr.a ** 2 / 1e6
    if zone is None:
        H, W = sea.shape
        E = (tr.c + tr.a * (np.arange(W) + .5)) / 1e3; N = (tr.f + tr.e * (np.arange(H) + .5)) / 1e3
        EE, NN = np.meshgrid(E, N)
        inner = INNER(EE, NN)
        dist_land_km = ndi.distance_transform_edt(sea) * tr.a / 1e3
        zone = np.where(inner, 0, np.where(dist_land_km < 1, 1, 2))  # 0 teluk_dalam,1 pantai,2 laut_lepas
        zone_km2 = {z: float(((zone == i) & sea).sum() * px_km2) for i, z in enumerate(["teluk_dalam", "pantai", "laut_lepas"])}
    for m in ["unet_lite", "deeplabv3p"]:
        with rasterio.open(os.path.join(od, f"mask_{m}.tif")) as s:
            mk = s.read(1) > 0
        lab, n = ndi.label(mk, structure=np.ones((3, 3)))
        r = {"date": date, "model": m, "spill_period": SPILL[0] <= date <= SPILL[1]}
        if n:
            sizes = ndi.sum(mk, lab, range(1, n + 1)) * px_km2
            cy, cx = np.array(ndi.center_of_mass(mk, lab, range(1, n + 1))).T.round().astype(int)
            zs = zone[cy, cx]; keep = sizes >= MIN_KM2
        else:
            sizes = zs = keep = np.array([])
        r["n_obj"] = int(keep.sum()); r["km2"] = float(sizes[keep].sum()) if n else 0.0
        for i, z in enumerate(["teluk_dalam", "pantai", "laut_lepas"]):
            sel = keep & (zs == i) if n else keep
            r[f"n_{z}"] = int(sel.sum()); r[f"km2_{z}"] = float(sizes[sel].sum()) if n else 0.0
        rows.append(r)

df = pd.DataFrame(rows); df.to_csv(os.path.join(RESULTS, "alarm_per_citra.csv"), index=False)
clean = df[~df.spill_period]
summ = {"aturan": {"stretch": "fixed -32..-17 dB", "pixel_m": 20, "min_obj_km2": MIN_KM2,
                   "periode_tumpahan_dikeluarkan": SPILL}, "luas_zona_km2": zone_km2,
        "n_citra_tanpa_insiden": int(clean.date.nunique()), "model": {}}
for m, g in clean.groupby("model"):
    s = {"obj_per_citra_mean": g.n_obj.mean(), "obj_per_citra_median": g.n_obj.median(),
         "obj_per_citra_p90": g.n_obj.quantile(.9), "frac_citra_tanpa_alarm": (g.n_obj == 0).mean(),
         "km2_per_citra_mean": g.km2.mean(), "km2_per_citra_median": g.km2.median()}
    for z in ["teluk_dalam", "pantai", "laut_lepas"]:
        s[f"obj_per_citra_{z}"] = g[f"n_{z}"].mean(); s[f"km2_per_citra_{z}"] = g[f"km2_{z}"].mean()
        s[f"frac_citra_tanpa_alarm_{z}"] = (g[f"n_{z}"] == 0).mean()
    summ["model"][m] = {k: round(float(v), 3) for k, v in s.items()}
json.dump(summ, open(os.path.join(RESULTS, "alarm_ringkasan.json"), "w"), indent=1)
print(json.dumps(summ, indent=1))

fig, ax = plt.subplots(2, 1, figsize=(13, 7), sharex=True, constrained_layout=True)
for m, c in [("unet_lite", "#2a6fdb"), ("deeplabv3p", "#e07b22")]:
    g = df[df.model == m].assign(d=lambda x: pd.to_datetime(x.date))
    ax[0].plot(g.d, g.n_obj, "o-", ms=3, lw=1, color=c, label=m)
    ax[1].plot(g.d, g.km2, "o-", ms=3, lw=1, color=c, label=m)
for a in ax:
    a.axvspan(pd.Timestamp(SPILL[0]), pd.Timestamp(SPILL[1]), color="red", alpha=.12, label="periode tumpahan")
    a.grid(alpha=.3)
ax[0].set_ylabel(f"jumlah objek ≥{MIN_KM2} km²"); ax[1].set_ylabel("luas ditandai (km²)"); ax[1].set_yscale("symlog", linthresh=1)
ax[0].legend(); ax[0].set_title(f"Deteksi per citra Sentinel-1 (orbit {ORBIT}), {SITUS.capitalize()} 2017–2019, skala dB tetap")
fig.savefig(os.path.join(RESULTS, "alarm_timeseries.png"), dpi=110)
