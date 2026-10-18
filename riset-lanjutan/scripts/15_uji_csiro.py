"""Tahap 15: uji U-Net Lite (CAYMAN, tanpa latih ulang) pada dataset CSIRO (label per potongan: 0 = tanpa minyak/look-alike, 1 = minyak).
Aturan DIBEKUKAN sebelum melihat hasil (17 Okt 2026):
- praproses = cara CAYMAN untuk PNG 8-bit SOS (x/255, normalisasi mean/std), karena skala dB CSIRO tidak diketahui;
- ambang piksel 0,45 (validasi CAYMAN); potongan dinyatakan "ada minyak" bila >= 1% piksel ditandai.
Kurva untuk ambang lain dilaporkan sebagai informasi, bukan untuk memilih ambang.
Pemakaian: python scripts/15_uji_csiro.py <folder csiro berisi kelas0/ dan kelas1/>
"""
import glob, json, os, sys
import numpy as np, pandas as pd, onnxruntime as ort
from PIL import Image

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ONNX = os.path.join(HERE, "..", "ML DAN DL", "oil-spill-sar", "outputs", "onnx", "unet_lite_fp32.onnx")
MEAN, STD, THR, FRAC, T = 0.38344, 0.201973, 0.45, 0.01, 256
root = sys.argv[1]
fs = sorted(glob.glob(os.path.join(root, "kelas*", "**", "*.jpg"), recursive=True))
sess = ort.InferenceSession(ONNX, providers=["CPUExecutionProvider"]); inp = sess.get_inputs()[0].name
rows = []
for k in range(0, len(fs), 32):
    batch, meta = [], []
    for f in fs[k:k + 32]:
        x = (np.asarray(Image.open(f).convert("L"), np.float32) / 255 - MEAN) / STD
        H, W = x.shape; ys, xs = [0, H - T], [0, W - T]
        for y in ys:
            for xx in xs:
                batch.append(x[y:y + T, xx:xx + T]); meta.append((f, y, xx, H, W))
    lg = np.concatenate([sess.run(None, {inp: b[None, None]})[0][:, 0] for b in batch])   # model ONNX: batch 1, keluaran logit
    p = 1 / (1 + np.exp(-lg))
    acc = {}
    for (f, y, xx, H, W), pr in zip(meta, p):
        a, c = acc.setdefault(f, (np.zeros((H, W), np.float32), np.zeros((H, W), np.float32)))
        a[y:y + T, xx:xx + T] += pr; c[y:y + T, xx:xx + T] += 1
    for f, (a, c) in acc.items():
        prob = a / c; b = os.path.basename(f)
        rows.append({"file": b, "label": int(b.split("_cls_")[1][0]), "wilayah": b.split("_")[-3],
                     "frac_045": float((prob >= THR).mean()), "pmax": float(prob.max())})
    print(f"{k + len(batch) // 4}/{len(fs)}", end="\r", flush=True)

df = pd.DataFrame(rows)
out = os.path.join(HERE, "results_csiro"); os.makedirs(out, exist_ok=True)
df.to_csv(os.path.join(out, "csiro_per_potongan.csv"), index=False)
df["pred"] = df.frac_045 >= FRAC
def met(g):
    tp = int((g.pred & (g.label == 1)).sum()); fp = int((g.pred & (g.label == 0)).sum())
    fn = int((~g.pred & (g.label == 1)).sum()); tn = int((~g.pred & (g.label == 0)).sum())
    return {"n": len(g), "n_minyak": tp + fn, "recall": round(tp / max(tp + fn, 1), 3),
            "alarm_palsu_rate": round(fp / max(fp + tn, 1), 3), "presisi": round(tp / max(tp + fp, 1), 3)}
from sklearn.metrics import roc_auc_score
res = {"aturan_beku": {"thr_piksel": THR, "min_frac": FRAC, "praproses": "CAYMAN 8-bit"},
       "semua": met(df), "auc_frac": round(roc_auc_score(df.label, df.frac_045), 3),
       "per_wilayah": {w: met(g) for w, g in df.groupby("wilayah") if len(g) >= 30},
       "kurva_info": {str(f): met(df.assign(pred=df.frac_045 >= f)) for f in [0.001, 0.005, 0.02, 0.05, 0.1]}}
json.dump(res, open(os.path.join(out, "csiro_ringkasan.json"), "w"), indent=1)
print(json.dumps({k: res[k] for k in ["semua", "auc_frac"]}, indent=1))
for w in ["SIN", "JAV", "BOR", "MLA", "PHI", "GBR"]:
    if w in res["per_wilayah"]: print(w, res["per_wilayah"][w])
