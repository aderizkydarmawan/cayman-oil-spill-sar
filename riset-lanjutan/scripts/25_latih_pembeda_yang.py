"""Tahap 25: pembeda minyak vs look-alike per objek, dilatih label ahli Yang & Singha (objek keluaran alur aplikasi, tahap 24).
Aturan dikunci sebelum hasil (18 Okt 2026):
- validasi silang 5 lipat DIKELOMPOKKAN per citra Sentinel-1 (sid), seed 0;
- model: regresi logistik (terstandar) dan HistGradientBoosting kecil; set fitur: VV saja (FEAT) dan VV+VH (FEAT_VH);
- ambang operasional = recall 90% objek minyak pada prediksi silang (jangan sampai tumpahan terlewat);
- uji luar: model VV saja dilatih ulang pada semua data Yang, diterapkan ke objek Karawang/Balikpapan (fitur_objek.csv tahap 17,
  label lemah) dengan ambang yang sama, tanpa penyetelan ulang. Dilaporkan: recall objek & luas minyak, alarm per lintasan bersih.
Keluaran: results_pembeda/yang_cv.json, yang_uji_lokal.json, pembeda_vv.joblib (untuk aplikasi)
"""
import json, os, sys
import numpy as np, pandas as pd, joblib
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.model_selection import GroupKFold
from sklearn.metrics import roc_auc_score
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fitur_objek import FEAT, FEAT_VH

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); OUT = os.path.join(HERE, "results_pembeda")
df = pd.read_csv(os.path.join(OUT, "yang_objek.csv")).sample(frac=1, random_state=0).reset_index(drop=True)
print(df.groupby(["set", "label"]).size().to_dict(), "| citra:", df.sid.nunique())
MOD = {"logistik": lambda: make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(class_weight="balanced", C=0.3, max_iter=3000)),
       "gboost": lambda: HistGradientBoostingClassifier(max_depth=4, max_iter=300, learning_rate=0.05, class_weight="balanced", random_state=0)}


def cv(feat, mf):
    p = np.zeros(len(df))
    for tr, te in GroupKFold(5).split(df, df.label, df.sid):
        p[te] = mf().fit(df.loc[tr, feat], df.label[tr]).predict_proba(df.loc[te, feat])[:, 1]
    thr = float(np.quantile(p[df.label == 1], 0.10))
    keep = p >= thr
    return p, thr, {"auc": round(roc_auc_score(df.label, p), 3), "ambang_recall90": round(thr, 3),
                    "lookalike_dibuang": round(float(1 - keep[df.label == 0].mean()), 3),
                    "minyak_tertangkap": round(float(keep[df.label == 1].mean()), 3)}


res = {}
for fs_name, feat in [("VV", FEAT), ("VV+VH", FEAT_VH)]:
    for mn, mf in MOD.items():
        _, thr, r = cv(feat, mf); res[f"{fs_name}/{mn}"] = r; print(fs_name, mn, r, flush=True)
json.dump(res, open(os.path.join(OUT, "yang_cv.json"), "w"), indent=1)

# uji luar: VV saja (citra arsip lokal kita hanya VV), model terbaik menurut AUC silang
best = max(MOD, key=lambda m: res[f"VV/{m}"]["auc"])
_, thr, _ = cv(FEAT, MOD[best])
m = MOD[best]().fit(df[FEAT], df.label)
joblib.dump({"model": m, "fitur": FEAT, "ambang": thr, "sumber": "Yang & Singha 2025 (CC-BY-4.0), tahap 25"}, os.path.join(OUT, "pembeda_vv.joblib"))
lok = pd.read_csv(os.path.join(OUT, "fitur_objek.csv"))
lok["p"] = m.predict_proba(lok[FEAT])[:, 1]; lok["lolos"] = lok.p >= thr
ul = {"model": best, "ambang": round(thr, 3)}
for s, g in lok.groupby("situs"):
    pos, cl = g.label == 1, g[g.label == 0]
    a0 = cl.groupby("date").size(); a1 = cl[cl.lolos].groupby("date").size().reindex(a0.index, fill_value=0)
    ul[s] = {"auc": round(roc_auc_score(g.label, g.p), 3), "recall_objek": round(float(g.lolos[pos].mean()), 2),
             "recall_luas": round(float(g.km2[pos & g.lolos].sum() / g.km2[pos].sum()), 2),
             "alarm_per_lintasan_median": [float(a0.median()), float(a1.median())],
             "alarm_per_lintasan_rata": [round(a0.mean(), 2), round(a1.mean(), 2)]}
lok.to_csv(os.path.join(OUT, "yang_uji_lokal_objek.csv"), index=False)
json.dump(ul, open(os.path.join(OUT, "yang_uji_lokal.json"), "w"), indent=1); print(json.dumps(ul, indent=1))
