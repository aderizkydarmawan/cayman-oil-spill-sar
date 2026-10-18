"""Tahap 5: catat setiap folder hasil ke experiments/log.jsonl lewat skrip skill experiment-log."""
import glob, json, os, subprocess, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from situs import DATA, RESULTS, NAME as SITUS
LOG = os.path.expanduser(r"~\.claude\skills\experiment-log\scripts\log_run.py")
for f in sorted(glob.glob(os.path.join(RESULTS, "*", "ringkasan.json"))):
    j = json.load(open(f)); name = os.path.basename(os.path.dirname(f))
    params = {"stretch": j["stretch"], "pixel_m": j["pixel_m"], "tile": 256, "stride": 128,
              "thr_unet": 0.45, "thr_deeplab": 0.5, "speckle": "focalMedian3x3",
              "sea_mask": "JRC GSW1_4 occurrence>50", "gee_project": os.environ.get("EE_PROJECT")}
    res = {"sea_km2": round(j["sea_km2"], 1),
           **{f"{m}_oil_km2": round(v["oil_km2"], 2) for m, v in j["models"].items()}}
    subprocess.run([sys.executable, LOG, "--project", HERE, "--name", f"{SITUS}-{name}",
                    "--cmd", f"python scripts/03_inferensi.py data/{j['tif']} {j['stretch']}",
                    "--params", json.dumps(params), "--data", os.path.join(DATA, j["tif"]),
                    "--results", json.dumps(res),
                    "--notes", f"uji kelayakan GEE {SITUS}; model CAYMAN tanpa latih ulang"], check=True)
