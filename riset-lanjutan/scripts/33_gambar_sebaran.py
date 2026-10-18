"""Tahap 33: gambar uji sebaran untuk situs (hanya visualisasi; angka dari tahap 16, 32, 32b)."""
import os, numpy as np, xarray as xr, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from rasterio.warp import transform as wt
from opendrift.readers import reader_global_landmask as glm
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); LM = glm.Reader()

def muat(skrip, ):
    g = {"__file__": os.path.join(HERE, "scripts", skrip)}; src = open(os.path.join(HERE, "scripts", skrip), encoding="utf-8").read().split("from opendrift.models.openoil")[0]
    exec(compile(src, skrip, "exec"), g); return g

def pts(m, g, step):
    yy, xx = np.where(m); yy, xx = yy[::step], xx[::step]; tr, crs = g["tr"], g["crs"]
    lo, la = wt(crs, "EPSG:4326", list(tr.c + tr.a * (xx + .5)), list(tr.f + tr.e * (yy + .5))); return np.array(lo), np.array(la)

def darat(ax, ext):
    x = np.linspace(ext[0], ext[1], 500); y = np.linspace(ext[2], ext[3], 400); X, Y = np.meshgrid(x, y)
    L = LM.get_variables(["land_binary_mask"], x=X.ravel(), y=Y.ravel())["land_binary_mask"].reshape(X.shape)
    ax.imshow(L, extent=ext, origin="lower", cmap=matplotlib.colors.ListedColormap(["#dbeef7", "#cfc8b8"]), aspect="auto", zorder=0)

def panel(ax, g, nc, ext, judul, step=20):
    darat(ax, ext)
    d = xr.open_dataset(nc); lo, la = d.lon.values, d.lat.values
    for p in np.linspace(0, lo.shape[0] - 1, 120).astype(int):
        ax.plot(lo[p], la[p], c="#2563eb", lw=.5, alpha=.45, zorder=2)
    a0 = pts(g["m0"], g, step); a1 = pts(g["m1"], g, step)
    ax.scatter(*a0, s=2, c="#f59e0b", zorder=3)
    ax.scatter(*a1, s=2, c="#dc2626", zorder=3)
    fin = np.array([[r[np.isfinite(r)][-1] for r in lo], [r[np.isfinite(r)][-1] for r in la]])
    ax.scatter(*fin, s=4, c="k", zorder=4)
    ax.set_xlim(ext[:2]); ax.set_ylim(ext[2:]); ax.set_title(judul, fontsize=10.5, loc="left")
    ax.tick_params(labelsize=7)

fig, axs = plt.subplots(1, 2, figsize=(12, 5.6), constrained_layout=True)
k = muat("32_opendrift_karawang.py")
panel(axs[0], k, os.path.join(HERE, "results_karawang/opendrift_2019-07-30/openoil.nc"), [107.15, 107.7, -6.25, -5.85],
      "A. Karawang (laut terbuka) — 30 Jul → 2 Agu 2019, 3,5 hari\nOpenOil 5% luas bercak laut terjangkau · diam 18%")
b = muat("16_opendrift_balikpapan.py")
panel(axs[1], b, os.path.join(HERE, "results/opendrift_2018-04/openoil.nc"), [116.55, 117.3, -1.92, -1.05],
      "B. Teluk Balikpapan — 1 → 13 Apr 2018, 12 hari\nOpenOil 4% partikel kena · diam 47% · 94% partikel keluar batas data arus (selatan)")
from matplotlib.lines import Line2D
h = [Line2D([], [], marker="o", ls="", c=c, label=l) for c, l in [("#f59e0b", "bercak awal (titik lepas)"), ("#dc2626", "bercak pengamatan berikutnya"), ("k", "posisi akhir partikel")]]
h.append(Line2D([], [], c="#2563eb", label="lintasan partikel (120 contoh)"))
fig.legend(handles=h, loc="lower center", ncol=4, fontsize=8.5, bbox_to_anchor=(.5, -.06), frameon=False)
out = os.path.join(os.path.dirname(HERE), "aplikasi-web", "data", "sebaran_karawang_2019.png")
fig.savefig(out, dpi=120, bbox_inches="tight", facecolor="white"); print(out)
