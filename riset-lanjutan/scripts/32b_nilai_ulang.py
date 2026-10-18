"""Tahap 32b: penilaian ulang uji sebaran Karawang (32) setelah ditemukan artefak.
Temuan: sebagian bercak terdeteksi 2 Agu jatuh di DARAT menurut masker pantai GSHHG (kemungkinan tambak di pesisir yang
lolos masker laut citra), dan 98,7% partikel OpenOil terdampar di pantai tepat di sebelahnya -> skor 'kena' 0,99 semu.
Koreksi (ditetapkan setelah melihat artefak, dicatat jujur): sasaran = piksel bercak 2 Agu yang LAUT menurut GSHHG;
dinilai dua cara: (a) fraksi partikel kena (<=1 km), (b) fraksi luas bercak-laut 2 Agu yang didekati partikel (<=1 km).
Partikel/titik pembanding yang di darat dihitung sebagai terdampar (tetap dinilai di posisinya).
"""
import os, json, numpy as np, xarray as xr, rasterio, scipy.ndimage as ndi
from rasterio.warp import transform as wt
from opendrift.readers import reader_global_landmask as glm
import importlib.util, sys
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); OUT = os.path.join(HERE, "results_karawang", "opendrift_2019-07-30")
sys.argv = ["x"]
src = open(os.path.join(HERE, "scripts", "32_opendrift_karawang.py"), encoding="utf-8").read()
src = src.split("from opendrift.models.openoil")[0]           # pakai ulang slick(), m0, m1, v1, titik lepas (seed 0)
exec(compile(src, "32", "exec"))
LM = glm.Reader()
yy, xx = np.where(m1)
lo, la = wt(crs, "EPSG:4326", list(tr.c + tr.a * (xx + .5)), list(tr.f + tr.e * (yy + .5)))
darat = LM.get_variables(["land_binary_mask"], x=np.array(lo), y=np.array(la))["land_binary_mask"].astype(bool)
m1s = np.zeros_like(m1); m1s[yy[~darat], xx[~darat]] = True
dist = ndi.distance_transform_edt(~m1s) * tr.a

def rc(lo, la):
    x, y = wt("EPSG:4326", crs, list(lo), list(la))
    c = ((np.array(x) - tr.c) / tr.a).astype(int); r = ((np.array(y) - tr.f) / tr.e).astype(int)
    ok = (r >= 0) & (r < m1.shape[0]) & (c >= 0) & (c < m1.shape[1]); ok[ok] = v1[r[ok], c[ok]] | ~v1[r[ok], c[ok]]
    return r, c, ok

def nilai(lo, la):
    r, c, ok = rc(lo, la)
    kena = dist[r[ok], c[ok]] <= 1000
    near = np.zeros_like(m1s); near[r[ok], c[ok]] = True
    near = ndi.distance_transform_edt(~near) * tr.a <= 1000
    return {"kena_partikel": round(float(kena.mean()), 3), "luas_bercak_didekati": round(float((near & m1s).sum() / m1s.sum()), 3)}

d = xr.open_dataset(os.path.join(OUT, "openoil.nc"))
lo_f = d.lon.values[:, -1]; la_f = d.lat.values[:, -1]
# posisi terakhir yang sah (partikel terdampar membeku di pantai)
for p in np.where(~np.isfinite(lo_f))[0]:
    k = np.where(np.isfinite(d.lon.values[p]))[0][-1]; lo_f[p], la_f[p] = d.lon.values[p, k], d.lat.values[p, k]
f = xr.open_dataset(os.path.join(OUT, "forcing.nc")).sel(time=slice(T0, T1))
uw, vw = float(f.x_wind.mean()), float(f.y_wind.mean()); secs = (T1 - T0).total_seconds()
dlon = 0.03 * uw * secs / (111e3 * np.cos(np.radians(-5.9))); dlat = 0.03 * vw * secs / 111e3
res = {"bercak_2agu_km2": {"semua": round(m1.sum() * tr.a ** 2 / 1e6, 1), "di_laut": round(m1s.sum() * tr.a ** 2 / 1e6, 1)},
       "openoil": nilai(lo_f, la_f), "diam": nilai(slon, slat), "angin_3persen": nilai(slon + dlon, slat + dlat),
       "geser_angin_km": round(float(np.hypot(dlon * 111 * np.cos(np.radians(-5.9)), dlat * 111)), 1)}
json.dump(res, open(os.path.join(OUT, "ringkasan_nilai_ulang.json"), "w"), indent=1); print(json.dumps(res, indent=1))
