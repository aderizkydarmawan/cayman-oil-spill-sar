# === 11. Ekspor ONNX + FP16 + INT8 (QDQ), verifikasi akurasi & latency, siapkan artefak web ===
# Dijalankan sebagai subprocess agar paket onnx/protobuf terisolasi dari kernel notebook (kagglehub memuat protobuf lama).
import json, os, shutil, sys, time, platform
from pathlib import Path
import numpy as np, torch
import onnx, onnxruntime as ort
from onnxruntime.quantization import quantize_static, CalibrationDataReader, QuantFormat, QuantType
from onnxruntime.quantization.shape_inference import quant_pre_process
from onnxconverter_common import float16
sys.path.insert(0, str(Path(__file__).parent))
from unet_lite import UNetLite

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "/content/outputs")
C = np.load(OUT / "cache" / "eval_arrays.npz")
Xcal, Xva, Yva, Xte, Yte, pred_te_torch = (C[k] for k in ["Xcal", "Xva", "Yva", "Xte", "Yte", "pred_te"])
ck = torch.load(OUT / "checkpoints" / "unet_lite_best.pt", map_location="cpu", weights_only=False)
cfg, MEAN, STD = ck["cfg"], ck["mean"], ck["std"]; S = cfg["img_size"]
THRESH = json.load(open(OUT / "eval" / "metrics.json"))["threshold"]
m = UNetLite(cfg["in_channels"], cfg["base_ch"]); m.load_state_dict(ck["state_dict"]); m.eval()
norm = lambda X: ((X[:, None].astype(np.float32) / 255.0) - MEAN) / STD

D = OUT / "onnx"; D.mkdir(exist_ok=True)
P = {"fp32": D / "unet_lite_fp32.onnx", "fp16": D / "unet_lite_fp16.onnx", "int8": D / "unet_lite_int8_qdq.onnx"}
dummy = torch.zeros(1, 1, S, S)
try:
    torch.onnx.export(m, (dummy,), str(P["fp32"]), input_names=["image"], output_names=["logits"], opset_version=17, dynamo=False)
    EXPORTER = "torch.onnx.export (TorchScript), opset 17"
except Exception as e:
    print("Exporter TorchScript gagal -> dynamo:", repr(e)[:300])
    torch.onnx.export(m, (dummy,), str(P["fp32"]), input_names=["image"], output_names=["logits"], opset_version=18, dynamo=True, external_data=False)
    EXPORTER = "torch.onnx.export (dynamo), opset 18"
g = onnx.load(str(P["fp32"])); onnx.checker.check_model(g)
print("Exporter:", EXPORTER, "| ops:", sorted({n.op_type for n in g.graph.node}), flush=True)

# FP16: bobot & komputasi FP16, I/O tetap float32 (kontrak frontend sama)
onnx.save(float16.convert_float_to_float16(g, keep_io_types=True), str(P["fp16"]))

# INT8 statis QDQ per-channel; kalibrasi 200 citra dari subset TRAIN
class Calib(CalibrationDataReader):
    def __init__(self, X): self.it = iter([{"image": norm(X[i:i + 1])} for i in range(len(X))])
    def get_next(self): return next(self.it, None)
pre = D / "_fp32_pre.onnx"; quant_pre_process(str(P["fp32"]), str(pre))
quantize_static(str(pre), str(P["int8"]), Calib(Xcal), quant_format=QuantFormat.QDQ, per_channel=True,
                activation_type=QuantType.QUInt8, weight_type=QuantType.QInt8)
pre.unlink()

def sess(path, threads=0):
    so = ort.SessionOptions(); so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL; so.intra_op_num_threads = threads
    return ort.InferenceSession(str(path), so, providers=["CPUExecutionProvider"])
def probs(s, X):
    out = np.empty(X.shape, np.float32)
    for i in range(len(X)): out[i] = s.run(None, {"image": norm(X[i:i + 1])})[0][0, 0]
    return 1 / (1 + np.exp(-out))
def gm(pred, gt):
    p, t = pred.astype(bool), gt.astype(bool); tp = np.sum(p & t); fp = np.sum(p & ~t); fn = np.sum(~p & t)
    return dict(dice=float(2 * tp / (2 * tp + fp + fn)), iou=float(tp / (tp + fp + fn)), precision=float(tp / (tp + fp)), recall=float(tp / (tp + fn)))
def lat(s, n=50, warm=5):
    x = norm(Xte[:1])
    for _ in range(warm): s.run(None, {"image": x})
    ts = []
    for _ in range(n): t0 = time.perf_counter(); s.run(None, {"image": x}); ts.append((time.perf_counter() - t0) * 1000)
    return dict(median=round(float(np.median(ts)), 2), p90=round(float(np.percentile(ts, 90)), 2))

with torch.no_grad(): ref = torch.sigmoid(m(torch.from_numpy(norm(Xte[:8])))).numpy()[:, 0]
cpu = next((l.split(":")[1].strip() for l in open("/proc/cpuinfo") if l.startswith("model name")), platform.processor())
R, PT = {}, {}
for name, path in P.items():
    s_all, s_1 = sess(path), sess(path, 1)
    t0 = time.time(); pv = probs(s_all, Xva); PT[name] = pt = probs(s_all, Xte)
    mv, mt = gm(pv >= THRESH, Yva), gm(pt >= THRESH, Yte)
    R[name] = dict(file=path.name, size_mb=round(os.path.getsize(path) / 1e6, 3),
        val_dice=round(mv["dice"], 4), val_iou=round(mv["iou"], 4), test_dice=round(mt["dice"], 4), test_iou=round(mt["iou"], 4),
        test_precision=round(mt["precision"], 4), test_recall=round(mt["recall"], 4),
        max_abs_prob_diff_vs_torch_fp32_cpu=float(np.abs(pt[:8] - ref).max()),
        test_pixel_agreement_vs_torch_gpu_mask=round(float(((pt >= THRESH) == pred_te_torch).mean()), 5),
        cpu_latency_ms_all_threads=lat(s_all), cpu_latency_ms_1_thread=lat(s_1), eval_sec=round(time.time() - t0, 1))
    print(name, R[name], flush=True)

if torch.cuda.is_available():
    mg = m.cuda(); xg = torch.from_numpy(norm(Xte[:1])).cuda()
    for tag, amp in [("torch_gpu_fp32", False), ("torch_gpu_amp_fp16", True)]:
        with torch.no_grad(), torch.autocast("cuda", dtype=torch.float16, enabled=amp):
            for _ in range(10): mg(xg)
            torch.cuda.synchronize(); ts = []
            for _ in range(100): t0 = time.perf_counter(); mg(xg); torch.cuda.synchronize(); ts.append((time.perf_counter() - t0) * 1000)
        R[tag] = dict(latency_ms=dict(median=round(float(np.median(ts)), 2), p90=round(float(np.percentile(ts, 90)), 2)), device=torch.cuda.get_device_name(0))

# Pilih varian web berdasarkan VALIDATION: terkecil yang penurunan val Dice-nya <= 0.005 dari FP32
ok = [k for k in P if R["fp32"]["val_dice"] - R[k]["val_dice"] <= 0.005]
WEB = min(ok, key=lambda k: R[k]["size_mb"])
ENV = dict(onnxruntime=ort.__version__, onnx=onnx.__version__, torch=torch.__version__, exporter=EXPORTER, cpu=cpu, n_cpu=os.cpu_count(),
    latency_protocol="batch=1, input float32 1x1x256x256; ORT CPUExecutionProvider; 5 warm-up + 50 run; median & p90 wall-clock sess.run(); tanpa pre/post-processing. GPU: 10 warm-up + 100 run dengan cuda.synchronize.",
    web_variant_rule="varian terkecil dengan penurunan Dice VALIDATION <= 0.005 terhadap FP32", web_variant=WEB, threshold=THRESH)
json.dump(dict(env=ENV, results=R), open(D / "edge_benchmark.json", "w"), indent=1)
print("ENV:", ENV, flush=True)
np.save(OUT / "cache" / "web_variant_test_probs.npy", PT[WEB].astype(np.float16))
