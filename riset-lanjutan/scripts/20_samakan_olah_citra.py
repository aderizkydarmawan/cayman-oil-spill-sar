"""Tahap 20: samakan cara olah citra kita dengan CSIRO, lalu uji ulang CNN v2 (tahap 18 v2) pada objek Bpn/Krw.
README CSIRO tidak tersedia; skala 8-bit-nya ditebak dari data. Aturan dikunci sebelum hasil (17 Okt 2026):
- "asli"        : regangan -32..-17 dB (seperti tahap 19);
- "regang_cocok": rentang dB [lo, hi] dipilih HANYA dengan meminimalkan jarak Wasserstein sebaran piksel potongan kita
                  (300 potongan acak, label TIDAK dipakai) ke sebaran piksel CSIRO wilayah latih  <- varian utama;
- "histmatch"   : tiap potongan dipetakan kuantil ke sebaran piksel CSIRO wilayah latih.
Ambang = ambang v2 (tidak disetel). Label lemah seperti tahap 17.
Keluaran: results_pembeda/olah_citra_ringkasan.json, olah_citra_objek.csv, contoh_potongan.png
"""
import glob, json, os, sys
import numpy as np, pandas as pd, rasterio, torch, torch.nn as nn, torchvision
from PIL import Image
from scipy.stats import wasserstein_distance
from sklearn.metrics import roc_auc_score
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from situs import _S

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "results_pembeda"); H = 100; rng = np.random.default_rng(0)
thr = json.load(open(os.path.join(OUT, "csiro_cnn_v2_ringkasan.json")))["ambang"]
m = torchvision.models.resnet18(); m.fc = nn.Linear(512, 1)
m.load_state_dict(torch.load(os.path.join(OUT, "csiro_cnn_v2.pt"), weights_only=True)); m.eval(); torch.set_num_threads(16)

# sebaran piksel CSIRO (wilayah latih saja)
cs = [f for f in glob.glob(os.path.join(HERE, "..", "data_terbuka", "csiro", "kelas*", "**", "*.jpg"), recursive=True)
      if os.path.basename(f).split("_")[-3] not in ("SIN", "JAV")]
ref = np.concatenate([np.asarray(Image.open(f).convert("L"), np.float32).ravel()[::97] for f in rng.choice(cs, 300, replace=False)])
ref_q = np.quantile(ref, np.linspace(0, 1, 257))

df = pd.read_csv(os.path.join(OUT, "fitur_objek.csv"))
chips = np.zeros((len(df), 2 * H, 2 * H), np.float32)          # dB, 4 x 4 km
for (s, d), g in df.groupby(["situs", "date"]):
    with rasterio.open(os.path.join(HERE, _S[s]["data"], f"s1_vv_db_{d}_20m.tif")) as r:
        db = r.read(1).astype(np.float32)
    db = np.where(np.isfinite(db) & (db != 0), db, np.nan); db = np.where(np.isnan(db), np.nanmedian(db), db)
    db = np.pad(db, H, mode="reflect")
    for i, o in g.iterrows():
        chips[i] = db[int(o.py):int(o.py) + 2 * H, int(o.px_):int(o.px_) + 2 * H]

sub = chips[rng.choice(len(chips), 300, replace=False)][:, ::4, ::4].ravel()
best = min(((wasserstein_distance(np.clip((sub - lo) / (hi - lo), 0, 1) * 255, ref), lo, hi)
            for lo in range(-40, -23) for hi in range(-20, -4)))
LO, HI = best[1], best[2]; print("regang_cocok:", LO, HI, "dB | jarak", round(best[0], 1), flush=True)


def to_u8(c, mode):
    if mode == "asli": return np.clip((c + 32) / 15, 0, 1) * 255
    if mode == "regang_cocok": return np.clip((c - LO) / (HI - LO), 0, 1) * 255
    q = np.quantile(c, np.linspace(0, 1, 257)); return np.interp(c, q, ref_q)


def score(mode):
    ps = []
    for k in range(0, len(chips), 128):
        xs = [torch.from_numpy((np.asarray(Image.fromarray(to_u8(c, mode).astype(np.uint8)).resize((224, 224), Image.BILINEAR),
                                           np.float32) / 255 - 0.449) / 0.226)[None].repeat(3, 1, 1) for c in chips[k:k + 128]]
        with torch.no_grad(): ps.append(torch.sigmoid(m(torch.stack(xs))[:, 0]).numpy())
    return np.concatenate(ps)


res = {"ambang_v2": thr, "regang_cocok_dB": [LO, HI], "varian_utama": "regang_cocok"}
for mode in ["asli", "regang_cocok", "histmatch"]:
    df["p_" + mode] = p = score(mode); res[mode] = {}
    for s, g in df.groupby("situs"):
        pp, pos, cl = p[g.index], g.label == 1, g.label == 0
        a0 = g[cl].groupby("date").size(); a1 = g[cl & (pp >= thr)].groupby("date").size().reindex(a0.index, fill_value=0)
        res[mode][s] = {"auc": round(roc_auc_score(g.label, pp), 3), "recall_objek": round(float((pp[pos] >= thr).mean()), 2),
                        "recall_luas": round(float(g.km2[pos & (pp >= thr)].sum() / g.km2[pos].sum()), 2),
                        "alarm_per_lintasan_median": [float(a0.median()), float(a1.median())],
                        "alarm_per_lintasan_rata": [round(a0.mean(), 2), round(a1.mean(), 2)]}
    print(mode, json.dumps(res[mode]), flush=True)
df.drop(columns=[]).to_csv(os.path.join(OUT, "olah_citra_objek.csv"), index=False)
json.dump(res, open(os.path.join(OUT, "olah_citra_ringkasan.json"), "w"), indent=1)

# contoh visual: 4 potongan CSIRO vs 4 potongan kita (regang_cocok)
fig, ax = plt.subplots(2, 4, figsize=(10, 5.4))
for j, f in enumerate(rng.choice(cs, 4, replace=False)):
    ax[0, j].imshow(np.asarray(Image.open(f).convert("L")), cmap="gray", vmin=0, vmax=255); ax[0, j].set_title("CSIRO " + os.path.basename(f).split("_")[-3], fontsize=8)
for j, i in enumerate(list(df[df.label == 1].index[:2]) + list(rng.choice(df[df.label == 0].index, 2))):
    ax[1, j].imshow(to_u8(chips[i], "regang_cocok"), cmap="gray", vmin=0, vmax=255)
    ax[1, j].set_title(f"{df.situs[i]} {'minyak' if df.label[i] else 'bukan'} p={df.p_regang_cocok[i]:.2f}", fontsize=8)
for a in ax.ravel(): a.axis("off")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "contoh_potongan.png"), dpi=110)
