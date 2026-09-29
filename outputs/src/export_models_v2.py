# === 18. Ekspor ONNX semua model v2 (ML + DL) untuk web, verifikasi terhadap hasil notebook, ukur latency ===
# Dijalankan sebagai subprocess (sama seperti export_onnx.py) agar paket onnx/protobuf terisolasi dari kernel notebook.
import json, os, sys, time, shutil, urllib.request
from pathlib import Path
import numpy as np, torch, torch.nn as nn, torch.nn.functional as F
import onnx, onnxruntime as ort, joblib, lightgbm as lgb, onnxmltools
from onnx import compose, helper, TensorProto
from skl2onnx import convert_sklearn
from skl2onnx.common.data_types import FloatTensorType
from onnxmltools.convert.common.data_types import FloatTensorType as MLFloatTensorType
from onnxruntime.quantization import quantize_static, CalibrationDataReader, QuantFormat, QuantType
from onnxruntime.quantization.shape_inference import quant_pre_process
from onnxconverter_common import float16
import segmentation_models_pytorch as smp
sys.path.insert(0, str(Path(__file__).parent))
from sar_features import SARFeatures, FEATURE_NAMES

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "/content/outputs"); V2 = OUT / "v2"
GH = "https://raw.githubusercontent.com/aderizkydarmawan/cayman-oil-spill-sar/main/"
C = np.load(OUT / "cache" / "eval_arrays_v2.npz")
Xcal, Xva, Yva, Xte, Yte = (C[k] for k in ["Xcal", "Xva", "Yva", "Xte", "Yte"])
M2 = json.load(open(V2 / "metrics_v2.json")); INFO, RES = M2["info"], M2["results"]
MEAN, STD, T_DARK = float(C["mean"]), float(C["std"]), int(C["t_dark"])
D = V2 / "onnx"; D.mkdir(exist_ok=True); WEB = V2 / "web_model"; WEB.mkdir(exist_ok=True)
OPSET_ML = 15   # konverter LightGBM (onnxmltools) mendukung sampai opset 15
rng = np.random.default_rng(42); CHECK = np.sort(rng.choice(len(Xte), 100, replace=False))   # subset test untuk cek kesetaraan model pohon (CPU lambat)

def dice_np(p, g):
    tp = (p & g).sum(); d = 2 * tp + (p & ~g).sum() + (~p & g).sum(); return 1.0 if d == 0 else float(2 * tp / d)
def iou_np(p, g):
    tp = (p & g).sum(); d = tp + (p & ~g).sum() + (~p & g).sum(); return 1.0 if d == 0 else float(tp / d)
def session(path, threads=0):
    so = ort.SessionOptions(); so.intra_op_num_threads = threads; return ort.InferenceSession(str(path), so, providers=["CPUExecutionProvider"])
def run_all(sess, X, to_input, out_to_prob):
    name = sess.get_inputs()[0].name
    return np.concatenate([out_to_prob(sess.run(None, {name: to_input(X[i:i + 1])})[0]) for i in range(len(X))])[:, 0]
def latency(path, x, n=20):
    r = {}
    for th, key in [(1, "cpu_latency_ms_1_thread"), (0, "cpu_latency_ms_all_threads")]:
        s = session(path, th); name = s.get_inputs()[0].name
        for _ in range(3): s.run(None, {name: x})
        ts = []
        for _ in range(n): t = time.perf_counter(); s.run(None, {name: x}); ts.append((time.perf_counter() - t) * 1000)
        r[key] = dict(median=round(float(np.median(ts)), 2), p90=round(float(np.percentile(ts, 90)), 2))
    return r
raw = lambda X: X[:, None].astype(np.float32)                       # model ML & dark-spot: input piksel 0-255
norm = lambda X: ((X[:, None].astype(np.float32) / 255.0) - MEAN) / STD   # model DL: input dinormalisasi
sig = lambda z: 0.5 * (1 + np.tanh(0.5 * z))   # sigmoid stabil (tanpa overflow)
REG = {}

# ---------- Dark-spot threshold sebagai graf ONNX kecil ----------
class DarkSpot(nn.Module):
    def forward(self, img):   # sama dengan dark_spot() di notebook: avg_pool 7x7 (padding nol, count_include_pad) lalu < T
        return (F.avg_pool2d(img, 7, 1, 3) < T_DARK).float()
p = D / "dark_spot.onnx"
torch.onnx.export(DarkSpot(), (torch.zeros(1, 1, 256, 256),), str(p), input_names=["image"], output_names=["prob"], opset_version=17, dynamo=False)
pr = run_all(session(p), Xte, raw, lambda o: o) >= 0.5
nb = np.load(OUT / "cache" / "prob_te_dark_spot.npy") >= 0.5
REG["dark_spot"] = dict(file=p.name, input="raw", output="prob", onnx_test_dice=dice_np(pr, Yte.astype(bool)), onnx_test_iou=iou_np(pr, Yte.astype(bool)),
                        pixel_agreement_vs_notebook=float((pr == nb).mean()), checked_on="test 839")
print("dark_spot:", REG["dark_spot"], flush=True)

# ---------- Model ML: graf fitur (PyTorch -> ONNX) + ensemble pohon, digabung jadi satu ONNX ----------
torch.onnx.export(SARFeatures(), (torch.zeros(1, 1, 256, 256),), str(D / "features.onnx"), input_names=["image"], output_names=["features"],
                  opset_version=OPSET_ML, dynamo=False)
FG = onnx.load(str(D / "features.onnx"))
def merge_with_features(tree, path):
    tree.ir_version = FG.ir_version
    for o in tree.opset_import:
        if o.domain in ("", "ai.onnx"): o.version = OPSET_ML
    tree = compose.add_prefix(tree, "t_"); g = tree.graph
    probs = [o.name for o in g.output if "prob" in o.name.lower()][0]
    g.initializer.extend([helper.make_tensor("c_st", TensorProto.INT64, [1], [1]), helper.make_tensor("c_en", TensorProto.INT64, [1], [2]),
                          helper.make_tensor("c_ax", TensorProto.INT64, [1], [1]), helper.make_tensor("c_sh", TensorProto.INT64, [4], [1, 1, 256, 256])])
    g.node.extend([helper.make_node("Slice", [probs, "c_st", "c_en", "c_ax"], ["p1"]), helper.make_node("Reshape", ["p1", "c_sh"], ["prob"])])
    while len(g.output): g.output.pop()
    g.output.append(helper.make_tensor_value_info("prob", TensorProto.FLOAT, [1, 1, 256, 256]))
    m = compose.merge_models(FG, tree, io_map=[("features", g.input[0].name)]); onnx.checker.check_model(m); onnx.save(m, str(path))

rf = joblib.load(V2 / "models" / "random_forest.joblib")
merge_with_features(convert_sklearn(rf, initial_types=[("X", FloatTensorType([None, len(FEATURE_NAMES)]))], options={id(rf): {"zipmap": False}},
                                    target_opset={"": OPSET_ML, "ai.onnx.ml": 3}), D / "random_forest.onnx")
booster = lgb.Booster(model_file=str(V2 / "models" / "lightgbm.txt"))
merge_with_features(onnxmltools.convert_lightgbm(booster, initial_types=[("X", MLFloatTensorType([None, len(FEATURE_NAMES)]))], zipmap=False,
                                                 target_opset=OPSET_ML), D / "lightgbm.onnx")
for k in ["random_forest", "lightgbm"]:
    thr = INFO[k]["threshold"]; t0 = time.time()
    po = run_all(session(D / f"{k}.onnx"), Xte[CHECK], raw, lambda o: o)
    pn = np.load(OUT / "cache" / f"prob_te_{k}.npy")[CHECK].astype(np.float32)
    g = Yte[CHECK].astype(bool)
    REG[k] = dict(file=f"{k}.onnx", input="raw", output="prob", onnx_test_dice=dice_np(po >= thr, g), notebook_test_dice_same_subset=dice_np(pn >= thr, g),
                  pixel_agreement_vs_notebook=float(((po >= thr) == (pn >= thr)).mean()), max_abs_prob_diff=float(np.abs(po - pn).max()),
                  checked_on=f"subset acak 100 citra test (seed 42), {time.time() - t0:.0f}s")
    print(k, REG[k], flush=True)

# ---------- DeepLabV3+ MobileNetV2: FP32 / FP16 / INT8 (QDQ), aturan pemilihan sama dengan U-Net Lite ----------
ck = torch.load(OUT / "checkpoints" / "deeplabv3p_mnv2_best.pt", map_location="cpu", weights_only=False)
dl = smp.DeepLabV3Plus("mobilenet_v2", encoder_weights=None, in_channels=1, classes=1); dl.load_state_dict(ck["state_dict"]); dl.eval()
P = {"fp32": D / "deeplabv3p_mnv2_fp32.onnx", "fp16": D / "deeplabv3p_mnv2_fp16.onnx", "int8": D / "deeplabv3p_mnv2_int8_qdq.onnx"}
torch.onnx.export(dl, (torch.zeros(1, 1, 256, 256),), str(P["fp32"]), input_names=["image"], output_names=["logits"], opset_version=17, dynamo=False)
g32 = onnx.load(str(P["fp32"])); onnx.checker.check_model(g32)
onnx.save(float16.convert_float_to_float16(g32, keep_io_types=True), str(P["fp16"]))
class Calib(CalibrationDataReader):
    def __init__(self, X): self.it = iter([{"image": norm(X[i:i + 1])} for i in range(len(X))])
    def get_next(self): return next(self.it, None)
pre = D / "deeplab_pre.onnx"; quant_pre_process(str(P["fp32"]), str(pre))
quantize_static(str(pre), str(P["int8"]), Calib(Xcal), quant_format=QuantFormat.QDQ, per_channel=True,
                activation_type=QuantType.QUInt8, weight_type=QuantType.QInt8); pre.unlink()
thr = INFO["deeplabv3p_mnv2"]["threshold"]; DLR = {}
with torch.no_grad(): ref = sig(dl(torch.from_numpy(norm(Xte[:4]))).numpy())
for v, path in P.items():
    s = session(path); pv = sig(run_all(s, Xva, norm, lambda o: o)); pt = sig(run_all(s, Xte, norm, lambda o: o))
    pt_b, gte = pt >= thr, Yte.astype(bool)
    tp = (pt_b & gte).sum()
    DLR[v] = dict(file=path.name, size_mb=round(path.stat().st_size / 1e6, 3), val_dice=dice_np(pv >= thr, Yva.astype(bool)),
                  test_dice=dice_np(pt_b, gte), test_iou=iou_np(pt_b, gte), test_precision=float(tp / max(pt_b.sum(), 1)), test_recall=float(tp / max(gte.sum(), 1)),
                  max_abs_prob_diff_vs_torch=float(np.abs(pt[:4] - ref[:, 0]).max()), **latency(path, norm(Xte[:1])))
    print("deeplab", v, {k_: DLR[v][k_] for k_ in ["size_mb", "val_dice", "test_dice", "cpu_latency_ms_1_thread"]}, flush=True)
WEB_VAR = next(v for v in ["int8", "fp16", "fp32"] if DLR["fp32"]["val_dice"] - DLR[v]["val_dice"] <= 0.005)
REG["deeplabv3p_mnv2"] = dict(file=DLR[WEB_VAR]["file"], input="normalized", output="logits", variant=WEB_VAR, onnx_test_dice=DLR[WEB_VAR]["test_dice"],
                              onnx_test_iou=DLR[WEB_VAR]["test_iou"], checked_on="test 839", variants=DLR)
print("DeepLab varian web:", WEB_VAR, flush=True)

# ---------- U-Net Lite: pakai model web INT8 yang sudah ada (tidak dilatih ulang) ----------
p = D / "unet_lite_int8_qdq.onnx"
if not p.exists(): urllib.request.urlretrieve(GH + "web/model/unet_lite_int8_qdq.onnx", p)
EB = json.load(urllib.request.urlopen(GH + "outputs/onnx/edge_benchmark.json"))["results"]["int8"]
REG["unet_lite"] = dict(file=p.name, input="normalized", output="logits", variant="int8", onnx_test_dice=EB["test_dice"], onnx_test_iou=EB["test_iou"], checked_on="test 839 (v1)")

# ---------- Latency CPU semua model web + registry models.json ----------
LABEL = {"dark_spot": ("Dark-spot threshold", "baseline", "Blur 7x7 lalu piksel lebih gelap dari ambang dianggap minyak. Tanpa training."),
         "random_forest": ("Random Forest", "machine_learning", "20 pohon keputusan, klasifikasi per piksel dari 13 fitur buatan tangan."),
         "lightgbm": ("LightGBM", "machine_learning", "100 pohon gradient boosting pada 13 fitur buatan tangan yang sama."),
         "unet_lite": ("U-Net Lite", "deep_learning", "U-Net ringan 1,94 juta parameter, dilatih dari nol."),
         "deeplabv3p_mnv2": ("DeepLabV3+ MobileNetV2", "deep_learning", "Encoder MobileNetV2 pretrained ImageNet (transfer learning) + decoder DeepLabV3+. Model terbaik (default).")}
models = []
for k, (nm, fam, desc) in LABEL.items():
    r = REG[k]; path = D / r["file"]; shutil.copy(path, WEB / path.name)
    x = raw(Xte[:1]) if r["input"] == "raw" else norm(Xte[:1])
    lat = r.get("variants", {}).get(r.get("variant"), {}) if k == "deeplabv3p_mnv2" else latency(path, x)
    t = RES[f"{k}/test"]
    models.append(dict(id=k, name=nm, family=fam, description=desc, file=path.name, size_mb=round(path.stat().st_size / 1e6, 3),
        input=r["input"], output=r["output"], threshold=INFO[k]["threshold"], n_params=INFO[k]["n_params"],
        train_minutes=None if INFO[k]["train_sec"] is None else round(INFO[k]["train_sec"] / 60, 2),
        metrics_test_sentinel=dict(dice=t["dice_global"], iou=t["iou_global"], precision=t["precision_global"], recall=t["recall_global"],
                                   dice_macro=t["dice_macro"], pr_auc=t.get("pr_auc_pixel")),
        metrics_palsar_cross_sensor=dict(dice=RES[f"{k}/palsar_test_cross_sensor"]["dice_global"]),
        onnx_check={kk: vv for kk, vv in r.items() if kk not in ("variants", "file", "input", "output")},
        cpu_latency_ms_colab=dict(one_thread=lat["cpu_latency_ms_1_thread"], all_threads=lat["cpu_latency_ms_all_threads"])))
    print(f"{nm:24s} {models[-1]['size_mb']:7.3f} MB | Dice test {t['dice_global']:.4f} | 1-thread {lat['cpu_latency_ms_1_thread']['median']} ms", flush=True)
REGISTRY = dict(default="deeplabv3p_mnv2", preprocessing=dict(raw="float32 piksel 0-255 (channel R), shape [1,1,256,256]",
                normalized=f"(x/255 - {MEAN:.6f}) / {STD:.6f}, shape [1,1,256,256]", mean=MEAN, std=STD),
                output=dict(prob="probabilitas minyak langsung", logits="prob = sigmoid(logits)"),
                env=dict(onnxruntime=ort.__version__, onnx=onnx.__version__, torch=torch.__version__, cpu_count=os.cpu_count(),
                         latency_protocol="batch 1, 3 warm-up + 20 run, median/p90 sess.run() tanpa pre/post-processing, CPU Colab"),
                models=models)
json.dump(REGISTRY, open(WEB / "models.json", "w"), indent=1, default=float)
json.dump(dict(REG=REG), open(V2 / "export_v2_report.json", "w"), indent=1, default=float)
print("Selesai. File web:", sorted(p.name for p in WEB.iterdir()))
