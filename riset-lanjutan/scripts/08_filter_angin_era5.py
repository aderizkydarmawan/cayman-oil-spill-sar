"""Tahap 8: filter angin ERA5. Aturan dikunci sebelum melihat hasil:
- angin 10 m ERA5 hourly (ECMWF/ERA5/HOURLY), jam 22:00 UTC (lintasan orbit 32 ±21:50 UTC),
  rata-rata di atas laut AOI (JRC occ>50); ERA5 0,25° -> resolusi kasar.
- citra dengan angin < 3 m/s = "tidak bisa dinilai" (ambang utama); 2 dan 4 m/s = uji kepekaan.
Keluaran: results/angin_era5.csv, results/alarm_filter_angin.json, results/alarm_vs_angin.png
"""
import sys
import json, os, ee, numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

ee.Initialize(project=os.environ["EE_PROJECT"])  # isi dengan project GEE Anda
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from situs import BBOX, CRS, ORBIT, ERA5_HOUR, LOOK_AZ, SPILL, YEARS, INNER, DATA, RESULTS, NAME as SITUS, SPILL_REF
AOI = ee.Geometry.Rectangle(BBOX)
SEA = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").gt(50)
MAIN, SENS = 3.0, [2.0, 4.0]

df = pd.read_csv(os.path.join(RESULTS, "alarm_per_citra.csv"))
dates = sorted(df.date.unique())

def wind(d):
    t = ee.Date(d + "T" + ERA5_HOUR + ":00")
    im = ee.ImageCollection("ECMWF/ERA5/HOURLY").filterDate(t, t.advance(1, "hour")).first()
    ws = im.expression("sqrt(u*u+v*v)", {"u": im.select("u_component_of_wind_10m"),
                                         "v": im.select("v_component_of_wind_10m")}).rename("ws")
    ws = ws.resample("bilinear").updateMask(SEA)
    return ee.Feature(None, {"date": d, "ws": ws.reduceRegion(ee.Reducer.mean(), AOI, 1000).get("ws")})

out = os.path.join(RESULTS, "angin_era5.csv")
w = pd.DataFrame([f["properties"] for f in ee.FeatureCollection([wind(d) for d in dates]).getInfo()["features"]])
w.to_csv(out, index=False)
df = df.merge(w, on="date")

REF_KM2 = float(df[(df.date == SPILL_REF) & (df.model == "unet_lite")].km2.iloc[0])  # luas tumpahan acuan (U-Net, objek >=0,1 km²)
summ_ref = {"citra_acuan": SPILL_REF, "km2_acuan_unet": REF_KM2}
summ = {"acuan": summ_ref, "aturan": {"sumber": f"ERA5 hourly {ERA5_HOUR} UTC, mean laut AOI", "ambang_utama_ms": MAIN, "kepekaan_ms": SENS},
        "angin_ms": {"min": w.ws.min(), "median": w.ws.median(), "max": w.ws.max()}, "hasil": {}}
clean = df[~df.spill_period]
for thr in [MAIN] + SENS:
    r = {}
    for m, g in clean.groupby("model"):
        ok = g[g.ws >= thr]
        r[m] = {"citra_dinilai": int(len(ok)), "citra_dibuang": int(len(g) - len(ok)),
                "frac_dibuang": len(g[g.ws < thr]) / len(g),
                "obj_median_sebelum": g.n_obj.median(), "obj_median_sesudah": ok.n_obj.median(),
                "obj_total_sebelum": int(g.n_obj.sum()), "obj_total_sesudah": int(ok.n_obj.sum()),
                "km2_mean_sebelum": g.km2.mean(), "km2_mean_sesudah": ok.km2.mean(),
                "km2_median_sesudah": ok.km2.median(), "frac_tanpa_alarm_sesudah": (ok.n_obj == 0).mean(),
                "n_citra_km2_gt_tumpahan": int((ok.km2 > REF_KM2).sum())}
    summ["hasil"][f"{thr:g}ms"] = {m: {k: round(float(v), 3) for k, v in d.items()} for m, d in r.items()}
sp = df[df.spill_period & (df.model == "unet_lite")][["date", "ws", "n_obj", "km2"]]
summ["periode_tumpahan_unet"] = sp.round(2).to_dict("records")
# korelasi peringkat angin vs luas (U-Net)
u = clean[clean.model == "unet_lite"]
summ["spearman_ws_vs_km2_unet"] = round(float(u[["ws", "km2"]].corr("spearman").iloc[0, 1]), 3)
summ["angin_per_bulan_median"] = {int(k): round(float(v), 2) for k, v in
                                  u.assign(b=pd.to_datetime(u.date).dt.month).groupby("b").ws.median().items()}
json.dump(summ, open(os.path.join(RESULTS, "alarm_filter_angin.json"), "w"), indent=1, default=float)
print(json.dumps(summ, indent=1, default=float))

fig, ax = plt.subplots(1, 2, figsize=(13, 5), constrained_layout=True)
for m, c in [("unet_lite", "#2a6fdb"), ("deeplabv3p", "#e07b22")]:
    g = clean[clean.model == m]
    ax[0].scatter(g.ws, g.km2 + .1, s=18, color=c, label=m, alpha=.8)
    ax[1].scatter(g.ws, g.n_obj, s=18, color=c, label=m, alpha=.8)
s = df[df.spill_period & (df.model == "unet_lite")]
ax[0].scatter(s.ws, s.km2 + .1, s=90, marker="*", color="red", label="periode tumpahan (U-Net)")
for a in ax:
    a.axvline(MAIN, color="k", ls="--", lw=1); a.grid(alpha=.3); a.set_xlabel("angin 10 m ERA5 (m/s)")
ax[0].set_yscale("log"); ax[0].set_ylabel("luas ditandai (km², +0,1)"); ax[1].set_ylabel("jumlah objek ≥0,1 km²")
ax[0].legend(fontsize=8); fig.suptitle(f"Alarm vs angin, {SITUS.capitalize()} 2017–2019 (garis putus = ambang 3 m/s)")
fig.savefig(os.path.join(RESULTS, "alarm_vs_angin.png"), dpi=110)
