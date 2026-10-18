"""Tahap 17: pembeda minyak vs look-alike per objek (setelah U-Net + saring.py).
Label (lemah, dikunci sebelum melihat hasil, 17 Okt 2026):
- 1 = objek pada citra acuan tumpahan (Balikpapan 2018-04-01, Karawang 2019-07-30) — sebagian mungkin alarm palsu (label berisik);
- 0 = objek pada citra di luar periode tumpahan (diasumsikan tanpa minyak);
- citra lain dalam periode tumpahan dibuang.
Uji: latih di satu lokasi, uji di lokasi lain (dua arah). Model: regresi logistik (fitur terstandar) dan gradient boosting kecil.
Metrik operasional: ambang dipilih di data LATIH agar menangkap 80% objek minyak latih; di data UJI dilaporkan
recall objek minyak, recall luas minyak, dan median alarm palsu per lintasan bersih (sebelum vs sesudah pembeda).
Keluaran: results_pembeda/fitur_objek.csv, ringkasan.json
"""
import glob, json, os, sys
import numpy as np, pandas as pd, rasterio
from scipy import ndimage as ndi
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.metrics import roc_auc_score
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from saring import bersihkan
from situs import _S

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "results_pembeda"); os.makedirs(OUT, exist_ok=True)
FEAT = ["log_km2", "kompak", "panjang", "obj_db", "std_db", "kontras_db", "tepi_grad", "jarak_pantai_km", "cincin_db", "frac_gelap"]


def fitur(db, sea, mk, px):
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
        cy, cx = int(yy.mean()) + y0, int(xx.mean()) + x0
        rd = float(np.nanmedian(d[ring])) if ring.sum() > 20 else np.nan
        rows.append({"km2": a, "log_km2": np.log10(a), "kompak": 4 * np.pi * o.sum() / max(edge.sum(), 1) ** 2,
                     "panjang": np.sqrt(ev[1] / max(ev[0], 1e-6)), "obj_db": float(np.nanmean(d[o])), "std_db": float(np.nanstd(d[o])),
                     "kontras_db": rd - float(np.nanmean(d[o])), "tepi_grad": float(g[y0:y1, x0:x1][edge].mean()),
                     "jarak_pantai_km": float(dcoast[y0:y1, x0:x1][o].min()), "cincin_db": rd, "frac_gelap": fl["frac_gelap"],
                     "py": cy, "px_": cx})
    return rows


fn = os.path.join(OUT, "fitur_objek.csv")
if not os.path.exists(fn):
    rows = []
    for name in ["balikpapan", "karawang"]:
        S = _S[name]
        for od in sorted(glob.glob(os.path.join(HERE, S["results"], "s1_vv_db_*_20m_fixed-32_-17"))):
            d = os.path.basename(od).split("_")[3]
            f = os.path.join(HERE, S["data"], f"s1_vv_db_{d}_20m.tif")
            if not os.path.exists(f) or not os.path.exists(os.path.join(od, "mask_unet_lite.tif")):
                continue
            ref, inper = d == S["spill_ref"], S["spill"][0] <= d <= S["spill"][1]
            if inper and not ref:
                continue
            with rasterio.open(f) as s:
                db, sea, px = s.read(1).astype(float), s.read(2) > 0, s.transform.a
            mk = rasterio.open(os.path.join(od, "mask_unet_lite.tif")).read(1) > 0
            for r in fitur(db, sea, mk, px):
                rows.append({"situs": name, "date": d, "label": int(ref), **r})
        print(name, "selesai", flush=True)
    pd.DataFrame(rows).to_csv(fn, index=False)

df = pd.read_csv(fn).dropna(subset=FEAT)
print(df.groupby(["situs", "label"]).size())
models = {"logistik": lambda: make_pipeline(StandardScaler(), LogisticRegression(class_weight="balanced", C=0.3, max_iter=2000)),
          "gboost": lambda: HistGradientBoostingClassifier(max_depth=3, max_iter=150, learning_rate=0.05, class_weight="balanced", random_state=0)}
res = {}
for tr_s, te_s in [("balikpapan", "karawang"), ("karawang", "balikpapan")]:
    tr, te = df[df.situs == tr_s], df[df.situs == te_s]
    for mn, mf in models.items():
        m = mf().fit(tr[FEAT], tr.label)
        p_tr, p_te = m.predict_proba(tr[FEAT])[:, 1], m.predict_proba(te[FEAT])[:, 1]
        thr = float(np.quantile(p_tr[tr.label == 1], 0.2))
        keep = p_te >= thr; pos = te.label == 1; clean = te[te.label == 0]
        per_pass0 = clean.groupby("date").size().reindex(te[te.label == 0].date.unique(), fill_value=0)
        per_pass1 = clean[keep[te.label.values == 0]].groupby("date").size().reindex(per_pass0.index, fill_value=0)
        res[f"{tr_s}->{te_s}/{mn}"] = {
            "n_uji_minyak": int(pos.sum()), "n_uji_lookalike": int((~pos).sum()),
            "auc": round(roc_auc_score(te.label, p_te), 3),
            "recall_objek": round(float(keep[pos.values].mean()), 2),
            "recall_luas": round(float(te.km2[pos & keep].sum() / te.km2[pos].sum()), 2),
            "alarm_per_lintasan_median": [float(per_pass0.median()), float(per_pass1.median())],
            "alarm_per_lintasan_rata": [round(per_pass0.mean(), 2), round(per_pass1.mean(), 2)]}
json.dump(res, open(os.path.join(OUT, "ringkasan.json"), "w"), indent=1)
print(json.dumps(res, indent=1))
# fitur paling berbeda (efek standar), semua data
z = {f: round(float((df[df.label == 1][f].mean() - df[df.label == 0][f].mean()) / df[f].std()), 2) for f in FEAT}
print("beda standar minyak-lookalike:", dict(sorted(z.items(), key=lambda kv: -abs(kv[1]))))
