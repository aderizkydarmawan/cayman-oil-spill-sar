"""Tahap 12: satu gambar bersih untuk lampiran WA (kejadian publik saja).
Pakai: SITUS=balikpapan python scripts/12_gambar_wa.py 2018-04-01
"""
import os, sys
import numpy as np, rasterio
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from rasterio.warp import transform as wt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from situs import DATA, RESULTS, NAME as SITUS

DATE = sys.argv[1]
run = os.path.join(RESULTS, f"s1_vv_db_{DATE}_20m_fixed-32_-17")
with rasterio.open(os.path.join(run, "input_u8.tif")) as s:
    u8, tr, crs = s.read(1), s.transform, s.crs
with rasterio.open(os.path.join(run, "mask_unet_lite.tif")) as s:
    mk = s.read(1) > 0
with rasterio.open(os.path.join(DATA, f"s1_vv_db_{DATE}_20m.tif")) as s:
    sea = s.read(2) > 0
mk &= sea

# potong ke teluk (sekitar bercak utama), margin 6 km
from scipy import ndimage as ndi
lab, n = ndi.label(mk, structure=np.ones((3, 3)))
big = lab == (np.argmax(ndi.sum(mk, lab, range(1, n + 1))) + 1)
cy, cx = [v.mean() for v in np.where(big)]
near = mk & (np.hypot(*np.meshgrid(np.arange(mk.shape[1]) - cx, np.arange(mk.shape[0]) - cy)[::-1]) * tr.a < 20000)
ys, xs = np.where(big if SITUS == "balikpapan" else near); pad = int(6000 / tr.a)
y0, y1 = max(ys.min() - pad, 0), min(ys.max() + pad, u8.shape[0]); x0, x1 = max(xs.min() - pad, 0), min(xs.max() + pad, u8.shape[1])
sub, m = u8[y0:y1, x0:x1], mk[y0:y1, x0:x1]
ext = [(tr.c + tr.a * x0) / 1e3, (tr.c + tr.a * x1) / 1e3, (tr.f + tr.e * y1) / 1e3, (tr.f + tr.e * y0) / 1e3]
km2 = m.sum() * tr.a ** 2 / 1e6

fig, axs = plt.subplots(1, 2, figsize=(12, 6.6), gridspec_kw=dict(wspace=0.04, left=0.04, right=0.99, top=0.84, bottom=0.12))
for i, ax in enumerate(axs):
    ax.set_facecolor("#d9d2c3")
    ax.imshow(np.where(sea[y0:y1, x0:x1], sub, np.nan), cmap="gray", extent=ext, vmin=0, vmax=255)
    if i == 1:
        ax.imshow(np.ma.masked_where(~m, np.ones_like(sub)), cmap="autumn", alpha=.8, extent=ext, interpolation="nearest")
    ax.set_xlim(ext[0], ext[1]); ax.set_ylim(ext[2], ext[3]); ax.set_xticks([]); ax.set_yticks([])
    sx, sy = ext[1] - (ext[1] - ext[0]) * .04 - 10, ext[2] + (ext[3] - ext[2]) * .05
    ax.plot([sx, sx + 10], [sy, sy], color="k", lw=3)
    ax.text(sx + 5, sy + (ext[3] - ext[2]) * .02, "10 km", ha="center", fontsize=9, bbox=dict(fc="white", alpha=.75, ec="none", pad=1))
axs[0].set_title("Citra radar satelit (gelap = permukaan laut licin)", fontsize=11)
axs[1].set_title("Bercak yang ditandai otomatis (merah)", fontsize=11)
lo, la = wt(crs, "EPSG:4326", [(ext[0] + ext[1]) / 2 * 1e3], [(ext[2] + ext[3]) / 2 * 1e3])
JUDUL = {"balikpapan": ("Uji pada kejadian publik: tumpahan minyak Teluk Balikpapan, 31 Maret 2018",
                     "Citra Sentinel-1, 2 April 2018 pukul 05:50 WITA (sekitar sehari setelah kejadian)"),
         "karawang": ("Uji pada kejadian publik: tumpahan minyak sumur YYA-1, Karawang, Juli 2019",
                      "Citra Sentinel-1, 30 Juli 2019 pukul 18:14 WIB (18 hari setelah kebocoran mulai)")}[SITUS]
fig.suptitle(JUDUL[0], fontsize=14, weight="bold", y=0.97)
fig.text(0.5, 0.905, JUDUL[1], ha="center", fontsize=10.5, color="#333")
fig.text(0.5, 0.045, "Uji riset ADE pada kejadian publik — bukan produk resmi. Bercak gelap belum tentu minyak; "
         "tidak ada validasi lapangan.\nMengandung data Copernicus Sentinel-1 (ESA), diolah di Google Earth Engine.",
         ha="center", fontsize=9, color="#444", linespacing=1.4)
out = os.path.join("laporan", f"lampiran_wa_{SITUS}_{DATE[:4]}.jpg"); os.makedirs("laporan", exist_ok=True)
fig.savefig(out, dpi=150, pil_kwargs={"quality": 88}); print("->", out, f"{km2:.1f} km2")
