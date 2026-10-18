"""Tahap 29: penjelasan SHAP untuk skor prioritas v2 (pembeda_vv2.joblib).
- Keluaran yang dijelaskan: margin mentah (log-odds) HistGradientBoosting, kelas 1 = minyak. Bukan sebab-akibat:
  hanya menggambarkan perilaku model terhadap fitur.
- Explainer: eksak (model-agnostik pada decision_function; TreeExplainer gagal uji aditivitas untuk HistGB monoton),
  latar belakang 50 objek acak Yang (seed 0), masker Independent. Aditivitas dicek terhadap decision_function.
- Global: rata-rata |SHAP| di Yang (500 sampel), Trujillo, dan objek lokal (Karawang/Balikpapan).
- fungsi alasan(): 2 fitur dengan kontribusi terbesar per bercak, dalam bahasa awam (dipakai 26_ekspor_web.py).
Keluaran: results_pembeda/shap_v2_global.csv, shap_v2_beeswarm.png
"""
import os, sys
import numpy as np, pandas as pd, joblib, shap

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); OUT = os.path.join(HERE, "results_pembeda")
NAMA = {"log_km2": ("luas besar", "luas kecil"), "kompak": ("bentuk membulat", "bentuk tidak membulat"),
        "panjang": ("bentuk memanjang", "bentuk tidak memanjang"), "obj_db": ("bercak sangat gelap", "bercak kurang gelap"),
        "std_db": ("isi bercak tidak rata", "isi bercak rata"), "kontras_db": ("kontras tinggi dengan laut sekitar", "kontras rendah dengan laut sekitar"),
        "tepi_grad": ("tepi tajam", "tepi kabur"), "jarak_pantai_km": ("jauh dari pantai", "dekat pantai"),
        "cincin_db": ("laut sekitar terang (berangin)", "laut sekitar gelap (tenang)")}
_P = _E = _MED = None


def _init():
    global _P, _E, _MED
    if _E is None:
        _P = joblib.load(os.path.join(OUT, "pembeda_vv2.joblib"))
        bg = pd.read_csv(os.path.join(OUT, "yang_objek.csv"))[_P["fitur"]].sample(50, random_state=0)
        _MED = bg.median()
        _E = shap.Explainer(_P["model"].decision_function, shap.maskers.Independent(bg.fillna(bg.median()), max_samples=50),
                            algorithm="exact")
    return _P, _E


def jelaskan(X):
    P, E = _init()
    X = X[P["fitur"]]
    ex = E(X.fillna(X.median()))
    err = np.abs(np.asarray(ex.base_values) + ex.values.sum(1) - P["model"].decision_function(X.fillna(X.median()))).max()
    assert err < 1e-3, f"aditivitas gagal: {err}"
    return ex


def alasan(X):
    """Daftar teks: 2 kontribusi terbesar per baris, mis. '↑ kontras tinggi dengan laut sekitar; ↓ dekat pantai'."""
    P, _ = _init(); ex = jelaskan(X); out = []
    for v, row in zip(ex.values, X[P["fitur"]].itertuples(index=False)):
        idx = np.argsort(-np.abs(v))[:2]; s = []
        for i in idx:
            f = P["fitur"][i]; arah = "↑" if v[i] > 0 else "↓"
            s.append(f"{arah} {NAMA[f][0] if getattr(row, f) >= _MED[f] else NAMA[f][1]}")
        out.append("; ".join(s))
    return out


if __name__ == "__main__":
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    P, _ = _init()
    sets = {"Yang": pd.read_csv(os.path.join(OUT, "yang_objek.csv")).sample(500, random_state=1),
            "Trujillo": pd.read_csv(os.path.join(HERE, "results_trujillo", "trujillo_objek.csv")),
            "Lokal": pd.read_csv(os.path.join(OUT, "fitur_objek.csv"))}
    g = {}
    for k, d in sets.items():
        ex = jelaskan(d); g[k] = np.abs(ex.values).mean(0)
        if k == "Lokal":
            shap.plots.beeswarm(ex, show=False, max_display=9); plt.tight_layout()
            plt.savefig(os.path.join(OUT, "shap_v2_beeswarm.png"), dpi=130); plt.close()
    gl = pd.DataFrame(g, index=P["fitur"]).round(3).sort_values("Yang", ascending=False)
    gl.to_csv(os.path.join(OUT, "shap_v2_global.csv")); print(gl.to_string())
    print(alasan(sets["Lokal"].head(3)))
