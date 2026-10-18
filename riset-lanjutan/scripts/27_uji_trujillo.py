"""Tahap 27: uji independen alur aplikasi (U-Net CAYMAN + saring.py + pemilah tahap 25) pada bagian UJI Trujillo-Acatitla dkk.
(Zenodo 13761290, CC-BY-4.0): 150 gambar per kelas Oil / Lookalike / No oil, TIFF dB 2048x2048x2 (kanal0 VH, kanal1 VV).
Data ini belum pernah dipakai melatih, menyetel, atau memilih ambang apa pun. Dijalankan di Colab (data 36 GB).
Aturan dikunci sebelum hasil (18 Okt 2026):
- hanya VV (kanal1); ukuran piksel dibaca dari GeoTIFF, bila tak ada dianggap 10 m; diperkecil ke 20 m (rata-rata daya linear);
- tidak ada data daratan: laut = piksel berdata (jarak_pantai_km jadi 99 untuk semua objek — catat sebagai beda domain);
- detektor, ambang 0,45, regangan -32..-17 dB, saring.py, objek >= 0,1 km², pemilah dan ambangnya PERSIS seperti aplikasi, tanpa penyetelan;
- Oil: recall piksel, presisi piksel, IoU (masker diperkecil ke 20 m, piksel minyak bila >= 50% sub-piksel), recall objek ahli >= 0,1 km²;
- objek U-Net yang menyentuh masker ahli = minyak; objek lain di gambar Oil DIBUANG (tak diketahui; sama dengan tahap 24);
  semua objek di gambar Lookalike/No oil = palsu;
- pemilah: AUC, recall minyak & look-alike dibuang pada ambang aplikasi, alarm per gambar sebelum/sesudah;
- laut tenang: fraksi gambar per kelas yang ditandai tenang (> 15%) — uji independen ambang 15%;
- selang kepercayaan 95%: bootstrap per gambar, 1000 ulangan, seed 0.
Pemakaian (Colab): python 27_uji_trujillo.py --data /content/tru --model-dir /content/bekal --out /content/hasil27
"""
import argparse, glob, json, os, sys
from concurrent.futures import ProcessPoolExecutor
import numpy as np, pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument("--data", default="/content/tru"); ap.add_argument("--model-dir", default="/content/bekal")
ap.add_argument("--out", default="/content/hasil27"); ap.add_argument("--workers", type=int, default=os.cpu_count())
A = ap.parse_args()
sys.path.insert(0, A.model_dir)
ONNX, PEMB = os.path.join(A.model_dir, "unet_lite_fp32.onnx"), os.path.join(A.model_dir, "pembeda_vv.joblib")
MEAN, STD, THR, TILE, STRIDE, PX = 0.38344, 0.201973, 0.45, 256, 128, 20.0
KELAS = ["Oil", "Lookalike", "No oil"]
_sess = None


def unet(db, valid):
    global _sess
    import onnxruntime as ort
    if _sess is None:
        so = ort.SessionOptions(); so.intra_op_num_threads = 1
        _sess = ort.InferenceSession(ONNX, so, providers=[p for p in ["CUDAExecutionProvider", "CPUExecutionProvider"] if p in ort.get_available_providers()])
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


def ukuran_piksel(fn):
    try:
        import rasterio
        with rasterio.open(fn) as s:
            if s.crs is not None and s.crs.is_projected:
                return abs(s.transform.a), "geotiff"
            if s.crs is not None:
                return abs(s.transform.a) * 111320, "geotiff-derajat"
    except Exception:
        pass
    return 10.0, "anggapan"


def kecilkan(a, f, mode):
    H, W = (a.shape[0] // f) * f, (a.shape[1] // f) * f
    b = a[:H, :W].reshape(H // f, f, W // f, f)
    if mode == "db":
        lin = np.where(np.isfinite(b) & (b != 0), 10 ** (b / 10), np.nan)
        with np.errstate(all="ignore"):
            m = np.nanmean(lin, axis=(1, 3))
        return np.where(np.isfinite(m) & (m > 0), 10 * np.log10(m), np.nan)
    return b.mean(axis=(1, 3)) >= 0.5


def cari_masker(fn, k):
    b = os.path.splitext(os.path.basename(fn))[0]
    for d in [f"Mask/{k}"]:
        for c in glob.glob(os.path.join(A.data, d, b + "*")):
            return c
    return None


def proses(arg):
    fn, k = arg
    import tifffile
    from scipy import ndimage as ndi
    from fitur_objek import fitur
    from saring import bersihkan
    a = tifffile.imread(fn).astype(np.float32)
    vv = a[..., 1] if a.ndim == 3 and a.shape[-1] == 2 else a[1]
    px0, src = ukuran_piksel(fn); f = max(int(round(PX / px0)), 1)
    db = kecilkan(vv, f, "db") if f > 1 else np.where(vv != 0, vv, np.nan)
    sea = np.isfinite(db) & (db != 0)
    rec = {"file": os.path.basename(fn), "kelas": k, "px_asli": px0, "px_sumber": src}
    if sea.sum() < 1000:
        return rec, []
    mk = unet(db, sea)
    mk2, fl = bersihkan(db, sea, mk, PX)
    rows, lab = fitur(db, sea, mk, PX)
    rec.update(frac_gelap=fl["frac_gelap"], tenang=fl["tenang"], n_objek=len(rows))
    gt = None
    if k == "Oil":
        mf = cari_masker(fn, k)
        if mf is not None:
            g = tifffile.imread(mf); g = (g[..., 0] if g.ndim == 3 else g) > 0
            gt = kecilkan(g.astype(np.float32), f, "mask") if f > 1 else g
            gt = gt[:db.shape[0], :db.shape[1]] & sea
            tp = int((mk2 & gt).sum())
            gl, gn = ndi.label(gt, structure=np.ones((3, 3)))
            besar = [i for i, s in enumerate(ndi.sum(gt, gl, range(1, gn + 1)), 1) if s * PX ** 2 / 1e6 >= 0.1]
            rec.update(masker=os.path.basename(mf), px_gt=int(gt.sum()), px_det=int(mk2.sum()), px_tp=tp,
                       objek_gt=len(besar), objek_gt_kena=int(sum(mk2[gl == i].any() for i in besar)))
    out = []
    for r in rows:
        hit = bool(gt[lab == r["label_id"]].any()) if gt is not None else False
        if k == "Oil" and not hit:
            continue
        out.append({"file": rec["file"], "kelas": k, "label": int(k == "Oil"), **r})
    return rec, out


def boot(df_img, fn, n=1000):
    rng = np.random.default_rng(0); v = []
    idx = np.arange(len(df_img))
    for _ in range(n):
        v.append(fn(df_img.iloc[rng.choice(idx, len(idx))]))
    return [round(float(np.nanpercentile(v, 2.5)), 3), round(float(np.nanpercentile(v, 97.5)), 3)]


if __name__ == "__main__":
    import joblib
    from sklearn.metrics import roc_auc_score
    os.makedirs(A.out, exist_ok=True)
    jobs = [(f, k) for k in KELAS for f in sorted(glob.glob(os.path.join(A.data, "Images", k, "*.tif*")))]
    print({k: sum(j[1] == k for j in jobs) for k in KELAS}, "| pekerja:", A.workers, flush=True)
    recs, rows = [], []
    with ProcessPoolExecutor(A.workers) as ex:
        for i, (rc, o) in enumerate(ex.map(proses, jobs, chunksize=2)):
            recs.append(rc); rows += o
            if i % 25 == 0: print(i, len(rows), flush=True)
    im = pd.DataFrame(recs); ob = pd.DataFrame(rows)
    P = joblib.load(PEMB); thr = P["ambang"]
    ob["p"] = P["model"].predict_proba(ob[P["fitur"]])[:, 1] if len(ob) else []
    ob["lolos"] = ob.p >= thr
    im.to_csv(os.path.join(A.out, "trujillo_gambar.csv"), index=False); ob.to_csv(os.path.join(A.out, "trujillo_objek.csv"), index=False)

    res = {"ambang_pemilah": round(thr, 3), "px_sumber": im.px_sumber.value_counts().to_dict(), "px_asli": im.px_asli.round(2).value_counts().to_dict(),
           "gambar": im.kelas.value_counts().to_dict()}
    oil = im[(im.kelas == "Oil") & im.px_gt.notna()] if "px_gt" in im else im.iloc[:0]
    if len(oil):
        rp = lambda d: d.px_tp.sum() / max(d.px_gt.sum(), 1)
        pp = lambda d: d.px_tp.sum() / max(d.px_det.sum(), 1)
        iou = lambda d: d.px_tp.sum() / max(d.px_gt.sum() + d.px_det.sum() - d.px_tp.sum(), 1)
        ro = lambda d: d.objek_gt_kena.sum() / max(d.objek_gt.sum(), 1)
        res["detektor_oil"] = {"gambar_bermasker": len(oil), "recall_piksel": round(rp(oil), 3), "ci": boot(oil, rp),
                               "presisi_piksel": round(pp(oil), 3), "ci_presisi": boot(oil, pp), "iou": round(iou(oil), 3),
                               "objek_ahli": int(oil.objek_gt.sum()), "recall_objek": round(ro(oil), 3), "ci_objek": boot(oil, ro),
                               "gambar_tanpa_deteksi_minyak": int((oil.px_tp == 0).sum())}
    res["laut_tenang_fraksi_gambar"] = im.groupby("kelas").tenang.mean().round(3).to_dict()
    res["frac_gelap_median"] = im.groupby("kelas").frac_gelap.median().round(3).to_dict()
    if len(ob) and ob.label.nunique() == 2:
        pos, neg = ob.label == 1, ob.label == 0
        res["pemilah"] = {"objek_minyak": int(pos.sum()), "objek_palsu": int(neg.sum()),
                          "auc": round(roc_auc_score(ob.label, ob.p), 3),
                          "recall_minyak_objek": round(float(ob.lolos[pos].mean()), 3),
                          "recall_minyak_luas": round(float(ob.km2[pos & ob.lolos].sum() / ob.km2[pos].sum()), 3),
                          "lookalike_dibuang": round(float(1 - ob.lolos[neg].mean()), 3)}
        # selang kepercayaan AUC & recall per gambar
        rng = np.random.default_rng(0); au, rc_ = [], []
        g = {f: d for f, d in ob.assign(gid=ob.kelas + "/" + ob.file).groupby("gid")}  # nama file berulang antar kelas
        fl = list(g)
        for _ in range(1000):
            d = pd.concat([g[f] for f in rng.choice(fl, len(fl))])
            if d.label.nunique() == 2:
                au.append(roc_auc_score(d.label, d.p)); rc_.append(d.lolos[d.label == 1].mean())
        res["pemilah"]["ci_auc"] = [round(float(np.percentile(au, q)), 3) for q in (2.5, 97.5)]
        res["pemilah"]["ci_recall_minyak"] = [round(float(np.percentile(rc_, q)), 3) for q in (2.5, 97.5)]
    alarm = {}
    for k in ["Lookalike", "No oil"]:
        ii = im[im.kelas == k]; d = ob[ob.kelas == k]
        a0 = d.groupby("file").size().reindex(ii.file, fill_value=0); a1 = d[d.lolos].groupby("file").size().reindex(ii.file, fill_value=0)
        alarm[k] = {"median": [float(a0.median()), float(a1.median())], "rata": [round(a0.mean(), 2), round(a1.mean(), 2)],
                    "gambar_tanpa_alarm": [round(float((a0 == 0).mean()), 3), round(float((a1 == 0).mean()), 3)]}
    res["alarm_per_gambar_sebelum_sesudah"] = alarm
    json.dump(res, open(os.path.join(A.out, "trujillo_ringkasan.json"), "w"), indent=1, default=str)
    print(json.dumps(res, indent=1, default=str))
