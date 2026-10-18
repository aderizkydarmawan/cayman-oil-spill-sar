"""Tahap 24: jalankan alur aplikasi (U-Net CAYMAN, regangan tetap -32..-17 dB, ambang 0,45, saring.py, objek >= 0,1 km²)
pada patch Yang & Singha hasil tahap 23, lalu beri label per objek. Aturan dikunci sebelum hasil (17 Okt 2026):
- patch set oil (ow/oc): objek yang beririsan kotak minyak ahli = 1 (minyak); objek lain di patch itu DIBUANG (tak diketahui);
- patch set no-oil (nw/nc): semua objek = 0 (look-alike menurut ahli);
- dicatat juga: fraksi kotak minyak ahli yang tersentuh objek U-Net (recall detektor pada data ahli).
Keluaran: results_pembeda/yang_objek.csv, yang_recall_detektor.json
"""
import glob, json, os, sys
from concurrent.futures import ProcessPoolExecutor
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "..", "data_terbuka", "yang_singha", "gee"); OUT = os.path.join(HERE, "results_pembeda")
ONNX = os.path.join(HERE, "..", "ML DAN DL", "oil-spill-sar", "outputs", "onnx", "unet_lite_fp32.onnx")
MEAN, STD, THR, TILE, STRIDE = 0.38344, 0.201973, 0.45, 256, 128
_sess = None


def unet(db, valid):
    global _sess
    import onnxruntime as ort
    if _sess is None:
        so = ort.SessionOptions(); so.intra_op_num_threads = 1
        _sess = ort.InferenceSession(ONNX, so, providers=["CPUExecutionProvider"])
    u8 = np.where(valid, np.round(np.clip((db + 32) / 15, 0, 1) * 255), 0).astype(np.uint8)
    xn = (u8 / 255.0 - MEAN) / STD; xn[~valid] = (np.median(u8[valid]) / 255.0 - MEAN) / STD
    H, W = u8.shape
    ph = (-(H - TILE) % STRIDE) if H > TILE else TILE - H; pw = (-(W - TILE) % STRIDE) if W > TILE else TILE - W
    xp = np.pad(xn, ((0, ph), (0, pw)), mode="reflect").astype(np.float32)
    acc = np.zeros(xp.shape, np.float32); cnt = np.zeros(xp.shape, np.float32)
    for y in range(0, xp.shape[0] - TILE + 1, STRIDE):
        for x in range(0, xp.shape[1] - TILE + 1, STRIDE):
            lg = _sess.run(None, {"image": xp[None, None, y:y + TILE, x:x + TILE]})[0][0, 0]
            acc[y:y + TILE, x:x + TILE] += 1 / (1 + np.exp(-lg)); cnt[y:y + TILE, x:x + TILE] += 1
    return ((acc / np.maximum(cnt, 1))[:H, :W] >= THR) & valid


def proses(fn):
    from fitur_objek import fitur
    from scipy import ndimage as ndi
    z = np.load(fn, allow_pickle=True)
    db, sea, kotak, st = z["vv"], z["sea"] > 0, z["kotak"] > 0, str(z["set"])
    vh = z["vh"] if z["vh"].size else None
    valid = sea & np.isfinite(db) & (db != 0)
    if valid.sum() < 1000:
        return [], None
    mk = unet(db, valid)
    rows, lab = fitur(db, sea, mk, 20.0, vh)
    pid = os.path.basename(fn)[:-4]
    out = []
    for r in rows:
        hit = bool(kotak[lab == r["label_id"]].any())
        if st.startswith("o") and not hit:
            continue
        out.append({"patch": pid, "set": st, "sid": str(z["sid"]), "label": int(st.startswith("o")), **r})
    rec = None
    if st.startswith("o") and kotak.any():
        kl, kn = ndi.label(kotak)
        rec = (kn, int(sum(mk[kl == i].any() for i in range(1, kn + 1))))
    return out, rec


if __name__ == "__main__":
    fs = sorted(glob.glob(os.path.join(SRC, "*.npz"))); print("patch:", len(fs), flush=True)
    rows, nk, nh = [], 0, 0
    with ProcessPoolExecutor(16) as ex:
        for i, (o, rec) in enumerate(ex.map(proses, fs, chunksize=8)):
            rows += o
            if rec: nk += rec[0]; nh += rec[1]
            if i % 300 == 0: print(i, len(rows), flush=True)
    df = pd.DataFrame(rows); df.to_csv(os.path.join(OUT, "yang_objek.csv"), index=False)
    res = {"patch": len(fs), "objek": len(df), "per_set": df.groupby("set").size().to_dict(),
           "kotak_minyak_ahli": nk, "kotak_tersentuh_unet": nh, "recall_detektor": round(nh / max(nk, 1), 3)}
    json.dump(res, open(os.path.join(OUT, "yang_recall_detektor.json"), "w"), indent=1); print(json.dumps(res, indent=1))
