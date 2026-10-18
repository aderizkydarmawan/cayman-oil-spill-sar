"""Tahap 28: pemilah v2 = tanpa fitur tingkat citra (frac_gelap) + batasan monoton (log_km2 naik -> skor tidak turun).
Diputuskan lewat llm-council (18 Okt 2026) setelah tahap 27 menunjukkan frac_gelap jalan pintas (pemilah v1 membuang 71% luas minyak Trujillo).
Aturan dikunci SEBELUM uji (18 Okt 2026):
- data latih: hanya Yang & Singha (yang_objek.csv); CV GroupKFold(5) per sid; model & hiperparameter sama dengan tahap 25;
- fitur: FEAT tanpa frac_gelap (9); monotonic_cst +1 untuk log_km2, 0 lainnya;
- ambang = recall 90% objek minyak di prediksi silang Yang; TIDAK disetel di Trujillo;
- uji Trujillo (trujillo_objek.csv tahap 27) SEKALI; status: semi-buta (Trujillo sudah dilihat saat diagnosis tahap 27);
- kriteria lulus (ditulis sebelum run): recall LUAS minyak >= 0,90; recall objek >= 0,80; look-alike dibuang >= 0,60;
  dilaporkan juga recall objek minyak > 10 km²;
- gagal -> opsi C: aplikasi hanya mengurutkan bercak (tak ada yang disembunyikan). Apa pun hasilnya, aplikasi tidak
  menyembunyikan bercak >= 10 km².
Pemakaian: python 28_pembeda_v2.py latih            (laptop; simpan pembeda_vv2.joblib)
           python 28_pembeda_v2.py uji OBJEK.csv    (Colab/laptop; nilai v2 di objek Trujillo)
"""
import json, os, sys
import numpy as np, pandas as pd, joblib
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import GroupKFold
from sklearn.metrics import roc_auc_score

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "results_pembeda")
FEAT2 = ["log_km2", "kompak", "panjang", "obj_db", "std_db", "kontras_db", "tepi_grad", "jarak_pantai_km", "cincin_db"]
MONO = [1 if f == "log_km2" else 0 for f in FEAT2]
mk = lambda: HistGradientBoostingClassifier(max_depth=4, max_iter=300, learning_rate=0.05, class_weight="balanced",
                                            monotonic_cst=MONO, random_state=0)


def latih():
    df = pd.read_csv(os.path.join(OUT, "yang_objek.csv")).sample(frac=1, random_state=0).reset_index(drop=True)
    p = np.zeros(len(df))
    for tr, te in GroupKFold(5).split(df, df.label, df.sid):
        p[te] = mk().fit(df.loc[tr, FEAT2], df.label[tr]).predict_proba(df.loc[te, FEAT2])[:, 1]
    thr = float(np.quantile(p[df.label == 1], 0.10)); keep = p >= thr
    cv = {"auc": round(roc_auc_score(df.label, p), 3), "ambang_recall90": round(thr, 3),
          "lookalike_dibuang": round(float(1 - keep[df.label == 0].mean()), 3)}
    m = mk().fit(df[FEAT2], df.label)
    joblib.dump({"model": m, "fitur": FEAT2, "ambang": thr, "sumber": "Yang & Singha 2025 (CC-BY-4.0), tahap 28 v2"},
                os.path.join(OUT, "pembeda_vv2.joblib"))
    json.dump(cv, open(os.path.join(OUT, "yang_cv_v2.json"), "w"), indent=1); print("CV Yang v2:", cv)


def uji(fn, pemb=os.path.join(OUT, "pembeda_vv2.joblib")):
    P = joblib.load(pemb); ob = pd.read_csv(fn)
    ob["gid"] = ob.kelas + "/" + ob.file  # nama file berulang antar kelas (Oil/00000.tif, Lookalike/00000.tif)
    ob["p2"] = P["model"].predict_proba(ob[P["fitur"]])[:, 1]; k = ob.p2 >= P["ambang"]; m = ob.label == 1
    r = {"auc": round(roc_auc_score(ob.label, ob.p2), 3), "recall_objek": round(float(k[m].mean()), 3),
         "recall_luas": round(float(ob.km2[m & k].sum() / ob.km2[m].sum()), 3),
         "lookalike_dibuang": round(float(1 - k[~m].mean()), 3),
         "recall_objek_gt10km2": round(float(k[m & (ob.km2 > 10)].mean()), 3)}
    rng = np.random.default_rng(0); g = {f: d.index.values for f, d in ob.groupby("gid")}; fl = list(g); bl = []
    for _ in range(1000):
        ii = np.concatenate([g[f] for f in rng.choice(fl, len(fl))]); mm, kk = m.values[ii], k.values[ii]
        bl.append(ob.km2.values[ii][mm & kk].sum() / ob.km2.values[ii][mm].sum())
    r["ci_recall_luas"] = [round(float(np.percentile(bl, q)), 3) for q in (2.5, 97.5)]
    r["auc_baseline_kontras_db"] = round(roc_auc_score(ob.label, ob.kontras_db.fillna(ob.kontras_db.median())), 3)
    lulus = r["recall_luas"] >= 0.90 and r["recall_objek"] >= 0.80 and r["lookalike_dibuang"] >= 0.60
    r["LULUS"] = bool(lulus)
    for kl in ["Lookalike", "No oil"]:
        d = ob[ob.kelas == kl]; a = d[k[d.index]].groupby("file").size()
        r[f"alarm_rata_{kl}"] = round(float(a.sum() / 150), 2)
    print(json.dumps(r, indent=1)); return r


if __name__ == "__main__":
    latih() if sys.argv[1] == "latih" else uji(sys.argv[2], *(sys.argv[3:4]))
