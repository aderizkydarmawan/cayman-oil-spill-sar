"""Tahap 3: jalankan model CAYMAN apa adanya (tanpa latih ulang) pada citra utuh Balikpapan.
Pemakaian: python 03_inferensi.py <tif> <stretch: pct|sosmatch>
- pct      : VV dB laut dipetakan p1..p99 -> 0..255
- sosmatch : VV dB laut distandardisasi agar mean/std = statistik train SOS (0.38344, 0.20197)
Jendela geser 256, stride 128, probabilitas dirata-rata; daratan dimasker.
Keluaran: results/<nama>/prob_<model>.tif, mask_<model>.tif, input_u8.tif, ringkasan.json
"""
import os, sys, json, time, numpy as np, rasterio, onnxruntime as ort

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from situs import BBOX, CRS, ORBIT, ERA5_HOUR, LOOK_AZ, SPILL, YEARS, INNER, DATA, RESULTS, NAME as SITUS, SPILL_REF
CAY = os.path.join(HERE, "..", "ML DAN DL", "oil-spill-sar", "outputs")
MODELS = {  # file, ambang validasi CAYMAN (metrics_v2.json)
    "unet_lite": (os.path.join(CAY, "onnx", "unet_lite_fp32.onnx"), 0.45),
    "deeplabv3p": (os.path.join(CAY, "v2", "onnx", "deeplabv3p_mnv2_fp32.onnx"), 0.50),
}
MEAN, STD = 0.38344, 0.201973
TILE, STRIDE = 256, 128

tif, stretch = sys.argv[1], sys.argv[2]
with rasterio.open(tif) as src:
    db, sea, prof = src.read(1), src.read(2) > 0, src.profile
valid = sea & np.isfinite(db)
v = db[valid]
if stretch == "pct":
    lo, hi = np.percentile(v, [1, 99])
    x = np.clip((db - lo) / (hi - lo), 0, 1)
elif stretch.startswith("fixed"):          # fixed:<lo_dB>:<hi_dB>, sama untuk semua tanggal
    lo, hi = map(float, stretch.split(":")[1:])
    x = np.clip((db - lo) / (hi - lo), 0, 1)
    stretch = f"fixed{int(lo)}_{int(hi)}"
elif stretch == "sosmatch":
    x = np.clip((db - v.mean()) / v.std() * STD + MEAN, 0, 1)
else:
    raise SystemExit("stretch?")
u8 = np.where(valid, np.round(x * 255), 0).astype(np.uint8)   # meniru PNG 8-bit SOS
xn = ((u8 / 255.0) - MEAN) / STD
xn[~valid] = (np.median(u8[valid]) / 255.0 - MEAN) / STD        # daratan diisi nilai laut tipikal

name = os.path.splitext(os.path.basename(tif))[0] + "_" + stretch
od = os.path.join(RESULTS, name); os.makedirs(od, exist_ok=True)
H, W = u8.shape
pad_h, pad_w = (-(H - TILE) % STRIDE) if H > TILE else TILE - H, (-(W - TILE) % STRIDE) if W > TILE else TILE - W
xp = np.pad(xn, ((0, pad_h), (0, pad_w)), mode="reflect").astype(np.float32)
P = dict(prof, count=1, dtype="float32", nodata=None)
with rasterio.open(os.path.join(od, "input_u8.tif"), "w", **dict(prof, count=1, dtype="uint8", nodata=0)) as d:
    d.write(u8, 1)

summary = {"tif": os.path.basename(tif), "stretch": stretch, "shape": [H, W],
           "pixel_m": prof["transform"].a, "sea_km2": float(valid.sum() * prof["transform"].a ** 2 / 1e6), "models": {}}
for m, (path, thr) in MODELS.items():
    sess = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
    acc = np.zeros(xp.shape, np.float32); cnt = np.zeros(xp.shape, np.float32)
    t0 = time.time(); n = 0
    for y in range(0, xp.shape[0] - TILE + 1, STRIDE):
        batch, pos = [], []
        for xx in range(0, xp.shape[1] - TILE + 1, STRIDE):
            batch.append(xp[y:y + TILE, xx:xx + TILE]); pos.append(xx)
        lg = sess.run(None, {"image": np.stack(batch)[:, None]})[0][:, 0] if False else \
             np.concatenate([sess.run(None, {"image": b[None, None]})[0][:, 0] for b in batch])
        for k, xx in enumerate(pos):
            acc[y:y + TILE, xx:xx + TILE] += 1 / (1 + np.exp(-lg[k])); cnt[y:y + TILE, xx:xx + TILE] += 1
        n += len(batch)
    prob = (acc / np.maximum(cnt, 1))[:H, :W]
    prob[~valid] = 0
    mask = (prob >= thr) & valid
    with rasterio.open(os.path.join(od, f"prob_{m}.tif"), "w", **P) as d: d.write(prob, 1)
    with rasterio.open(os.path.join(od, f"mask_{m}.tif"), "w", **dict(prof, count=1, dtype="uint8", nodata=None)) as d:
        d.write(mask.astype(np.uint8), 1)
    summary["models"][m] = {"threshold": thr, "tiles": n, "sec": round(time.time() - t0, 1),
                            "oil_km2": float(mask.sum() * prof["transform"].a ** 2 / 1e6),
                            "oil_frac_sea": float(mask.sum() / valid.sum())}
    print(m, summary["models"][m])
json.dump(summary, open(os.path.join(od, "ringkasan.json"), "w"), indent=1)
print("->", od)
