"""Tahap 10: laporan satu lintasan untuk responder (contoh keluaran).
Pemakaian: SITUS=karawang python 10_laporan_lintasan.py 2019-07-30 [model]
Membutuhkan hasil tahap 3 (mask) dan tahap 9 (objek_angin.csv) untuk tanggal itu.
Keluaran (RESULTS/laporan_<tgl>/): alarm_<tgl>.geojson, alarm_<tgl>.csv, laporan_<tgl>.pdf, laporan_<tgl>.png
Sesuai council 17 Okt: TIDAK ada skor kepercayaan (tanpa label, skor akan dibaca sebagai peluang);
yang ada keterangan kondisi per alarm.
"""
import json, os, sys, datetime as dt
import numpy as np, pandas as pd, rasterio, ee
from rasterio import features
from rasterio.warp import transform_geom
from scipy import ndimage as ndi
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from situs import BBOX, ORBIT, DATA, RESULTS, NAME as SITUS, LABEL

DATE = sys.argv[1]
MODEL = sys.argv[2] if len(sys.argv) > 2 else "unet_lite"
MIN_KM2, WIND_LOW, COAST_KM = 0.1, 3.0, 1.0      # sama dengan tahap 7 & 9
run = os.path.join(RESULTS, f"s1_vv_db_{DATE}_20m_fixed-32_-17")
od = os.path.join(RESULTS, f"laporan_{DATE}"); os.makedirs(od, exist_ok=True)

# waktu lintasan dari GEE
ee.Initialize(project=os.environ["EE_PROJECT"])  # isi dengan project GEE Anda
d0 = ee.Date(DATE)
t_ms = (ee.ImageCollection("COPERNICUS/S1_GRD").filterBounds(ee.Geometry.Rectangle(BBOX))
        .filterDate(d0, d0.advance(1, "day")).filter(ee.Filter.eq("relativeOrbitNumber_start", ORBIT) if ORBIT else ee.Filter.neq("system:index", ""))
        .aggregate_min("system:time_start").getInfo())
t_utc = dt.datetime.fromtimestamp(t_ms / 1000, dt.timezone.utc)
tz = 7 if (BBOX[0] + BBOX[2]) / 2 < 114.5 else 8   # WIB di barat, WITA di tengah
t_loc = t_utc + dt.timedelta(hours=tz); tz_name = "WIB" if tz == 7 else "WITA"
BLN = "Jan Feb Mar Apr Mei Jun Jul Agu Sep Okt Nov Des".split()
t_loc_s = f"{t_loc.day} {BLN[t_loc.month - 1]} {t_loc.year} pukul {t_loc:%H:%M} {tz_name}"
c = lambda x, nd=1: f"{x:.{nd}f}".replace(".", ",")   # angka gaya Indonesia (koordinat tetap pakai titik)

with rasterio.open(os.path.join(run, "input_u8.tif")) as s:
    u8, tr, crs = s.read(1), s.transform, s.crs
with rasterio.open(os.path.join(run, f"mask_{MODEL}.tif")) as s:
    mk = s.read(1) > 0
with rasterio.open(os.path.join(DATA, f"s1_vv_db_{DATE}_20m.tif")) as s:
    sea = s.read(2) > 0
px_km2 = tr.a ** 2 / 1e6
dist_land_km = ndi.distance_transform_edt(sea) * tr.a / 1e3

lab, n = ndi.label(mk, structure=np.ones((3, 3)))
ob = pd.read_csv(os.path.join(RESULTS, "objek_angin.csv"))
ob = ob[(ob.date == DATE) & (ob.model == MODEL)].set_index("obj")

feats, rows, cyx = [], [], []
sizes = ndi.sum(mk, lab, range(1, n + 1)) * px_km2 if n else []
order = np.argsort(sizes)[::-1] if n else []
aid = 0
for k0 in order:
    k = int(k0) + 1
    if sizes[k0] < MIN_KM2:
        continue
    aid += 1
    o = ob.loc[k] if k in ob.index else None
    reg = lab == k
    geom = next(g for g, v in features.shapes(reg.astype(np.uint8), mask=reg, transform=tr) if v == 1)
    geom_ll = transform_geom(crs, "EPSG:4326", geom)
    near = float(dist_land_km[reg].min())
    ws = float(o.sar_ws_ring) if o is not None and np.isfinite(o.sar_ws_ring) else np.nan
    notes = []
    if not np.isfinite(ws):
        notes.append("angin sekitar tidak terukur")
    elif ws < WIND_LOW:
        notes.append(f"angin sekitar {ws:.1f} m/s (<{WIND_LOW:g}): laut tenang bisa tampak seperti minyak")
    else:
        notes.append(f"angin sekitar {ws:.1f} m/s: cukup untuk menilai bercak gelap")
    if near < COAST_KM:
        notes.append("menempel/dekat pantai (<1 km): cek alur sungai & masker darat")
    r = {"id": aid, "lon": round(float(o.lon), 5) if o is not None else None,
         "lat": round(float(o.lat), 5) if o is not None else None,
         "luas_km2": round(float(sizes[k0]), 2), "angin_sekitar_ms": None if not np.isfinite(ws) else round(ws, 1),
         "angin_era5_ms": None if o is None else round(float(o.era5_ws), 1),
         "jarak_pantai_km": round(near, 1), "keterangan": "; ".join(notes)}
    yy_, xx_ = np.nonzero(reg); cyx.append((int(yy_.mean()), int(xx_.mean())))
    rows.append(r)
    feats.append({"type": "Feature", "geometry": geom_ll, "properties": r})

df = pd.DataFrame(rows)
# urutan cek dari CNN pembeda (tahap 18 v2 + 20: potongan 4 km, regangan -31..-17 dB). Uji: laut terbuka (Karawang) AUC 0,91;
# teluk (Balikpapan) 0,51 -> hanya urutan prioritas, BUKAN penyaring.
_cnn = os.path.join(HERE, "results_pembeda", "csiro_cnn_v2.pt")
if len(df) and os.path.exists(_cnn):
    import torch, torchvision
    from PIL import Image
    _m = torchvision.models.resnet18(); _m.fc = torch.nn.Linear(512, 1)
    _m.load_state_dict(torch.load(_cnn, weights_only=True)); _m.eval()
    with rasterio.open(os.path.join(DATA, f"s1_vv_db_{DATE}_20m.tif")) as s:
        _db = s.read(1).astype(np.float32)
    _db = np.where(np.isfinite(_db) & (_db != 0), _db, np.nan); _db = np.where(np.isnan(_db), np.nanmedian(_db), _db)
    _u = (np.clip((np.pad(_db, 100, mode="reflect") + 31) / 14, 0, 1) * 255).astype(np.uint8)
    _x = [torch.from_numpy((np.asarray(Image.fromarray(_u[y:y + 200, x:x + 200]).resize((224, 224), Image.BILINEAR), np.float32) / 255
                            - 0.449) / 0.226)[None].repeat(3, 1, 1) for y, x in cyx]
    with torch.no_grad():
        df["skor_cnn"] = np.round(torch.sigmoid(_m(torch.stack(_x))[:, 0]).numpy(), 3)
    df["urutan_cek"] = df.skor_cnn.rank(ascending=False, method="first").astype(int)
    for f, (_, r_) in zip(feats, df.iterrows()):
        f["properties"].update(skor_cnn=float(r_.skor_cnn), urutan_cek=int(r_.urutan_cek))
def _save_tables():
    df.to_csv(os.path.join(od, f"alarm_{DATE}.csv"), index=False)
_save_tables()
json.dump({"type": "FeatureCollection", "name": f"alarm_{SITUS}_{DATE}",
           "metadata": {"sensor": "Sentinel-1 IW GRD VV", "lintasan_utc": t_utc.isoformat(), "model": MODEL,
                        "aturan": "skala -32..-17 dB, objek >=0,1 km2, angin CMOD5.N cincin 1-3 km"},
           "features": feats}, open(os.path.join(od, f"alarm_{DATE}.geojson"), "w"), indent=1)

json.dump({"waktu_lokal": t_loc_s, "waktu_utc": f"{t_utc:%Y-%m-%d %H:%M} UTC"},
          open(os.path.join(od, "meta.json"), "w"))

# ---------- halaman laporan A4 lanskap ----------
n_low = int((df.angin_sekitar_ms < WIND_LOW).sum()) if len(df) else 0
_sj = os.path.join(run, f"saring_{MODEL}.json")
TENANG = json.load(open(_sj)).get("tenang", False) if os.path.exists(_sj) else False
fig = plt.figure(figsize=(11.69, 8.27))
gs = fig.add_gridspec(3, 2, width_ratios=[2.1, 1], height_ratios=[0.11, 1, 0.13], hspace=0.08, wspace=0.04,
                      left=0.045, right=0.985, top=0.975, bottom=0.025)
ax_h = fig.add_subplot(gs[0, :]); ax_h.axis("off")
ax_h.text(0, 1, f"Bercak gelap di laut (radar Sentinel-1) — {LABEL}, {t_loc_s}",
          fontsize=15, weight="bold", va="top")
ax_h.text(0, .42, f"{len(df)} bercak gelap ditandai (total {c(df.luas_km2.sum() if len(df) else 0)} km²) · "
          f"{n_low} di antaranya di area berangin lemah (< {WIND_LOW:g} m/s), belum bisa dinilai"
          + (" · LINTASAN DIDOMINASI LAUT TENANG: belum bisa dinilai" if TENANG else "") + "\n"
          f"Satelit lewat {t_loc_s} ({t_utc:%Y-%m-%d %H:%M} UTC). Prototipe riset ADE, data arsip; bukan produk resmi.",
          fontsize=9.5, color="#333", va="top", linespacing=1.4)

gl = gs[1, 0].subgridspec(2, 1, height_ratios=[0.70, 0.30], hspace=0.10)
ax = fig.add_subplot(gl[0])
ax_s = fig.add_subplot(gl[1]); ax_s.axis("off")
# potong ke area sekitar alarm (atau seluruh laut berdata bila tanpa alarm), dengan margin 5 km
ys, xs = np.where(mk if mk.any() else (sea & (u8 > 0)))
pad = int(5000 / tr.a)
y0, y1 = max(ys.min() - pad, 0), min(ys.max() + pad, u8.shape[0]); x0, x1 = max(xs.min() - pad, 0), min(xs.max() + pad, u8.shape[1])
sub = u8[y0:y1, x0:x1]
ext = [(tr.c + tr.a * x0) / 1e3, (tr.c + tr.a * x1) / 1e3, (tr.f + tr.e * y1) / 1e3, (tr.f + tr.e * y0) / 1e3]
ax.imshow(np.where(sub == 0, np.nan, sub), cmap="gray", extent=ext, vmin=0, vmax=255)
ax.set_facecolor("#d9d2c3")
sm = np.ma.masked_where(~mk[y0:y1, x0:x1], np.ones_like(sub))
ax.imshow(sm, cmap="autumn", alpha=.75, extent=ext, interpolation="nearest")
ax.set_xlim(ext[0], ext[1]); ax.set_ylim(ext[2], ext[3])

# garis lintang/bujur (responder membaca koordinat geografis, bukan UTM)
from rasterio.warp import transform as wt
lo0, la0 = wt(crs, "EPSG:4326", [ext[0] * 1e3], [ext[2] * 1e3]); lo1, la1 = wt(crs, "EPSG:4326", [ext[1] * 1e3], [ext[3] * 1e3])
step = 0.1 if (lo1[0] - lo0[0]) < 1.2 else 0.2
xt, xl, yt, yl = [], [], [], []
for lon in np.arange(np.ceil(lo0[0] / step) * step, lo1[0], step):
    xx, yy = wt("EPSG:4326", crs, [lon] * 50, list(np.linspace(la0[0] - .2, la1[0] + .2, 50)))
    ax.plot(np.array(xx) / 1e3, np.array(yy) / 1e3, color="#3a6ea5", lw=.4, alpha=.6)
    xb, _ = wt("EPSG:4326", crs, [lon], [la0[0]]); xt.append(xb[0] / 1e3); xl.append(f"{lon:.1f}°E")
for lat in np.arange(np.ceil(la0[0] / step) * step, la1[0], step):
    xx, yy = wt("EPSG:4326", crs, list(np.linspace(lo0[0] - .2, lo1[0] + .2, 50)), [lat] * 50)
    ax.plot(np.array(xx) / 1e3, np.array(yy) / 1e3, color="#3a6ea5", lw=.4, alpha=.6)
    _, yb = wt("EPSG:4326", crs, [lo0[0]], [lat]); yt.append(yb[0] / 1e3); yl.append(f"{abs(lat):.1f}°{'S' if lat < 0 else 'N'}")
ax.set_xticks(xt, xl, fontsize=7.5); ax.set_yticks(yt, yl, fontsize=7.5)
ax.set_xlim(ext[0], ext[1]); ax.set_ylim(ext[2], ext[3])
# skala 10 km
sx, sy = ext[1] - (ext[1] - ext[0]) * .03 - 10, ext[2] + (ext[3] - ext[2]) * .04
ax.plot([sx, sx + 10], [sy, sy], color="k", lw=3); ax.text(sx + 5, sy + (ext[3] - ext[2]) * .015, "10 km", ha="center", fontsize=7.5,
                                                          bbox=dict(fc="white", alpha=.7, ec="none", pad=1))

# label nomor: geser bergantian supaya tidak bertumpuk
offs = [(8, 8), (-16, 10), (8, -14), (-18, -14), (14, 0), (-22, 0)]
placed = []
for f in feats:
    p = f["properties"]
    E_, N_ = wt("EPSG:4326", crs, [p["lon"]], [p["lat"]]); xy = (E_[0] / 1e3, N_[0] / 1e3)
    near_n = sum(1 for q in placed if abs(q[0] - xy[0]) < 4 and abs(q[1] - xy[1]) < 4)
    placed.append(xy)
    fy = (xy[1] - ext[2]) / (ext[3] - ext[2]); fx = (xy[0] - ext[0]) / (ext[1] - ext[0])
    dx, dy = offs[near_n % len(offs)]
    if fy < .12: dy = abs(dy) + 4          # dekat tepi bawah: label ke atas
    if fy > .9: dy = -abs(dy) - 4
    if fx < .06: dx = abs(dx) + 4
    if fx > .94: dx = -abs(dx) - 4
    col = "#b00020" if (p["angin_sekitar_ms"] or 0) >= WIND_LOW else "#7a5c00"
    ax.annotate(str(p["id"]), xy, xytext=(dx, dy), textcoords="offset points",
                fontsize=8, weight="bold", color="white", ha="center", va="center",
                bbox=dict(boxstyle="round,pad=0.15", fc=col, ec="none"),
                arrowprops=dict(arrowstyle="-", color=col, lw=.6))
legend = ("Cara membaca peta: abu-abu = laut di radar (makin gelap makin licin) · krem = darat · merah = bercak gelap yang ditandai"
          + (" · label cokelat = angin lemah, belum bisa dinilai" if n_low else ""))

# ringkasan: kelompokkan bercak berjarak < GROUP_KM (single-linkage) -> satu kejadian kandidat
GROUP_KM = 5.0
if len(df):
    from scipy.cluster.hierarchy import fcluster, linkage
    EN = np.array([wt("EPSG:4326", crs, [r.lon], [r.lat]) for r in df.itertuples()])[:, :, 0] / 1e3
    df["kelompok"] = fcluster(linkage(EN, "single"), GROUP_KM, "distance") if len(df) > 1 else [1]
    lines = []
    grp = sorted(df.groupby("kelompok"), key=lambda g: -g[1].luas_km2.sum())
    for gi, (_, g) in enumerate(grp[:4], start=1):
        e = EN[g.index]; span = float(np.hypot(*(e.max(0) - e.min(0))))
        sp = f"sebaran ±{span:.0f} km · " if len(g) > 1 else ""
        lines.append(f"Lokasi {gi}: bercak {', '.join(map(str, g.id))} · {c(g.luas_km2.sum())} km² · "
                     f"{sp}pusat {g.lat.mean():.3f}, {g.lon.mean():.3f}")
    if len(grp) > 4: lines.append(f"(+{len(grp) - 4} lokasi kecil lain)")
else:
    lines = ["Tidak ada bercak yang ditandai pada lintasan ini."]
summary = ("Ringkasan (bercak berjarak < 5 km digabung menjadi satu lokasi):\n" + "\n".join(lines) +
           "\nLangkah konfirmasi: (1) cocokkan dengan laporan lapangan/patroli terdekat; (2) cek citra optik atau lintasan berikutnya "
           "(±6–12 hari); (3) dahulukan lokasi terbesar dan yang paling dekat aset; bercak yang menempel garis pantai sering berasal "
           "dari muara sungai, cek dulu.\n" + legend)
import textwrap
summary = "\n".join(textwrap.fill(l, 118, subsequent_indent="   ") for l in summary.split("\n"))
ax_s.set_anchor("N")
ax_s.text(0, 0.93, summary, fontsize=8.2, va="top", linespacing=1.45,
          bbox=dict(fc="#f4f7fb", ec="#c9d6e6", boxstyle="round,pad=0.5"))

ax_t = fig.add_subplot(gs[1, 1]); ax_t.axis("off")
show = df.head(15)
# urutan cek TIDAK ditampilkan (17 Okt 2026): bercak terbesar justru berurutan terakhir (potongan 4 km < bercak). Skor hanya di CSV.
HAS_RANK = False
cell = [[r.id, f"{r.lat:.3f}, {r.lon:.3f}", c(r.luas_km2, 2),
         "-" if pd.isna(r.angin_sekitar_ms) else c(r.angin_sekitar_ms), c(r.jarak_pantai_km)]
        + ([str(r.urutan_cek)] if HAS_RANK else []) for r in show.itertuples()]
tb = ax_t.table(cellText=cell, colLabels=["ID", "Lat, Lon", "Luas\nkm²", "Angin\nm/s", "Ke pantai\nkm"] + (["Urutan\ncek"] if HAS_RANK else []),
                loc="upper center", cellLoc="center",
                colWidths=[.08, .34, .13, .13, .15, .13] if HAS_RANK else [.08, .4, .14, .14, .17])
tb.auto_set_font_size(False); tb.set_fontsize(8); tb.scale(1, 1.35)
for (r_, c_), c in tb.get_celld().items():
    if r_ == 0: c.set_facecolor("#e8e8e8"); c.set_text_props(weight="bold", fontsize=7); c.set_height(c.get_height() * 1.5)
    elif cell[r_ - 1][3] != "-" and float(cell[r_ - 1][3].replace(",", ".")) < WIND_LOW: c.set_facecolor("#fff4d6")
extra = f"(+{len(df) - 15} bercak lain di berkas CSV/GeoJSON)" if len(df) > 15 else ""
fig.canvas.draw()
bb = tb.get_window_extent(fig.canvas.get_renderer()).transformed(ax_t.transAxes.inverted())
ax_t.text(0.5, bb.y0 - 0.02, ("Baris kuning: angin lemah (< 3 m/s), belum bisa dinilai.\n" if n_low else "")
          + "Koordinat = titik tengah bercak (lintang, bujur). " + extra
          + ("\nUrutan cek = mirip minyak menurut model pembeda (1 = cek dulu).\nAndal di laut terbuka; di teluk/perairan tertutup belum andal." if HAS_RANK else ""),
          transform=ax_t.transAxes, ha="center", fontsize=7.5, va="top")

ax_f = fig.add_subplot(gs[2, :]); ax_f.axis("off")
ax_f.text(0, 1, "Batasan: ini daftar bercak gelap di radar, BUKAN konfirmasi tumpahan, dan TIDAK menyatakan sumber atau pihak yang "
          "bertanggung jawab. Belum ada validasi lapangan; diuji pada 14 kejadian arsip (tertangkap jelas di 3, mungkin di 2).\n"
          "Pada hari tanpa kejadian tercatat, tetap muncul median 3–6,5 bercak per lintasan. Satelit lewat tiap ±6–12 hari; bukan pemantauan "
          "real-time. Bercak di area berangin lemah dan yang menempel pantai paling sering keliru.\n"
          "Prototipe riset ADE dari data arsip, bukan produk resmi; jangan disebarkan tanpa konteks. "
          "Mengandung data Copernicus Sentinel-1 (ESA) dan ERA5 (ECMWF), diolah di Google Earth Engine.",
          fontsize=7.6, va="top", color="#222", wrap=True)

_save_tables()   # simpan ulang: CSV kini memuat kolom 'kelompok'
for ext_ in ["pdf", "png"]:
    fig.savefig(os.path.join(od, f"laporan_{DATE}.{ext_}"), dpi=150 if ext_ == "png" else None)
print(df.to_string(index=False)); print("->", od)
