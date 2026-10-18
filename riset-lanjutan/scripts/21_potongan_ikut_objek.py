"""Tahap 21 (EKSPLORATIF, ide muncul setelah tahap 20): ukuran potongan mengikuti objek.
Sisi potongan = max(4 km, 3 x akar luas objek), lalu diperkecil ke 224 px; regangan -31..-17 dB; model CNN v2.
Keluaran: results_pembeda/potongan_objek_ringkasan.json
"""
import json, os, sys
import numpy as np, pandas as pd, rasterio, torch, torch.nn as nn, torchvision
from PIL import Image
from sklearn.metrics import roc_auc_score
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from situs import _S
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); OUT = os.path.join(HERE, "results_pembeda")
m = torchvision.models.resnet18(); m.fc = nn.Linear(512, 1)
m.load_state_dict(torch.load(os.path.join(OUT, "csiro_cnn_v2.pt"), weights_only=True)); m.eval(); torch.set_num_threads(16)
df = pd.read_csv(os.path.join(OUT, "fitur_objek.csv")); p = np.zeros(len(df))
for (s, d), g in df.groupby(["situs", "date"]):
    with rasterio.open(os.path.join(HERE, _S[s]["data"], f"s1_vv_db_{d}_20m.tif")) as r:
        db = r.read(1).astype(np.float32)
    db = np.where(np.isfinite(db) & (db != 0), db, np.nan); db = np.where(np.isnan(db), np.nanmedian(db), db)
    u8 = (np.clip((db + 31) / 14, 0, 1) * 255).astype(np.uint8); P = 1200; u8 = np.pad(u8, P, mode="reflect")
    xs = []
    for _, o in g.iterrows():
        h = int(max(2000, 1.5 * np.sqrt(o.km2) * 1000) / 20); h = min(h, P)
        c = u8[int(o.py) + P - h:int(o.py) + P + h, int(o.px_) + P - h:int(o.px_) + P + h]
        x = np.asarray(Image.fromarray(c).resize((224, 224), Image.BILINEAR), np.float32) / 255
        xs.append(torch.from_numpy((x - 0.449) / 0.226)[None].repeat(3, 1, 1))
    with torch.no_grad(): p[g.index] = torch.sigmoid(m(torch.stack(xs))[:, 0]).numpy()
df["p"] = p; res = {}
for s, g in df.groupby("situs"):
    r = g[g.label == 1].copy(); r["rank"] = r.p.rank(ascending=False)
    res[s] = {"auc": round(roc_auc_score(g.label, g.p), 3), "skor_bercak_terbesar": round(float(r.loc[r.km2.idxmax(), "p"]), 3),
              "peringkat_bercak_terbesar_di_citranya": int(r.loc[r.km2.idxmax(), "rank"]), "n_minyak": len(r)}
json.dump(res, open(os.path.join(OUT, "potongan_objek_ringkasan.json"), "w"), indent=1); print(json.dumps(res, indent=1))
