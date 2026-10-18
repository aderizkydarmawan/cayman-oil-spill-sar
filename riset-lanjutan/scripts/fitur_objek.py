"""Fitur per objek bercak (dipakai tahap 24–25 dan aplikasi). Sama dengan tahap 17, ditambah VH bila ada.
Masukan: db (VV dB), sea (bool), mk (masker U-Net), px (m), vh (VH dB atau None). Mengembalikan daftar dict per objek >= 0,1 km².
"""
import numpy as np
from scipy import ndimage as ndi
from saring import bersihkan

FEAT = ["log_km2", "kompak", "panjang", "obj_db", "std_db", "kontras_db", "tepi_grad", "jarak_pantai_km", "cincin_db", "frac_gelap"]
FEAT_VH = FEAT + ["obj_vh", "kontras_vh"]


def fitur(db, sea, mk, px, vh=None):
    land = ~sea
    dcoast = ndi.distance_transform_edt(~land) * px / 1000 if land.any() else np.full(db.shape, 99.0)
    gy, gx = np.gradient(np.where(np.isfinite(db), db, 0)); g = np.hypot(gx, gy)
    mk2, fl = bersihkan(db, sea, mk, px)
    lab, n = ndi.label(mk2, structure=np.ones((3, 3)))
    rows = []
    for i, sl in enumerate(ndi.find_objects(lab), 1):
        pad = int(2000 / px) + 1
        y0, y1 = max(sl[0].start - pad, 0), min(sl[0].stop + pad, db.shape[0])
        x0, x1 = max(sl[1].start - pad, 0), min(sl[1].stop + pad, db.shape[1])
        o = lab[y0:y1, x0:x1] == i; a = o.sum() * px ** 2 / 1e6
        if a < 0.1:
            continue
        d = db[y0:y1, x0:x1]; s = sea[y0:y1, x0:x1]
        dist = ndi.distance_transform_edt(~o) * px
        ring = (dist > 500) & (dist <= 2000) & s & ~mk2[y0:y1, x0:x1] & np.isfinite(d) & (d != 0)
        edge = o & ~ndi.binary_erosion(o)
        yy, xx = np.nonzero(o); cov = np.cov(np.vstack([yy, xx])) if len(yy) > 2 else np.eye(2)
        ev = np.sort(np.linalg.eigvalsh(cov))
        rd = float(np.nanmedian(d[ring])) if ring.sum() > 20 else np.nan
        r = {"km2": a, "log_km2": np.log10(a), "kompak": 4 * np.pi * o.sum() / max(edge.sum(), 1) ** 2,
             "panjang": np.sqrt(ev[1] / max(ev[0], 1e-6)), "obj_db": float(np.nanmean(d[o])), "std_db": float(np.nanstd(d[o])),
             "kontras_db": rd - float(np.nanmean(d[o])), "tepi_grad": float(g[y0:y1, x0:x1][edge].mean()),
             "jarak_pantai_km": float(dcoast[y0:y1, x0:x1][o].min()), "cincin_db": rd, "frac_gelap": fl["frac_gelap"],
             "py": int(yy.mean()) + y0, "px_": int(xx.mean()) + x0, "label_id": i}
        if vh is not None and vh.size:
            v = vh[y0:y1, x0:x1]; ok = np.isfinite(v) & (v != 0)
            ov = float(np.nanmean(v[o & ok])) if (o & ok).any() else np.nan
            rv = float(np.nanmedian(v[ring & ok])) if (ring & ok).sum() > 20 else np.nan
            r.update(obj_vh=ov, kontras_vh=rv - ov)
        rows.append(r)
    return rows, lab
