"""Menyusun slide presentasi CAYMAN (Kasus 38) dari materi laporan v2. Tema terang.
Jalankan: python build_ppt.py  ->  CAYMAN_Kelompok01_Oil_Spill_SAR.pptx"""
from pathlib import Path
import io, json, qrcode
from PIL import Image
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION

HERE = Path(__file__).parent; ROOT = HERE.parent.parent
FIG = ROOT / "docs" / "laporan" / "fig"; ASSET = HERE / "assets"; ASSET.mkdir(exist_ok=True)
OUT = HERE / "CAYMAN_Kelompok01_Oil_Spill_SAR.pptx"
WEB = "https://cayman-kelompok1.vercel.app"

C = dict(bg="FFFFFF", tint="EEF7FB", tint2="E0F2F8", navy="0B2545", teal="0E7490", muted="5B7085", line="D6E6EF",
         oil="7C3AED", pink="DB2777", amber="D97706", boom="F97316", green="059669", red="DC2626", slate="94A3B8")
rgb = lambda h: RGBColor.from_string(h)
FONT_H, FONT_B = "Calibri", "Calibri"

prs = Presentation(); prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
BLANK = prs.slide_layouts[6]
W, H = 13.333, 7.5

def text(sl, x, y, w, h, runs, size=16, color="navy", bold=False, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, font=FONT_B, spacing=None, italic=False):
    """runs: str | list of paragraphs; paragraph = str | list of (text, {opts})"""
    tb = sl.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h)); tf = tb.text_frame
    tf.word_wrap = True; tf.vertical_anchor = anchor
    for m in ("margin_left", "margin_right", "margin_top", "margin_bottom"): setattr(tf, m, 0)
    paras = runs if isinstance(runs, list) else [runs]
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph(); p.alignment = align
        if spacing: p.space_after = Pt(spacing)
        segs = para if isinstance(para, list) else [(para, {})]
        for seg, o in segs:
            r = p.add_run(); r.text = seg; f = r.font
            f.name = o.get("font", font); f.size = Pt(o.get("size", size)); f.bold = o.get("bold", bold); f.italic = o.get("italic", italic)
            f.color.rgb = rgb(C.get(o.get("color", color), o.get("color", color)))
    return tb

def box(sl, x, y, w, h, fill="tint", line=None, radius=0.12, shadow=False, shape=MSO_SHAPE.ROUNDED_RECTANGLE):
    s = sl.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    s.fill.solid(); s.fill.fore_color.rgb = rgb(C.get(fill, fill))
    if line: s.line.color.rgb = rgb(C.get(line, line)); s.line.width = Pt(1)
    else: s.line.fill.background()
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE: s.adjustments[0] = radius / min(w, h)
    if not shadow: s.shadow.inherit = False
    s.text_frame.text = ""
    return s

def pic(sl, path, x, y, w=None, h=None):
    return sl.shapes.add_picture(str(path), Inches(x), Inches(y), Inches(w) if w else None, Inches(h) if h else None)

def pic_fit(sl, path, x, y, w, h):
    iw, ih = Image.open(path).size; r = min(w / iw, h / ih); pw, ph = iw * r, ih * r
    return pic(sl, path, x + (w - pw) / 2, y + (h - ph) / 2, pw, ph)

def header(sl, no, label, title, sub=None):
    sl.background.fill.solid(); sl.background.fill.fore_color.rgb = rgb(C["bg"])
    # motif: tetes minyak berkilau (lingkaran bertumpuk warna sheen) + label seksi
    for i, c in enumerate(["oil", "pink", "amber", "green", "teal"]):
        d = sl.shapes.add_shape(MSO_SHAPE.OVAL, Inches(0.6 + i * 0.13), Inches(0.52), Inches(0.2), Inches(0.2))
        d.fill.solid(); d.fill.fore_color.rgb = rgb(C[c]); d.line.fill.background(); d.shadow.inherit = False
    text(sl, 1.45, 0.49, 6, 0.3, f"{no:02d} · {label.upper()}", size=12, color="teal", bold=True)
    text(sl, 0.6, 0.85, 12.1, 0.75, title, size=32, bold=True, font=FONT_H)
    if sub: text(sl, 0.6, 1.58, 12.1, 0.45, sub, size=15, color="muted")
    text(sl, 11.4, 7.05, 1.4, 0.25, f"CAYMAN · {no + 1}", size=10, color="muted", align=PP_ALIGN.RIGHT)

def card(sl, x, y, w, h, title, body, color="teal", fill="tint", tsize=17, bsize=13.5):
    box(sl, x, y, w, h, fill=fill)
    dot = sl.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x + 0.25), Inches(y + 0.27), Inches(0.22), Inches(0.22))
    dot.fill.solid(); dot.fill.fore_color.rgb = rgb(C[color]); dot.line.fill.background(); dot.shadow.inherit = False
    text(sl, x + 0.6, y + 0.2, w - 0.8, 0.4, title, size=tsize, bold=True)
    text(sl, x + 0.25, y + 0.7, w - 0.5, h - 0.85, body, size=bsize, color="navy", spacing=4)

def stat(sl, x, y, w, big, label, color="navy", size=40):
    text(sl, x, y, w, 0.75, big, size=size, bold=True, color=color)
    text(sl, x, y + 0.78, w, 0.6, label, size=12.5, color="muted")

# ---------------- aset gambar ----------------
hero = ASSET / "hero_art.png"
Image.open(r"C:/Users/ADERIZ~1/AppData/Local/Temp/claude-chrome-screenshots-TdtBmq/screenshot-1790698328561-3.jpg").crop((803, 189, 1254, 571)).save(hero)
qr = ASSET / "qr_web.png"; qrcode.make(WEB, border=1).save(qr)
team = json.load(open(ROOT / "web" / "team.json", encoding="utf-8"))
M = {m["id"]: m for m in json.load(open(ROOT / "web" / "model" / "models.json", encoding="utf-8"))["models"]}
# crop 1 baris pertama & kolom gambar prediksi untuk slide contoh
side = Image.open(FIG / "model_predictions_side_by_side.png")

# ================= 1. JUDUL =================
s = prs.slides.add_slide(BLANK); s.background.fill.solid(); s.background.fill.fore_color.rgb = rgb("F4FAFD")
text(s, 0.7, 0.75, 7.2, 0.35, "TUGAS BESAR DEEP LEARNING · KELOMPOK 1 CAYMAN · KASUS 38", size=12.5, color="teal", bold=True)
text(s, 0.7, 1.25, 7.0, 2.6, [[("Deteksi, Pemetaan, & Perencanaan Respons ", {}), ("Tumpahan Minyak", {"color": "oil"})],
                               [("dari Citra Satelit Sentinel-1 SAR", {})]], size=38, bold=True, font=FONT_H)
text(s, 0.7, 3.95, 6.8, 0.9, "Perbandingan Machine Learning & Deep Learning, inferensi langsung di browser, "
     "dan dukungan keputusan untuk tim HSSE.", size=17, color="muted")
text(s, 0.7, 5.15, 6.8, 1.3, [[("Ketua: ", {"bold": True}), (team[0]["nama"], {})],
                               ", ".join(m["nama"] for m in team[1:]),
                               "S1 Sains Data · UPN \"Veteran\" Jawa Timur"], size=13, color="navy", spacing=3)
pic_fit(s, hero, 7.75, 1.0, 5.0, 5.4)
s.notes_slide.notes_text_frame.text = ("Perkenalan kelompok. Topik: Kasus 38 Marine Oil Spill Detection and Mapping via Satellite SAR. "
    "Kami membandingkan model ML dan DL untuk mendeteksi tumpahan minyak, memetakannya menjadi poligon, dan membantu tim HSSE merencanakan respons.")

# ================= 2. LATAR BELAKANG =================
s = prs.slides.add_slide(BLANK)
header(s, 1, "Latar belakang", "Tumpahan minyak harus dipetakan secepat mungkin",
       "Tim HSSE butuh lokasi, luas, dan arah gerak tumpahan untuk menempatkan oil boom dan skimmer.")
card(s, 0.6, 2.35, 3.9, 3.0, "Sumber risiko migas",
     "Semburan rig lepas pantai, kebocoran pipa bawah laut, kecelakaan tanker, dan buangan kapal. Pengecekan manual lewat patroli udara/laut mahal dan memaparkan personel pada bahaya.", color="red", bsize=15.5)
card(s, 4.72, 2.35, 3.9, 3.0, "Kenapa citra SAR?",
     "Radar Sentinel-1 bekerja siang–malam dan menembus awan. Minyak meredam riak gelombang sehingga tampak gelap. Lebih dari 80% tumpahan di Teluk Jiaozhou terjadi malam hari [Liao 2023].", color="teal", bsize=15.5)
card(s, 8.84, 2.35, 3.9, 3.0, "Tantangannya",
     "Area gelap alami (angin lemah, lapisan biogenik) terlihat mirip minyak (look-alike). Interpretasi manual lambat dan rentan bias.", color="amber", bsize=15.5)
box(s, 0.6, 5.65, 12.14, 1.05, fill="tint2")
text(s, 0.9, 5.8, 11.6, 0.8, [[("Tujuan: ", {"bold": True, "color": "teal"}),
     ("model segmentasi otomatis yang akurat & ringan, berjalan di browser, lalu diperluas menjadi alat bantu respons HSSE (poligon, simulasi penyebaran, oil boom, biaya & risiko).", {})]],
     size=15, anchor=MSO_ANCHOR.MIDDLE)
s.notes_slide.notes_text_frame.text = ("Tumpahan minyak sebagian besar terkait aktivitas migas lepas pantai. Pada pilar HSSE, tim respons butuh lokasi, luas, dan arah gerak "
    "tumpahan secepat mungkin. SAR bekerja siang malam dan menembus awan; minyak tampak gelap karena meredam gelombang kapiler. "
    "Tantangannya adalah look-alike seperti angin lemah dan lapisan biogenik.")

# ================= 3. DATA =================
s = prs.slides.add_slide(BLANK)
header(s, 2, "Data", "Dataset SOS: citra SAR + mask tumpahan", "Deep-SAR Oil Spill (Zhu dkk., 2022) · Kaggle · CC BY 4.0 · patch 256×256 piksel")
stat(s, 0.6, 2.3, 2.9, "8.070", "pasangan citra–mask\n(ALOS PALSAR + Sentinel-1A)")
stat(s, 3.5, 2.3, 2.9, "4.193", "citra Sentinel-1 dipakai\n(sensor utama)", color="teal")
stat(s, 0.6, 3.85, 2.9, "2.850 · 504", "latih · validasi\n(grup near-duplicate tidak dipisah)", size=30)
stat(s, 3.5, 3.85, 2.9, "839", "citra uji, dipakai sekali\n+ 776 PALSAR (lintas sensor)", color="oil")
box(s, 0.6, 5.45, 5.8, 1.1, fill="tint")
text(s, 0.85, 5.58, 5.35, 1.15, [[("Audit sebelum training: ", {"bold": True}), ("pasangan lengkap, 3 kanal identik → 1 kanal, label dibinerkan (≥128), tidak ada duplikat eksak; hanya 9 citra uji mirip citra latih (dampak diuji: Dice −0,0008).", {})]], size=12.5)
pic_fit(s, FIG / "sample_pairs_grid.png", 6.75, 2.2, 6.0, 4.65)
text(s, 6.75, 6.88, 6.0, 0.3, "Contoh citra, mask, dan overlay (merah = minyak) per split dan sensor.", size=11, color="muted", align=PP_ALIGN.CENTER)
s.notes_slide.notes_text_frame.text = ("Dataset SOS berisi 8.070 pasangan citra-mask dari ALOS PALSAR (Teluk Meksiko) dan Sentinel-1A (Teluk Persia). "
    "Kami memakai Sentinel-1 karena sampel terbanyak, label ambigu lebih sedikit, dan datanya terbuka. Split 2.850 latih, 504 validasi, 839 uji. "
    "Audit memastikan tidak ada kebocoran data antar split.")

# ================= 4. PIPELINE =================
s = prs.slides.add_slide(BLANK)
header(s, 3, "Pipeline", "Dari data mentah sampai aplikasi web", "Semua langkah ada di satu notebook Colab (GPU Tesla T4) dan bisa dijalankan ulang.")
pic_fit(s, FIG / "pipeline.png", 0.6, 2.2, 12.14, 4.15)
box(s, 0.6, 6.4, 12.14, 0.5, fill="tint")
text(s, 0.85, 6.43, 11.7, 0.45, "Preprocessing: z-score dari statistik latih · augmentasi 8 rotasi/flip + jitter kecerahan (hanya data latih) · threshold dipilih di validasi, bukan di data uji",
     size=13, color="navy", anchor=MSO_ANCHOR.MIDDLE)
s.notes_slide.notes_text_frame.text = ("Alur: unduh dataset, audit, split, preprocessing, training model ML dan DL, evaluasi, ekspor ONNX dan kuantisasi INT8, "
    "lalu aplikasi web. Threshold selalu dipilih di data validasi agar data uji tetap bersih.")

# ================= 5. MODEL =================
s = prs.slides.add_slide(BLANK)
header(s, 4, "Model", "Dua keluarga model, satu protokol evaluasi", "Split, threshold (dari validasi), dan metrik yang sama untuk semua model.")
box(s, 0.6, 2.25, 5.95, 4.6, fill="FEF3C7")
text(s, 0.9, 2.45, 5.4, 0.4, "MACHINE LEARNING", size=13, bold=True, color="amber")
text(s, 0.9, 2.85, 5.4, 0.5, "Random Forest & LightGBM", size=22, bold=True)
text(s, 0.9, 3.55, 5.4, 3.3, [
    "Klasifikasi per piksel dari 13 fitur buatan tangan:",
    "• intensitas & rata-rata lokal 5/11/21/41 piksel",
    "• simpangan baku lokal (tekstur), gradien Sobel (tepi)",
    "• kontras, selisih vs rata-rata citra, min/max lokal",
    [("Latih 855.000 piksel sampel · RF 20 pohon, LightGBM 100 pohon · ", {}), ("0,24–1,8 MB", {"bold": True})]], size=17, spacing=8)
box(s, 6.79, 2.25, 5.95, 4.6, fill="EDE9FE")
text(s, 7.09, 2.45, 5.4, 0.4, "DEEP LEARNING", size=13, bold=True, color="oil")
text(s, 7.09, 2.85, 5.4, 0.5, "U-Net Lite & DeepLabV3+", size=22, bold=True)
text(s, 7.09, 3.5, 5.4, 3.3, [
    "Belajar fitur sendiri dari citra:",
    "• U-Net Lite: 4 level, 1,94 juta parameter, dari nol",
    "• DeepLabV3+ MobileNetV2: 4,38 juta parameter, pralatih ImageNet (transfer learning)",
    "• Loss 0,5·BCE + 0,5·Dice, AdamW, 40 epoch, GPU T4",
    [("Baseline: ", {"bold": True}), ("dark-spot thresholding (blur 7×7, intensitas < 70)", {})]], size=17, spacing=8)
s.notes_slide.notes_text_frame.text = ("Model ML tidak bisa belajar fitur sendiri, jadi kami membuat 13 fitur per piksel yang menggambarkan kegelapan, tekstur, dan tepi. "
    "Model DL belajar fitur langsung dari citra. DeepLabV3+ memakai encoder MobileNetV2 pralatih ImageNet. Kedua DL dilatih dengan resep yang sama agar adil.")

# ================= 6. EVALUASI =================
s = prs.slides.add_slide(BLANK)
header(s, 5, "Evaluasi", "Deep Learning unggul 5–6 poin Dice atas Machine Learning", "Set uji Sentinel-1 (839 citra), agregasi piksel global. Dice = F1 piksel.")
order = ["dark_spot", "random_forest", "lightgbm", "unet_lite", "deeplabv3p_mnv2"]
names = ["Dark-spot", "Random Forest", "LightGBM", "U-Net Lite", "DeepLabV3+"]
cd = CategoryChartData(); cd.categories = names
cd.add_series("Dice uji Sentinel-1", [round(M[k]["metrics_test_sentinel"]["dice"], 3) for k in order])
cd.add_series("Dice PALSAR (lintas sensor)", [round(M[k]["metrics_palsar_cross_sensor"]["dice"], 3) for k in order])
gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(0.5), Inches(2.15), Inches(7.6), Inches(4.75), cd); ch = gf.chart
ch.has_legend = True; ch.legend.include_in_layout = False; ch.legend.font.size = Pt(12); ch.legend.font.color.rgb = rgb(C["muted"])
from pptx.enum.chart import XL_LEGEND_POSITION; ch.legend.position = XL_LEGEND_POSITION.TOP
va = ch.value_axis; va.minimum_scale, va.maximum_scale = 0.5, 0.9; va.has_major_gridlines = True
va.major_gridlines.format.line.color.rgb = rgb(C["line"]); va.tick_labels.font.size = Pt(11); va.tick_labels.font.color.rgb = rgb(C["muted"]); va.format.line.fill.background()
ca = ch.category_axis; ca.tick_labels.font.size = Pt(12); ca.tick_labels.font.color.rgb = rgb(C["navy"]); ca.format.line.color.rgb = rgb(C["line"])
for ser, col in zip(ch.plots[0].series, ["0E7490", "CBD5E1"]):
    ser.format.fill.solid(); ser.format.fill.fore_color.rgb = rgb(col)
pl = ch.plots[0]; pl.gap_width = 60; pl.overlap = -10; pl.has_data_labels = True
dl = pl.data_labels; dl.number_format = "0.000"; dl.number_format_is_linked = False; dl.position = XL_LABEL_POSITION.OUTSIDE_END; dl.font.size = Pt(10.5); dl.font.color.rgb = rgb(C["navy"])
box(s, 8.45, 2.25, 4.3, 4.6, fill="tint")
text(s, 8.75, 2.45, 3.8, 0.4, "DeepLabV3+ (terbaik)", size=15, bold=True, color="oil")
stat(s, 8.75, 2.85, 1.9, "0,867", "Dice / F1", color="oil", size=34)
stat(s, 10.75, 2.85, 1.9, "0,765", "IoU", size=34)
stat(s, 8.75, 4.1, 1.9, "0,834", "Precision", size=34)
stat(s, 10.75, 4.1, 1.9, "0,902", "Recall", size=34)
text(s, 8.75, 5.4, 3.8, 1.35, "Selisih F1 dengan CBD-Net (state of the art dataset SOS, 87,87%) tinggal 1,1 poin. DL unggul terutama di precision: lebih sedikit look-alike yang ikut ditandai.",
     size=12.5, color="navy")
s.notes_slide.notes_text_frame.text = ("Hasil uji: dark-spot 0,726, Random Forest 0,804, LightGBM 0,806, U-Net Lite 0,855, DeepLabV3+ 0,867. "
    "Model DL unggul 5-6 poin Dice, terutama karena precision lebih tinggi. Pada PALSAR yang tidak pernah dilihat, semua model turun 5-9 poin; "
    "DeepLabV3+ tetap terbaik (0,798). Recall DL sekitar 0,90 yang aman untuk peringatan dini.")

# ================= 7. CONTOH PREDIKSI =================
s = prs.slides.add_slide(BLANK)
header(s, 6, "Analisis hasil", "Apa yang dilihat tiap model?", "Citra uji mudah, tipikal, sulit, dan tanpa minyak (merah = prediksi minyak).")
pic_fit(s, FIG / "model_predictions_side_by_side.png", 0.5, 2.1, 8.3, 5.1)
card(s, 9.1, 2.2, 3.65, 1.5, "Fitur terpenting ML", "minimum & rata-rata lokal 11 px, selisih vs rata-rata citra → kegelapan relatif.", color="amber", bsize=12.5, tsize=15)
card(s, 9.1, 3.85, 3.65, 1.5, "Error utama", "slick sangat kecil, garis gelap tipis tak berlabel, dan batas slick yang melebar.", color="red", bsize=12.5, tsize=15)
card(s, 9.1, 5.5, 3.65, 1.5, "Per citra bervariasi", "kadang ML lebih baik di citra sulit → web punya mode \"bandingkan semua model\".", color="teal", bsize=12.5, tsize=15)
s.notes_slide.notes_text_frame.text = ("Model ML cenderung menandai bercak gelap kecil di laut, DL lebih bersih karena memakai konteks spasial. "
    "Kesalahan utama: slick sangat kecil, garis gelap yang tidak dilabeli, dan batas slick karena label berupa poligon kasar.")

# ================= 8. DEPLOYMENT =================
s = prs.slides.add_slide(BLANK)
header(s, 7, "Deployment · Edge AI", "Semua model berjalan di browser, tanpa server GPU", "ONNX + kuantisasi INT8 → onnxruntime-web (WebAssembly multi-thread) di Vercel.")
steps = [("PyTorch /\nscikit-learn", "tint"), ("ONNX\n(fitur + model)", "tint"), ("INT8 QDQ\n(model DL)", "FEF3C7"), ("Vercel +\nonnxruntime-web", "EDE9FE")]
for i, (t, f) in enumerate(steps):
    x = 0.6 + i * 3.1; box(s, x, 2.25, 2.6, 1.15, fill=f)
    text(s, x, 2.25, 2.6, 1.15, t, size=15, bold=True, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    if i < 3:
        a = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(x + 2.68), Inches(2.67), Inches(0.35), Inches(0.32))
        a.fill.solid(); a.fill.fore_color.rgb = rgb(C["teal"]); a.line.fill.background(); a.shadow.inherit = False
rows = [("Model (varian web)", "Ukuran", "Dice uji", "CPU 1 thread")] + [
    (n, f"{M[k]['size_mb']:.2f} MB".replace(".", ",") if M[k]["size_mb"] >= 0.1 else "<0,1 MB",
     f"{M[k]['metrics_test_sentinel']['dice']:.3f}".replace(".", ","), ("<1 ms" if M[k]["cpu_latency_ms_colab"]["one_thread"]["median"] < 1 else f"{M[k]['cpu_latency_ms_colab']['one_thread']['median']:.0f} ms")) for k, n in zip(order, names)]
tb = s.shapes.add_table(len(rows), 4, Inches(0.6), Inches(3.75), Inches(7.4), Inches(3.0)).table
for j, wd in enumerate([2.9, 1.5, 1.4, 1.6]): tb.columns[j].width = Inches(wd)
for i, row in enumerate(rows):
    for j, v in enumerate(row):
        cl = tb.cell(i, j); cl.text = v; p = cl.text_frame.paragraphs[0]; p.alignment = PP_ALIGN.LEFT if j == 0 else PP_ALIGN.CENTER
        f = p.runs[0].font; f.size = Pt(13); f.name = FONT_B; f.bold = i == 0 or i == len(rows) - 1; f.color.rgb = rgb("FFFFFF" if i == 0 else C["navy"])
        cl.fill.solid(); cl.fill.fore_color.rgb = rgb(C["teal"] if i == 0 else ("EDE9FE" if i == len(rows) - 1 else ("FFFFFF" if i % 2 else C["tint"])))
        cl.margin_left = cl.margin_right = Inches(0.1)
box(s, 8.35, 3.75, 4.4, 3.0, fill="tint")
text(s, 8.65, 3.95, 3.9, 2.7, [
    [("Citra tidak pernah dikirim ke server", {"bold": True})],
    "Inferensi 100% di perangkat pengguna.",
    [("INT8 tanpa penurunan akurasi", {"bold": True})],
    "DeepLabV3+ 17,5 → 4,8 MB, Dice tetap 0,867.",
    [("±130 ms per citra di browser", {"bold": True})],
    "Uji di Chrome laptop, WASM multi-thread."], size=13.5, spacing=3)
s.notes_slide.notes_text_frame.text = ("Model diekspor ke ONNX. Model DL dikuantisasi INT8 statis; varian web dipilih bila penurunan Dice validasi <= 0,005. "
    "Model ML diekspor sebagai satu graf (fitur + pohon). Web statis di Vercel menjalankan model dengan onnxruntime-web, jadi citra tidak dikirim ke server. "
    "Model ML paling kecil tetapi paling lambat karena 65.536 piksel harus melewati semua pohon.")

# ================= 9. RESPONS HSSE =================
s = prs.slides.add_slide(BLANK)
header(s, 8, "Respons HSSE", "Dari deteksi ke rencana respons: poligon, arah, dan oil boom", "Simulasi skenario (what-if) dengan angin & arus yang diisi pengguna.")
pic_fit(s, FIG / "web_v2_sim.jpg", 0.5, 2.1, 7.4, 4.9)
card(s, 8.2, 2.15, 4.55, 1.45, "Drift (arah & kecepatan)", "3% kecepatan angin + 100% arus permukaan (aturan praktis model NOAA GNOME).", color="teal", bsize=12.5, tsize=15)
card(s, 8.2, 3.75, 4.55, 1.45, "Penyebaran", "Persamaan Fay (gravitasi-viskos) + difusi turbulen Okubo; volume = luas × ketebalan Bonn Agreement.", color="oil", bsize=12.5, tsize=15)
box(s, 8.2, 5.35, 4.55, 1.65, fill="FFEDD5")
text(s, 8.45, 5.45, 4.1, 0.35, "Contoh: sampel uji tipikal, 10 m/piksel", size=12.5, bold=True, color="boom")
text(s, 8.45, 5.82, 4.1, 1.15, "Angin 8 m/s, arus 0,3 m/s → slick bergerak 0,21 m/s ke tenggara, melebar ±0,10 km²/jam. Saat tim tiba (+3 jam) perlu oil boom ±16,4 km.",
     size=12.5, color="navy")
s.notes_slide.notes_text_frame.text = ("Mask diubah menjadi poligon per slick dengan luas dan keliling, bisa diunduh GeoJSON. Simulasi memproyeksikan poligon: "
    "drift 3% angin + arus, penyebaran Fay plus difusi Okubo. Kebutuhan oil boom = 1,3 x keliling convex hull saat tim tiba; ada peringatan bila arus > 0,7 knot. "
    "Batasan: dataset tidak punya koordinat dan waktu, jadi simulasi adalah skenario, bukan ramalan.")

# ================= 10. BIAYA & RISIKO =================
s = prs.slides.add_slide(BLANK)
header(s, 9, "Nilai bisnis", "Efisiensi biaya & penurunan risiko personel", "Kalkulator di web · angka default adalah asumsi ilustratif yang bisa diganti data perusahaan.")
stat(s, 0.6, 2.25, 3.9, "−75%", "biaya pemantauan per bulan\nRp2,16 M → Rp0,54 M (asumsi)", color="green", size=48)
stat(s, 0.6, 3.85, 3.9, "192 → 48", "jam paparan personel di lapangan\nper bulan (−75%)", color="teal", size=40)
stat(s, 0.6, 5.4, 3.9, "68 → 41", "total skor risiko HSSE (L × S)\nturun 40%", color="oil", size=40)
risk = [("Bahaya", "Sebelum", "Sesudah CV"),
        ("Paparan uap hidrokarbon (VOC, H₂S)", "12 · Tinggi", "4 · Rendah"),
        ("Kecelakaan penerbangan pengintaian", "10 · Tinggi", "5 · Sedang"),
        ("Insiden kapal patroli", "12 · Tinggi", "4 · Rendah"),
        ("Kebakaran/ledakan dekat minyak segar", "10 · Tinggi", "5 · Sedang"),
        ("Kelelahan kru (patroli panjang & malam)", "12 · Tinggi", "6 · Sedang"),
        ("Tumpahan terlambat diketahui", "12 · Tinggi", "8 · Sedang"),
        ("Risiko baru: salah deteksi / terlewat", "–", "9 · Sedang")]
lvl = {"Tinggi": "FED7AA", "Sedang": "FEF3C7", "Rendah": "D1FAE5"}
tb = s.shapes.add_table(len(risk), 3, Inches(4.75), Inches(2.25), Inches(8.0), Inches(4.2)).table
for j, wd in enumerate([4.6, 1.7, 1.7]): tb.columns[j].width = Inches(wd)
for i, row in enumerate(risk):
    for j, v in enumerate(row):
        cl = tb.cell(i, j); cl.text = v; p = cl.text_frame.paragraphs[0]; p.alignment = PP_ALIGN.LEFT if j == 0 else PP_ALIGN.CENTER
        f = p.runs[0].font; f.size = Pt(12.5); f.name = FONT_B; f.bold = i == 0; f.italic = i == len(risk) - 1 and j == 0
        f.color.rgb = rgb("FFFFFF" if i == 0 else C["navy"]); cl.fill.solid()
        cl.fill.fore_color.rgb = rgb(C["navy"] if i == 0 else (lvl.get(v.split(" · ")[-1], "FFFFFF") if j else ("FFFFFF" if i % 2 else C["tint"])))
text(s, 4.75, 6.6, 8.0, 0.45, "Kemungkinan (L) turun karena jam paparan berkurang; keparahan (S) tetap. CV tidak menggantikan tim lapangan: verifikasi & pemasangan boom tetap oleh manusia.",
     size=11.5, color="muted")
s.notes_slide.notes_text_frame.text = ("Asumsi ilustratif: 12 sortie per bulan x 4 jam x Rp45 juta per jam, dibanding 10 citra x 0,5 jam analis, dan 25% sortie tetap untuk konfirmasi. "
    "Biaya turun 75%. Jam paparan personel 192 menjadi 48 jam, sehingga kemungkinan bahaya berbasis paparan turun dua tingkat. "
    "Risiko baru berupa salah deteksi dicatat dan dikendalikan dengan verifikasi analis. Angka perlu diganti data kontrak nyata.")

# ================= 11. KESIMPULAN =================
s = prs.slides.add_slide(BLANK)
header(s, 10, "Kesimpulan", "Ringkasan & pengembangan berikutnya")
card(s, 0.6, 1.9, 6.0, 4.3, "Kesimpulan", [
    "• DL > ML pada protokol yang sama: DeepLabV3+ Dice 0,867, U-Net Lite 0,855, RF & LightGBM ±0,805, baseline 0,726.",
    "• Transfer learning (ImageNet) membantu, termasuk lintas sensor (PALSAR 0,798).",
    "• Kelima model berjalan di browser; DL INT8 tanpa penurunan akurasi.",
    "• Web menjadi alat bantu HSSE: poligon + GeoJSON, simulasi drift & oil boom, biaya & risiko."], color="green", bsize=18)
card(s, 6.75, 1.9, 6.0, 4.3, "Saran pengembangan", [
    "• Tambah kelas look-alike dan data multi-sensor.",
    "• Proses citra Sentinel-1 penuh dengan tiling & georeferensi (koordinat nyata).",
    "• Hubungkan simulasi dengan data angin & arus operasional, validasi dengan citra berurutan.",
    "• Uji beberapa seed; pilot di perairan Indonesia bersama tim HSSE."], color="amber", bsize=18)
s.notes_slide.notes_text_frame.text = "Rangkum hasil utama lalu pindah ke demo langsung di web."

# ================= 12. DEMO =================
s = prs.slides.add_slide(BLANK); s.background.fill.solid(); s.background.fill.fore_color.rgb = rgb("F4FAFD")
text(s, 0.7, 0.7, 8, 0.35, "11 · DEMO LANGSUNG", size=12.5, color="teal", bold=True)
text(s, 0.7, 1.1, 8.2, 1.0, "Mari coba di web CAYMAN", size=40, bold=True, font=FONT_H)
text(s, 0.7, 2.1, 8.0, 0.5, WEB.replace("https://", ""), size=24, bold=True, color="oil")
text(s, 0.7, 2.85, 7.8, 2.2, ["1. Pilih model & sampel → lihat poligon per slick",
                               "2. Bandingkan semua model pada citra yang sama",
                               "3. Simulasi angin & arus → arah, laju penyebaran, oil boom",
                               "4. Kalkulator biaya & matriks risiko HSSE"], size=17, spacing=6)
box(s, 9.55, 0.75, 3.1, 3.1, fill="FFFFFF", line="line"); pic(s, qr, 9.75, 0.95, 2.7, 2.7)
text(s, 9.55, 3.95, 3.1, 0.3, "Pindai untuk membuka web", size=11.5, color="muted", align=PP_ALIGN.CENTER)
text(s, 0.7, 5.05, 6, 0.3, "TIM CAYMAN", size=12, color="teal", bold=True)
for i, m in enumerate(team):
    x = 0.7 + i * 2.05; p_ = ROOT / "web" / m["foto"]
    im = Image.open(p_).convert("RGB"); sq = min(im.size); im = im.crop(((im.width - sq) // 2, 0, (im.width - sq) // 2 + sq, sq)).resize((300, 300))
    from PIL import ImageDraw
    mask = Image.new("L", (300, 300), 0); ImageDraw.Draw(mask).ellipse((0, 0, 299, 299), fill=255)
    out = Image.new("RGBA", (300, 300)); out.paste(im, (0, 0), mask); fp = ASSET / f"team_{i}.png"; out.save(fp)
    pic(s, fp, x + 0.45, 5.45, 0.9, 0.9)
    text(s, x, 6.4, 1.8, 0.6, [[(m["nama"].split(" ")[0] + " " + (m["nama"].split(" ")[1] if len(m["nama"].split(" ")) > 1 else ""), {"bold": True})],
                               m["peran"].split(" (")[0].replace(" Specialist", "")], size=10.5, align=PP_ALIGN.CENTER)
s.notes_slide.notes_text_frame.text = ("Buka cayman-kelompok1.vercel.app. Demo: klik Sampel 2 (DeepLabV3+), tunjukkan poligon dan daftar slick; klik Bandingkan semua model; "
    "isi resolusi 10 m, lalu di Simulasi klik preset Sedang dan Putar; tunjukkan kebutuhan oil boom; terakhir kalkulator biaya & matriks risiko. "
    "Buka web sebelum presentasi agar model sudah terunduh (±20 MB).")

prs.save(OUT); print("saved", OUT)
