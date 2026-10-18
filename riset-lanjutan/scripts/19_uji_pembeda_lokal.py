"""Tahap 19: terapkan CNN pembeda (tahap 18, dilatih CSIRO) ke objek Balikpapan & Karawang (fitur_objek.csv tahap 17).
Aturan dikunci: potongan 4 x 4 km (200 px @20 m) berpusat di objek, regangan tetap -32..-17 dB -> 0..255,
ambang = ambang tahap 18 (tidak disetel ulang). Label lemah sama dengan tahap 17.
Keluaran: results_pembeda/lokal_cnn.csv, lokal_cnn_ringkasan.json
"""
import json, os
import numpy as np, pandas as pd, rasterio, torch, torch.nn as nn, torchvision
from PIL import Image
from sklearn.metrics import roc_auc_score
import sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from situs import _S

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "results_pembeda"); H = 100
thr = json.load(open(os.path.join(OUT, "csiro_cnn_ringkasan.json")))["ambang"]
m = torchvision.models.resnet18(); m.fc = nn.Linear(512, 1)
m.load_state_dict(torch.load(os.path.join(OUT, "csiro_cnn.pt"))); m.eval(); torch.set_num_threads(16)
df = pd.read_csv(os.path.join(OUT, "fitur_objek.csv"))
ps = np.zeros(len(df))
for (s, d), g in df.groupby(["situs", "date"]):
    with rasterio.open(os.path.join(HERE, _S[s]["data"], f"s1_vv_db_{d}_20m.tif")) as r:
        db = r.read(1).astype(float)
    u8 = np.clip((np.nan_to_num(db, nan=-32) + 32) / 15, 0, 1)
    u8 = np.pad(u8, H, mode="reflect")
    xs = []
    for _, o in g.iterrows():
        c = u8[int(o.py):int(o.py) + 2 * H, int(o.px_):int(o.px_) + 2 * H]
        x = np.asarray(Image.fromarray((c * 255).astype(np.uint8)).resize((224, 224), Image.BILINEAR), np.float32) / 255
        xs.append(torch.from_numpy((x - 0.449) / 0.226)[None].repeat(3, 1, 1))
    with torch.no_grad():
        ps[g.index] = torch.sigmoid(m(torch.stack(xs))[:, 0]).numpy()
df["p_cnn"] = ps; df["lolos"] = ps >= thr
df.to_csv(os.path.join(OUT, "lokal_cnn.csv"), index=False)
res = {"ambang": thr}
for s, g in df.groupby("situs"):
    pos, cl = g.label == 1, g[g.label == 0]
    a0 = cl.groupby("date").size(); a1 = cl[cl.lolos].groupby("date").size().reindex(a0.index, fill_value=0)
    res[s] = {"auc": round(roc_auc_score(g.label, g.p_cnn), 3), "recall_objek": round(float(g.lolos[pos].mean()), 2),
              "recall_luas": round(float(g.km2[pos & g.lolos].sum() / g.km2[pos].sum()), 2),
              "alarm_per_lintasan_median": [float(a0.median()), float(a1.median())]}
json.dump(res, open(os.path.join(OUT, "lokal_cnn_ringkasan.json"), "w"), indent=1); print(json.dumps(res, indent=1))
