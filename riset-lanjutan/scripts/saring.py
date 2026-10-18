"""Penyaring pasca-model (tahap 13b), sama untuk semua lokasi. Ditambahkan setelah uji 12 kejadian (17 Okt 2026).
1. Tepi sapuan: di luar jangkauan citra GEE mengisi 0 (bukan NaN); piksel bercak < 1,5 km dari daerah itu dibuang.
2. Laut tenang: bila bercak menutupi > 15% laut berdata, seluruh lintasan ditandai "didominasi laut tenang"
   (bercak tidak dibuang, hanya diberi tanda). Ambang 15% dipilih setelah melihat hasil: tumpahan Balikpapan 1 Apr 2018 = 8%,
   p95 citra tanpa kejadian = 23%. Jadi ambang ini belum diuji secara independen.
"""
import numpy as np
from scipy import ndimage as ndi

EDGE_M, CALM_FRAC = 1500, 0.15


def bersihkan(db, sea, mk, px):
    nod = ~np.isfinite(db) | (db == 0)
    near = ndi.distance_transform_edt(~nod) * px < EDGE_M if nod.any() else np.zeros_like(mk)
    mk2 = mk & ~near
    valid = sea & ~nod
    frac = float(mk2.sum() / max(valid.sum(), 1))
    return mk2, {"px_tepi_dibuang": int((mk & near).sum()), "frac_gelap": round(frac, 3),
                 "tenang": bool(frac > CALM_FRAC), "cakupan_laut": round(float(valid.sum() / max(sea.sum(), 1)), 2)}
