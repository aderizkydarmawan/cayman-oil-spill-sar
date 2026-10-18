"""Tahap 13b: dampak saring.py pada citra lama (Balikpapan & Karawang, 2017-2019) tanpa mengunduh ulang.
Pemakaian: python scripts/14_dampak_saring.py  -> results_kejadian/dampak_saring.csv + ringkasan di layar
"""
import glob, os, sys
import numpy as np, pandas as pd, rasterio
from scipy import ndimage as ndi
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from saring import bersihkan
from situs import _S

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rows = []
for name in ["balikpapan", "karawang"]:
    S = _S[name]
    for od in sorted(glob.glob(os.path.join(HERE, S["results"], "s1_vv_db_*_20m_fixed-32_-17"))):
        d = os.path.basename(od).split("_")[3]
        f = os.path.join(HERE, S["data"], f"s1_vv_db_{d}_20m.tif")
        if not os.path.exists(f):
            continue
        with rasterio.open(f) as s:
            db, sea, px = s.read(1), s.read(2) > 0, s.transform.a
        mk = rasterio.open(os.path.join(od, "mask_unet_lite.tif")).read(1) > 0
        mk2, fl = bersihkan(db, sea, mk, px)
        def n_obj(m):
            lab, n = ndi.label(m, structure=np.ones((3, 3)))
            return int((ndi.sum(m, lab, range(1, n + 1)) * px ** 2 / 1e6 >= 0.1).sum()) if n else 0
        rows.append({"situs": name, "date": d, "kejadian": S["spill"][0] <= d <= S["spill"][1], "acuan": d == S["spill_ref"],
                     "n_sebelum": n_obj(mk), "n_sesudah": n_obj(mk2), **fl})
df = pd.DataFrame(rows); df.to_csv(os.path.join(HERE, "results_kejadian", "dampak_saring.csv"), index=False)
for name, g in df.groupby("situs"):
    c = g[~g.kejadian]
    print(f"{name}: {len(c)} citra tanpa kejadian | median bercak {c.n_sebelum.median():g} -> {c.n_sesudah.median():g} | "
          f"lintasan ditandai laut tenang {int(c.tenang.sum())} ({c.tenang.mean():.0%}) | piksel tepi dibuang di {int((c.px_tepi_dibuang > 0).sum())} citra")
print(df[df.acuan][["situs", "date", "n_sebelum", "n_sesudah", "frac_gelap", "tenang"]].to_string(index=False))
