"""Tahap 16: uji kelayakan prakiraan sebaran (OpenDrift/OpenOil) untuk Teluk Balikpapan.
Lepas partikel dari bercak terdeteksi 1 Apr 2018 21:50 UTC, jalankan sampai lintasan berikutnya yang mencakup teluk
(13 Apr 2018 ~21:50 UTC), lalu bandingkan dengan bercak terdeteksi 13 Apr. Pembanding: (a) diam, (b) hanya angin 3%.
Gaya pendorong: arus permukaan HYCOM (GEE, harian, ±9 km, TANPA pasang surut) + angin ERA5 per jam (GEE).
Keluaran: results/opendrift_2018-04/ (nc gaya, ringkasan json, peta png).
"""
import json, os, sys, datetime as dt
from concurrent.futures import ThreadPoolExecutor
import numpy as np, xarray as xr, rasterio, ee
from rasterio.warp import transform as wt
from scipy import ndimage as ndi
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from saring import bersihkan

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "results", "opendrift_2018-04"); os.makedirs(OUT, exist_ok=True)
T0, T1 = dt.datetime(2018, 4, 1, 21, 50), dt.datetime(2018, 4, 13, 21, 50)
W, S, E, N, G = 116.30, -1.90, 117.70, -0.70, 0.04
ee.Initialize(project="bledos")
lon = np.arange(W + G / 2, E, G); lat = np.arange(N - G / 2, S, -G)


def grid(img, bands):
    a = ee.data.computePixels({"expression": img, "fileFormat": "NUMPY_NDARRAY", "bandIds": bands,
                               "grid": {"dimensions": {"width": len(lon), "height": len(lat)},
                                        "affineTransform": {"scaleX": G, "shearX": 0, "translateX": W, "shearY": 0, "scaleY": -G, "translateY": N},
                                        "crsCode": "EPSG:4326"}})
    return [np.where(np.isfinite(a[b].astype(float)), a[b].astype(float), np.nan) for b in bands]


fn = os.path.join(OUT, "forcing.nc")
if not os.path.exists(fn):
    hy = ee.ImageCollection("HYCOM/sea_water_velocity")
    # HYCOM di GEE berlubang (mis. 8 Apr 2018 kosong): pakai hanya hari yang ada, sela diisi interpolasi
    have = set(hy.filterDate(str(T0.date()), str(T1.date() + dt.timedelta(2))).aggregate_array("system:time_start")
               .map(lambda t: ee.Date(t).format("YYYY-MM-dd")).getInfo())
    days = [d for d in (T0.date() + dt.timedelta(i) for i in range((T1 - T0).days + 2)) if str(d) in have]
    def hday(d):
        im = hy.filterDate(str(d), str(d + dt.timedelta(1))).first().select(["velocity_u_0", "velocity_v_0"])
        return grid(im.resample("bilinear"), ["velocity_u_0", "velocity_v_0"])
    hours = [dt.datetime.combine(T0.date(), dt.time()) + dt.timedelta(hours=h) for h in range(int((T1 - T0).total_seconds() // 3600) + 48)]
    era = ee.ImageCollection("ECMWF/ERA5/HOURLY")
    def ehour(t):
        im = era.filterDate(t.strftime("%Y-%m-%dT%H:00"), (t + dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:00")).first()
        return grid(im.resample("bilinear"), ["u_component_of_wind_10m", "v_component_of_wind_10m"])
    with ThreadPoolExecutor(8) as ex:
        H = list(ex.map(hday, days)); Ew = list(ex.map(ehour, hours))
    # HYCOM harian -> diinterpolasi ke tiap jam; skala GEE 0,001 m/s; sel darat/tak berdata = 0 (OpenDrift memakai landmask sendiri)
    hu = np.stack([h[0] for h in H]) * 1e-3; hv = np.stack([h[1] for h in H]) * 1e-3
    td = np.array([(dt.datetime.combine(d, dt.time()) - hours[0]).total_seconds() for d in days])
    th = np.array([(t - hours[0]).total_seconds() for t in hours])
    iu = np.stack([np.apply_along_axis(lambda s: np.interp(th, td, s), 0, hu)])[0]
    iv = np.stack([np.apply_along_axis(lambda s: np.interp(th, td, s), 0, hv)])[0]
    ds = xr.Dataset({"x_sea_water_velocity": (("time", "lat", "lon"), np.nan_to_num(iu), {"standard_name": "x_sea_water_velocity", "units": "m s-1"}),
                     "y_sea_water_velocity": (("time", "lat", "lon"), np.nan_to_num(iv), {"standard_name": "y_sea_water_velocity", "units": "m s-1"}),
                     "x_wind": (("time", "lat", "lon"), np.stack([e[0] for e in Ew]), {"standard_name": "x_wind", "units": "m s-1"}),
                     "y_wind": (("time", "lat", "lon"), np.stack([e[1] for e in Ew]), {"standard_name": "y_wind", "units": "m s-1"})},
                    coords={"time": hours, "lat": ("lat", lat, {"standard_name": "latitude", "units": "degrees_north"}),
                            "lon": ("lon", lon, {"standard_name": "longitude", "units": "degrees_east"})})
    ds.to_netcdf(fn)
    print("forcing tersimpan; sel HYCOM berdata di kotak:", int(np.isfinite(hu[0]).sum()), "dari", hu[0].size)


def slick(d):
    with rasterio.open(os.path.join(HERE, "data", f"s1_vv_db_{d}_20m.tif")) as s:
        db, sea, tr, crs = s.read(1), s.read(2) > 0, s.transform, s.crs
    mk = rasterio.open(os.path.join(HERE, "results", f"s1_vv_db_{d}_20m_fixed-32_-17", "mask_unet_lite.tif")).read(1) > 0
    mk, _ = bersihkan(db, sea, mk, tr.a)
    lab, n = ndi.label(mk, structure=np.ones((3, 3)))
    keep = np.isin(lab, [i + 1 for i, a in enumerate(ndi.sum(mk, lab, range(1, n + 1)) * tr.a ** 2 / 1e6) if a >= 0.1])
    return keep, tr, crs


m0, tr, crs = slick("2018-04-01"); m1, _, _ = slick("2018-04-13")
rng = np.random.default_rng(0)
yy, xx = np.where(m0); k = rng.choice(len(yy), 3000, replace=False)
slon, slat = wt(crs, "EPSG:4326", list(tr.c + tr.a * (xx[k] + .5)), list(tr.f + tr.e * (yy[k] + .5)))
slon, slat = np.array(slon), np.array(slat)

from opendrift.models.openoil import OpenOil
from opendrift.readers import reader_netCDF_CF_generic
o = OpenOil(loglevel=50, weathering_model="noaa")
o.add_reader(reader_netCDF_CF_generic.Reader(fn))
o.set_config("general:coastline_action", "stranding")
o.seed_elements(lon=slon, lat=slat, time=T0, z=0, oil_type="GENERIC MEDIUM CRUDE", m3_per_hour=1)
o.run(end_time=T1, time_step=900, time_step_output=3600 * 6, outfile=os.path.join(OUT, "openoil.nc"))
lo_f, la_f = o.elements.lon, o.elements.lat
st = o.elements_deactivated

# sasaran: bercak 13 Apr, diperlebar 1 km
dist = ndi.distance_transform_edt(~m1) * tr.a
def hit(lo, la):
    x, y = wt("EPSG:4326", crs, list(lo), list(la))
    c = ((np.array(x) - tr.c) / tr.a).astype(int); r = ((np.array(y) - tr.f) / tr.e).astype(int)
    ok = (r >= 0) & (r < m1.shape[0]) & (c >= 0) & (c < m1.shape[1])
    h = np.zeros(len(lo), bool); h[ok] = dist[r[ok], c[ok]] <= 1000
    return float(h.mean())
# pembanding angin saja: 3% angin ERA5 rata-rata periode di titik pusat
f = xr.open_dataset(fn).sel(time=slice(T0, T1))
uw, vw = float(f.x_wind.mean()), float(f.y_wind.mean()); secs = (T1 - T0).total_seconds()
dlon = 0.03 * uw * secs / (111e3 * np.cos(np.radians(-1.25))); dlat = 0.03 * vw * secs / 111e3
res = {"partikel": 3000, "jam": secs / 3600, "terdampar_frac": round(len(st.lon) / 3000, 3) if hasattr(st, "lon") else None,
       "kena_bercak_13apr_1km": {"openoil": hit(np.r_[lo_f, getattr(st, "lon", [])], np.r_[la_f, getattr(st, "lat", [])]),
                                 "diam": hit(slon, slat), "angin_3persen": hit(slon + dlon, slat + dlat)},
       "luas_bercak_km2": {"1apr": round(m0.sum() * tr.a ** 2 / 1e6, 1), "13apr": round(m1.sum() * tr.a ** 2 / 1e6, 1)},
       "angin_rata_ms": [round(uw, 2), round(vw, 2)],
       "catatan": "HYCOM harian ±9 km tanpa pasang surut; sel darat diisi 0; teluk hampir tidak terwakili"}
json.dump(res, open(os.path.join(OUT, "ringkasan.json"), "w"), indent=1); print(json.dumps(res, indent=1))

fig, ax = plt.subplots(figsize=(8, 7))
for m, c_, lb in [(m0, "orange", "bercak 1 Apr (awal)"), (m1, "red", "bercak 13 Apr (pengamatan)")]:
    yy, xx = np.where(m); s_ = slice(None, None, 25)
    lo_, la_ = wt(crs, "EPSG:4326", list(tr.c + tr.a * xx[s_]), list(tr.f + tr.e * yy[s_])); ax.scatter(lo_, la_, s=1, c=c_, label=lb)
ax.scatter(lo_f, la_f, s=2, c="blue", label="prakiraan OpenOil 13 Apr (aktif)")
if hasattr(st, "lon"): ax.scatter(st.lon, st.lat, s=2, c="k", label="terdampar")
ax.set_xlim(116.6, 117.3); ax.set_ylim(-1.6, -1.0); ax.legend(markerscale=6, fontsize=8)
ax.set_title("Uji kelayakan sebaran Balikpapan: 1 Apr → 13 Apr 2018 (HYCOM+ERA5)")
fig.savefig(os.path.join(OUT, "peta_sebaran.png"), dpi=130)
