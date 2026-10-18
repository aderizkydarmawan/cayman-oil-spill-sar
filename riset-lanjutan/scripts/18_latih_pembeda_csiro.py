"""Tahap 18: latih pembeda minyak vs bukan-minyak (CNN kecil, ResNet18 pralatih ImageNet) dengan label ahli CSIRO.
Aturan dikunci sebelum hasil (17 Okt 2026):
- UJI = wilayah SIN + JAV (paling mirip Indonesia), tidak pernah dilihat saat latih;
- LATIH = semua wilayah lain; 15% CITRA ASAL (seed 0, v2) jadi validasi untuk memilih epoch & ambang;
- ambang = recall 80% minyak di validasi, dipakai apa adanya di uji;
- 6 epoch, AdamW lr 3e-4, augmentasi flip/rot90, input 224 px abu-abu x3 kanal.
Keluaran: results_pembeda/csiro_cnn.pt, csiro_cnn_ringkasan.json, csiro_cnn_prediksi_uji.csv
Pemakaian: python scripts/18_latih_pembeda_csiro.py <folder csiro berisi kelas0/ dan kelas1/>
"""
import glob, json, os, sys, time
import numpy as np, pandas as pd, torch, torch.nn as nn, torchvision
from PIL import Image
from sklearn.metrics import roc_auc_score

torch.manual_seed(0); torch.set_num_threads(16)
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "results_pembeda"); os.makedirs(OUT, exist_ok=True)
UJI = {"SIN", "JAV"}
fs = sorted(glob.glob(os.path.join(sys.argv[1], "kelas*", "**", "*.jpg"), recursive=True))
df = pd.DataFrame({"f": fs}); b = df.f.map(os.path.basename)
df["label"] = b.map(lambda s: int(s.split("_cls_")[1][0])); df["wilayah"] = b.map(lambda s: s.split("_")[-3])
df["citra"] = b.map(lambda s: s.split("_img_")[1].rsplit("_", 3)[0])
te = df[df.wilayah.isin(UJI)]; rest = df[~df.wilayah.isin(UJI)]
# v2: validasi dipisah per citra asal (potongan secitra tidak boleh di latih & val sekaligus)
ids = rest.citra.drop_duplicates().sample(frac=1, random_state=0); vid = set(ids[:int(len(ids) * .15)])
va, tr = rest[rest.citra.isin(vid)], rest[~rest.citra.isin(vid)]
print("latih", len(tr), "val", len(va), "uji", len(te), "| minyak latih", int(tr.label.sum()))


def load(f):
    x = np.asarray(Image.open(f).convert("L").resize((224, 224), Image.BILINEAR), np.float32) / 255
    return (x - 0.449) / 0.226


class DS(torch.utils.data.Dataset):
    def __init__(s, d, aug): s.d, s.aug = d.reset_index(drop=True), aug
    def __len__(s): return len(s.d)
    def __getitem__(s, i):
        x = load(s.d.f[i])
        if s.aug:
            x = np.rot90(x, np.random.randint(4)); x = x[:, ::-1] if np.random.rand() < .5 else x
        return torch.from_numpy(np.ascontiguousarray(x))[None].repeat(3, 1, 1), torch.tensor(float(s.d.label[i]))


def dl(d, aug): return torch.utils.data.DataLoader(DS(d, aug), batch_size=64, shuffle=aug, num_workers=0)
m = torchvision.models.resnet18(weights="IMAGENET1K_V1"); m.fc = nn.Linear(512, 1)
opt = torch.optim.AdamW(m.parameters(), 3e-4, weight_decay=1e-4)
pw = torch.tensor((tr.label == 0).sum() / max(tr.label.sum(), 1)); lossf = nn.BCEWithLogitsLoss(pos_weight=pw)


def pred(d):
    m.eval(); out = []
    with torch.no_grad():
        for x, _ in dl(d, False): out.append(torch.sigmoid(m(x)[:, 0]).numpy())
    return np.concatenate(out)


best, hist = -1, []
for ep in range(6):
    m.train(); t = time.time()
    for x, y in dl(tr, True):
        opt.zero_grad(); l = lossf(m(x)[:, 0], y); l.backward(); opt.step()
    pv = pred(va); auc = roc_auc_score(va.label, pv); hist.append(round(auc, 3))
    print(f"epoch {ep} val AUC {auc:.3f} ({time.time() - t:.0f} d)", flush=True)
    if auc > best: best = auc; torch.save(m.state_dict(), os.path.join(OUT, "csiro_cnn_v2.pt")); pv_best = pv

m.load_state_dict(torch.load(os.path.join(OUT, "csiro_cnn_v2.pt")))
thr = float(np.quantile(pv_best[va.label.values == 1], 0.2))
pt = pred(te); te = te.assign(p=pt, pred=pt >= thr)
te.drop(columns="f").assign(file=te.f.map(os.path.basename)).to_csv(os.path.join(OUT, "csiro_cnn_v2_prediksi_uji.csv"), index=False)


def met(g):
    tp = int((g.pred & (g.label == 1)).sum()); fp = int((g.pred & (g.label == 0)).sum())
    fn = int((~g.pred & (g.label == 1)).sum()); tn = int((~g.pred & (g.label == 0)).sum())
    return {"n": len(g), "auc": round(roc_auc_score(g.label, g.p), 3), "recall": round(tp / max(tp + fn, 1), 3),
            "alarm_palsu_rate": round(fp / max(fp + tn, 1), 3), "presisi": round(tp / max(tp + fp, 1), 3)}
res = {"val_auc_per_epoch": hist, "ambang": round(thr, 3), "uji_semua": met(te),
       "uji_per_wilayah": {w: met(g) for w, g in te.groupby("wilayah")},
       "pembanding_unet_beku_tahap15": "AUC 0,51 semua; JAV 0,889; SIN 0,689"}
json.dump(res, open(os.path.join(OUT, "csiro_cnn_v2_ringkasan.json"), "w"), indent=1); print(json.dumps(res, indent=1))
