"""Tahap 6: uji alarm palsu 2017-2019, orbit relatif 32 (mosaik 2 frame menutup AOI penuh).
Aturan dikunci SEBELUM melihat hasil: skala tetap -32..-17 dB, ambang U-Net 0.45 / DeepLab 0.5, piksel 20 m.
Periode tumpahan 2018-03-31..2018-05-01 dikeluarkan.
Memanggil 02_unduh_citra.py dan 03_inferensi.py per tanggal; melewati tanggal yang sudah selesai.
Keluaran: data/daftar_citra_batch.csv
"""
import csv, os, subprocess, sys, ee

ee.Initialize(project="bledos")
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from situs import BBOX, CRS, ORBIT, ERA5_HOUR, LOOK_AZ, SPILL, YEARS, INNER, DATA, RESULTS, NAME as SITUS, SPILL_REF
AOI = ee.Geometry.Rectangle(BBOX)
STRETCH, SCALE = "fixed:-32:-17", 20
EXCL = SPILL

col = (ee.ImageCollection("COPERNICUS/S1_GRD").filterBounds(AOI).filterDate(*YEARS)
       .filter(ee.Filter.eq("instrumentMode", "IW")).filter(ee.Filter.eq("relativeOrbitNumber_start", ORBIT))
       .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV")))
dates = sorted(set(col.aggregate_array("system:time_start").map(
    lambda t: ee.Date(t).format("YYYY-MM-dd")).getInfo()))
dates = [d for d in dates if not (EXCL[0] <= d <= EXCL[1])]
print(len(dates), "tanggal")
with open(os.path.join(DATA, "daftar_citra_batch.csv"), "w", newline="") as fh:
    csv.writer(fh).writerows([["date"]] + [[d] for d in dates])

# Unduhan GEE paralel (WORKERS tanggal sekaligus; waktu habis menunggu server), inferensi tetap berurutan
# di thread utama agar CPU tidak berebut dan hasil identik dengan versi berurutan.
from concurrent.futures import ThreadPoolExecutor, as_completed
WORKERS = int(os.environ.get("WORKERS", "4"))
py = sys.executable
tif_of = lambda d: os.path.join(DATA, f"s1_vv_db_{d}_{SCALE}m.tif")
todo = [d for d in dates if not os.path.exists(
    os.path.join(RESULTS, f"s1_vv_db_{d}_{SCALE}m_fixed-32_-17", "ringkasan.json"))]
print(len(todo), "belum diproses; unduh paralel x", WORKERS, flush=True)


def unduh(d):
    if not os.path.exists(tif_of(d)):
        subprocess.run([py, os.path.join(HERE, "scripts", "02_unduh_citra.py"), d, str(SCALE)], check=True,
                       stdout=subprocess.DEVNULL)
    return d


done = 0
with ThreadPoolExecutor(WORKERS) as ex:
    futs = {ex.submit(unduh, d): d for d in todo}
    for f in as_completed(futs):
        d = futs[f]; done += 1
        try:
            f.result()
            subprocess.run([py, os.path.join(HERE, "scripts", "03_inferensi.py"), tif_of(d), STRETCH], check=True,
                           stdout=subprocess.DEVNULL)
            print(f"[{done}/{len(todo)}] {d}", flush=True)
        except subprocess.CalledProcessError as e:
            print("  GAGAL", d, e, flush=True)
