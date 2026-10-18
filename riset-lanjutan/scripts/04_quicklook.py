"""Tahap 4: gambar cek visual — citra SAR + mask tiap model untuk setiap folder hasil.
Pemakaian: python 04_quicklook.py results/<folder> [results/<folder> ...]
Keluaran: <folder>/quicklook.png
"""
import os, sys, numpy as np, rasterio, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt

for od in sys.argv[1:]:
    rd = lambda f: rasterio.open(os.path.join(od, f))
    with rd("input_u8.tif") as s:
        u8, tr = s.read(1), s.transform
    ext = [tr.c / 1e3, (tr.c + tr.a * u8.shape[1]) / 1e3, (tr.f + tr.e * u8.shape[0]) / 1e3, tr.f / 1e3]
    fig, ax = plt.subplots(1, 3, figsize=(18, 6.4), constrained_layout=True)
    ax[0].imshow(u8, cmap="gray", extent=ext); ax[0].set_title("Input SAR (8-bit, daratan = hitam)")
    for a, m in zip(ax[1:], ["unet_lite", "deeplabv3p"]):
        with rd(f"mask_{m}.tif") as s: mk = s.read(1)
        a.imshow(u8, cmap="gray", extent=ext)
        a.imshow(np.ma.masked_where(mk == 0, mk), cmap="autumn", alpha=.55, extent=ext)
        a.set_title(f"{m}: {mk.sum() * tr.a ** 2 / 1e6:.1f} km² ditandai minyak")
    with rd("input_u8.tif") as s: crs_name = s.crs.to_string()
    for a in ax: a.set_xlabel(f"{crs_name} Easting (km)")
    ax[0].set_ylabel("Northing (km)")
    fig.suptitle(os.path.basename(od.rstrip("/\\")))
    fig.savefig(os.path.join(od, "quicklook.png"), dpi=90); plt.close(fig)
    print("saved", os.path.join(od, "quicklook.png"))
