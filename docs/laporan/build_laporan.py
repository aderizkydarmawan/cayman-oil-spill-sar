"""Menyusun laporan ilmiah Kelompok 1 CAYMAN (Kasus 38) sebagai .docx.
Format sesuai panduan: single column, A4, spasi 1.15, margin 2.5 cm.
Semua angka berasal dari outputs/ (hasil eksekusi nyata di Colab & uji browser)."""
import re
from pathlib import Path
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

HERE = Path(__file__).parent
FIG = HERE / "fig"
OUT = HERE / "Tubes_DL_Kelompok01_Oil_Spill_SAR.docx"
FONT = "Times New Roman"

doc = Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
    setattr(sec, side, Cm(2.5))

normal = doc.styles["Normal"]
normal.font.name = FONT
normal.font.size = Pt(11)
normal.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
pf = normal.paragraph_format
pf.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
pf.line_spacing = 1.15
pf.space_after = Pt(4)
pf.space_before = Pt(0)

for name, size in (("Heading 1", 12.5), ("Heading 2", 11.5)):
    st = doc.styles[name]
    st.font.name, st.font.size, st.font.bold = FONT, Pt(size), True
    st.font.color.rgb = RGBColor(0, 0, 0)
    rf = st.element.rPr.rFonts
    for a in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
        rf.attrib.pop(qn(a), None)
    for a in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rf.set(qn(a), FONT)
    st.paragraph_format.space_before = Pt(10 if name == "Heading 1" else 6)
    st.paragraph_format.space_after = Pt(4)
    st.paragraph_format.keep_with_next = True


def add_runs(par, text, size=None, italic_all=False):
    """Markup sederhana: **tebal**, *miring*."""
    for tok in re.split(r"(\*\*[^*]+\*\*|\*[^*]+\*)", text):
        if not tok:
            continue
        if tok.startswith("**"):
            r = par.add_run(tok[2:-2]); r.bold = True
        elif tok.startswith("*"):
            r = par.add_run(tok[1:-1]); r.italic = True
        else:
            r = par.add_run(tok)
        if italic_all:
            r.italic = True
        if size:
            r.font.size = Pt(size)
    return par


def P(text, align="justify", size=None, italic=False, space_after=None, indent=True):
    p = doc.add_paragraph()
    p.alignment = {"justify": WD_ALIGN_PARAGRAPH.JUSTIFY, "center": WD_ALIGN_PARAGRAPH.CENTER, "left": WD_ALIGN_PARAGRAPH.LEFT}[align]
    if indent and align == "justify":
        p.paragraph_format.first_line_indent = Cm(0.75)
    if space_after is not None:
        p.paragraph_format.space_after = Pt(space_after)
    return add_runs(p, text, size, italic)


def B(text, level=0):
    p = doc.add_paragraph(style="List Bullet")
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.left_indent = Cm(0.9 + 0.6 * level)
    p.paragraph_format.space_after = Pt(2)
    return add_runs(p, text)


def H1(t): doc.add_heading(t, level=1)
def H2(t): doc.add_heading(t, level=2)


def caption(text, before=False):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(8 if not before else 3)
    p.paragraph_format.space_before = Pt(3 if not before else 6)
    if before:
        p.paragraph_format.keep_with_next = True
    label, rest = text.split(".", 1)
    r = p.add_run(label + "."); r.bold = True; r.font.size = Pt(9.5)
    add_runs(p, rest, size=9.5)


def figure(path, width_cm, text):
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.keep_with_next = True
    p.paragraph_format.space_after = Pt(0)
    p.add_run().add_picture(str(path), width=Cm(width_cm))
    caption(text)


def set_cell_border(cell, **kw):
    tcPr = cell._tc.get_or_add_tcPr()
    borders = tcPr.find(qn("w:tcBorders"))
    if borders is None:
        borders = OxmlElement("w:tcBorders"); tcPr.append(borders)
    for edge, val in kw.items():
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), val.get("val", "single")); el.set(qn("w:sz"), str(val.get("sz", 6)))
        el.set(qn("w:color"), val.get("color", "000000")); el.set(qn("w:space"), "0")
        borders.append(el)


def shade(cell, hex_fill):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd"); shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), hex_fill)
    tcPr.append(shd)


def table(title, header, rows, widths_cm, size=9, bold_rows=(), note=None, align_first_left=True):
    caption(title, before=True)
    t = doc.add_table(rows=1 + len(rows), cols=len(header))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    for i, row in enumerate([header] + rows):
        for j, val in enumerate(row):
            c = t.cell(i, j); c.width = Cm(widths_cm[j])
            c.paragraphs[0].paragraph_format.space_after = Pt(1)
            c.paragraphs[0].paragraph_format.line_spacing = 1.0
            c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.LEFT if (j == 0 and align_first_left) else WD_ALIGN_PARAGRAPH.CENTER
            add_runs(c.paragraphs[0], str(val), size=size)
            if i == 0 or i - 1 in bold_rows:
                for r in c.paragraphs[0].runs: r.bold = True
            if i == 0:
                shade(c, "E7EEF7")
                set_cell_border(c, top={"sz": 10}, bottom={"sz": 6})
            if i == len(rows):
                set_cell_border(c, bottom={"sz": 10})
            if i - 1 in bold_rows:
                shade(c, "F2F7EC")
            if i < len(rows):  # jaga tabel tetap utuh satu halaman
                c.paragraphs[0].paragraph_format.keep_with_next = True
        trPr = t.rows[i]._tr.get_or_add_trPr(); cs = OxmlElement("w:cantSplit"); trPr.append(cs)
    if note:
        p = doc.add_paragraph(); p.paragraph_format.space_after = Pt(8)
        add_runs(p, note, size=8.5)
    else:
        doc.add_paragraph().paragraph_format.space_after = Pt(2)


def page_number_footer(section):
    p = section.footer.paragraphs[0]; p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run()
    for kind, text in (("begin", None), (None, "PAGE"), ("end", None)):
        if kind:
            el = OxmlElement("w:fldChar"); el.set(qn("w:fldCharType"), kind); r._r.append(el)
        else:
            el = OxmlElement("w:instrText"); el.set(qn("xml:space"), "preserve"); el.text = text; r._r.append(el)
    r.font.size = Pt(9)
    hp = section.header.paragraphs[0]; hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    hr = hp.add_run("Tugas Besar Deep Learning · Kelompok 1 CAYMAN · Kasus 38"); hr.font.size = Pt(8.5); hr.italic = True


page_number_footer(sec)

# ============================== JUDUL & IDENTITAS ==============================
tp = doc.add_paragraph(); tp.alignment = WD_ALIGN_PARAGRAPH.CENTER; tp.paragraph_format.space_after = Pt(6)
r = tp.add_run("Deteksi dan Pemetaan Tumpahan Minyak pada Citra Sentinel-1 SAR Menggunakan U-Net Ringan Terkuantisasi INT8 untuk Inferensi Edge di Browser")
r.bold = True; r.font.size = Pt(15)

P("Kelompok 1 — **CAYMAN** · Kasus 38: *Marine Oil Spill Detection and Mapping via Satellite SAR*", align="center", size=10.5, space_after=2)
P("Ade Rizky Darmawan (23083010080, Ketua) · Arkananta Daniswara Handoyo (23083010059) · Muhammad Arsyad Alzam (23083010082) · "
  "Choirul Amin (22083010050) · Hana Titania Sastrian (23083010056) · Zaydan Arief Athallah (23083010063)", align="center", size=10, space_after=2)
P("Program Studi S1 Sains Data, UPN \"Veteran\" Jawa Timur · Semester Ganjil 2026/2027", align="center", size=10, italic=True, space_after=2)
P("Kode & dokumentasi: github.com/aderizkydarmawan/cayman-oil-spill-sar · Aplikasi web: cayman-kelompok1.vercel.app", align="center", size=9.5, space_after=10)

# ================================== ABSTRAK ===================================
ab = doc.add_paragraph(); ab.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
ab.paragraph_format.left_indent = Cm(0.8); ab.paragraph_format.right_indent = Cm(0.8)
rr = ab.add_run("Abstrak — "); rr.bold = True; rr.font.size = Pt(10)
add_runs(ab, (
    "Tumpahan minyak dari fasilitas migas lepas pantai, pipa bawah laut, dan kapal tanker harus dipetakan secepat mungkin agar respons "
    "HSSE tepat sasaran. Penelitian ini membangun model segmentasi semantik biner berbasis U-Net ringan (1,94 juta parameter) untuk "
    "memetakan area tumpahan minyak pada citra Sentinel-1 SAR dari dataset SOS (2.850 patch latih, 504 validasi, 839 uji). Audit data "
    "dilakukan sebelum pelatihan, meliputi pasangan citra–mask, nilai label, dan duplikat termasuk hasil rotasi/flip. Model dilatih di GPU Tesla T4 "
    "selama 10 menit dengan loss BCE+Dice, threshold dipilih pada data validasi, dan test set hanya dipakai sekali. Pada 839 citra uji, model "
    "mencapai Dice/F1 0,855, IoU 0,746, precision 0,806, recall 0,910, dan PR-AUC 0,936, jauh di atas baseline dark-spot thresholding "
    "(Dice 0,726). Kuantisasi INT8 statis (QDQ) memperkecil model dari 7,77 MB menjadi 2,01 MB dengan penurunan Dice hanya 0,0002, dan model "
    "berjalan sepenuhnya di browser melalui onnxruntime-web dengan latensi 65–74 ms per patch 256×256 pada laptop uji. Dibandingkan CBD-Net pada "
    "subset Sentinel-1 dataset yang sama (F1 87,87%), F1 model ini 2,4 poin lebih rendah, tetapi model jauh lebih ringan dan dapat "
    "dioperasikan tanpa server GPU."), size=10)
kw = doc.add_paragraph(); kw.paragraph_format.left_indent = Cm(0.8); kw.paragraph_format.right_indent = Cm(0.8); kw.paragraph_format.space_after = Pt(8)
r = kw.add_run("Kata kunci: "); r.bold = True; r.font.size = Pt(10)
add_runs(kw, "oil spill, SAR, Sentinel-1, segmentasi semantik, U-Net, kuantisasi INT8, edge AI, onnxruntime-web, HSSE.", size=10, italic_all=True)

# ================================ PENDAHULUAN =================================
H1("1. Pendahuluan")
P("Tumpahan minyak adalah salah satu ancaman terbesar bagi ekosistem laut, dan sebagian besar terkait aktivitas industri migas lepas "
  "pantai: semburan dari rig pengeboran, kecelakaan tanker, hingga buangan rutin kapal [6]. Pada pilar **HSSE** (*Health, Safety, Security "
  "and Environment*), tim respons membutuhkan informasi lokasi dan luas tumpahan secepat mungkin untuk menentukan penempatan *boom*, "
  "*skimmer*, dan kapal penanggulangan [1]. Kegagalan mendeteksi dini berisiko memperluas pencemaran pesisir dan berujung pada sanksi "
  "maupun penghentian izin operasi fasilitas.")
P("Radar apertur sintetis (SAR) menjadi sensor utama pemantauan tumpahan minyak karena bekerja siang–malam dan menembus awan. Lapisan "
  "minyak meredam gelombang kapiler sehingga tampak sebagai area gelap pada citra SAR [1]. Kemampuan malam hari penting: Liao dkk. "
  "menemukan lebih dari 80% kejadian tumpahan di Teluk Jiaozhou terjadi pada malam hari, terutama dari buangan ilegal kapal [8]. Tantangan "
  "utamanya adalah fenomena *look-alike* (angin lemah, lapisan biogenik) yang juga tampak gelap [2], [4], [7], serta interpretasi visual "
  "manual yang lambat dan rentan bias [7].")
P("Tabel 1 merangkum penelitian lima tahun terakhir yang menjadi rujukan. Angka antarpenelitian umumnya **tidak dapat dibandingkan "
  "langsung** karena dataset, jumlah kelas, dan protokol evaluasinya berbeda; pembanding yang setara hanya Zhu dkk. [3], yang "
  "memperkenalkan dataset SOS yang juga kami gunakan.")
table("Tabel 1. Ringkasan penelitian rujukan (state of the art).",
      ["Rujukan", "Data", "Metode", "Hasil utama (sesuai paper)"],
      [["Zhu dkk., 2022 [3]", "SOS: ALOS PALSAR & Sentinel-1A", "CBD-Net (multiskala, scSE, supervisi tepi)", "Sentinel-1: mIoU 83,42%, F1 87,87%"],
       ["Shaban dkk., 2021 [5]", "SAR, dataset tidak seimbang", "CNN 23 lapis + U-Net 5 tahap", "Dice 80%, precision 84%"],
       ["Hasimoto-Beltran dkk., 2023 [6]", "16 citra ENVISAT-ASAR", "M-DNN multi-kanal (U-Net + ResNet)", "F1 hingga 98,24% (dataset sendiri)"],
       ["Li dkk., 2023 [7]", "Sentinel-1", "Algoritma DL *self-evolving*", "F1 0,8423 → 0,8896 (21 siklus)"],
       ["Liao dkk., 2023 [8]", "35 citra Sentinel-1 PolSAR", "DeepLabv3+ + fitur polarimetrik", "OA 0,9812; MIoU 0,9599"],
       ["Das dkk., 2024 [9]", "SAR, 5 kelas", "U-Net multi-backbone (EfficientNet-B3)", "mIoU 76,53%; IoU minyak 62,08%"],
       ["Petalas dkk., 2025 [10]", "Sentinel-1, Laut Aegea", "U-Net operasional + model dispersi", "IoU kelas minyak 0,30"]],
      [3.4, 3.6, 4.4, 4.6], size=8.5)
P("Sebagian besar penelitian tersebut berfokus pada akurasi dengan model berat yang dijalankan di GPU; aspek efisiensi dan penyebaran "
  "ke perangkat pengguna jarang dibahas. Kontribusi proyek ini adalah: (1) *pipeline* yang diaudit, termasuk pemeriksaan kebocoran antar "
  "split; (2) U-Net ringan yang dikuantisasi INT8 menjadi 2 MB dengan penurunan akurasi yang dapat diabaikan; (3) aplikasi web dengan "
  "inferensi sepenuhnya di sisi klien, tombol *Try Sample Data*, dan estimasi luas tumpahan (km²); serta (4) perbandingan jujur terhadap "
  "tolok ukur SOS [3].")

# ================================= METODOLOGI =================================
H1("2. Metodologi")
H2("2.1 Dataset dan audit data")
P("Dataset yang digunakan adalah *Deep-SAR Oil Spill* (SOS) [3], diunduh dari Kaggle melalui pustaka kagglehub [13] (lisensi CC BY 4.0 "
  "sesuai halaman sumber). SOS berisi 8.070 pasangan citra–mask PNG 256×256 piksel dari dua sensor: ALOS PALSAR (Teluk Meksiko; 3.101 latih "
  "/ 776 uji) dan Sentinel-1A polarisasi VV (Teluk Persia; 3.354 latih / 839 uji). Sebelum pelatihan dilakukan audit menyeluruh dengan temuan berikut:")
B("Semua 8.070 pasangan cocok berdasarkan nama berkas; tidak ada citra tanpa mask, dimensi tidak cocok, NaN/Inf, maupun citra konstan.")
B("Citra tersimpan sebagai RGB, tetapi ketiga kanalnya identik (100%), sehingga model menggunakan **1 kanal**.")
B("Label uji murni bernilai 0/255, sedangkan label latih memiliki 2,2–2,5% piksel bernilai antara (pada 44–53% berkas). Label "
  "dibinerkan dengan aturan piksel ≥128 = minyak.")
B("Tidak ada duplikat eksak (md5) di dalam maupun antar split. Pemeriksaan *near-duplicate* dengan *average hash* terhadap 8 transformasi "
  "rotasi/flip menemukan 9 citra uji per sensor yang mirip citra latih; pemeriksaan visual menunjukkan tekstur speckle-nya berbeda "
  "(bukan salinan). Dampaknya diuji pada analisis sensitivitas (Subbab 3.2).")
B("Zhu dkk. menyebutkan bahwa augmentasi (*cropping*, rotasi, penambahan noise) dilakukan sebelum data dibagi 8:2 [3], sehingga korelasi "
  "spasial antara patch latih dan uji tidak dapat sepenuhnya disingkirkan. Hal ini dicatat sebagai batasan.")
figure(FIG / "sample_pairs_grid.png", 14.5, "Gambar 1. Contoh pasangan citra SAR, mask, dan overlay (merah = minyak) per split dan sensor hasil audit.")

H2("2.2 Pemilihan sensor, split, dan preprocessing")
P("Eksperimen utama menggunakan **Sentinel-1** karena jumlah sampelnya terbanyak, file dengan label ambigu lebih sedikit (1.468 vs 1.654), "
  "sesuai dengan katalog kasus, dan datanya tersedia terbuka sehingga relevan untuk operasional. Data latih dibagi menjadi 2.850 latih dan "
  "504 validasi (15%, *seed* 42). Karena ID berkas terbukti tidak berurutan menurut *scene* (jarak Hamming antar-ID berurutan sama dengan "
  "pasangan acak, median 126), pengelompokan dilakukan berdasarkan komponen *near-duplicate* agar citra yang mirip tidak terpisah ke latih "
  "dan validasi. Set uji (839 citra) hanya dipakai sekali untuk evaluasi akhir. Proporsi piksel minyak adalah 29,3% (latih), 29,4% "
  "(validasi), dan 34,7% (uji).")
P("Preprocessing: kanal R (= grayscale), ukuran asli 256×256 tanpa resize, normalisasi *z-score* x' = (x/255 − 0,3834)/0,2020 dengan "
  "statistik dari subset latih saja. Augmentasi hanya diterapkan pada data latih: 8 transformasi dihedral (rotasi 90° dan flip) yang "
  "identik untuk citra dan mask, serta jitter kecerahan/kontras ±10% khusus citra. Konfigurasi preprocessing disimpan agar inferensi web "
  "memakai langkah yang sama persis.")
figure(FIG / "pipeline.png", 15.5, "Gambar 2. Diagram alur sistem, dari data hingga inferensi di browser.")

H2("2.3 Arsitektur model dan pelatihan")
P("Model utama adalah **U-Net Lite**, varian U-Net [11] dengan 4 level *encoder–decoder* dan jumlah kanal 16–32–64–128–256 "
  "(±1,94 juta parameter, 7,8 MB dalam FP32). Setiap blok terdiri atas dua lapis Conv 3×3–BatchNorm–ReLU; *downsampling* memakai MaxPool "
  "2×2, *upsampling* memakai ConvTranspose 2×2, dan fitur *encoder* digabungkan melalui *skip connection*. Keluaran berupa satu peta logit "
  "256×256. Setelah diekspor, graf hanya berisi operator Conv, ConvTranspose, MaxPool, Relu, dan Concat, yang semuanya didukung "
  "onnxruntime-web.")
P("Pelatihan menggunakan loss 0,5·BCE + 0,5·Soft Dice untuk menangani ketidakseimbangan kelas, optimizer AdamW (lr 10⁻³, *weight decay* "
  "10⁻⁴) dengan jadwal *cosine* selama 40 epoch, *batch* 16, dan *mixed precision* (AMP) pada GPU Tesla T4 di Google Colab. Checkpoint "
  "terbaik dipilih berdasarkan Dice validasi (epoch 37, Dice 0,8640); total waktu pelatihan 10,0 menit. Threshold biner dipilih melalui "
  "*sweep* 0,20–0,80 pada data **validasi**, menghasilkan 0,45 (Dice validasi 0,8641).")

H2("2.4 Evaluasi dan baseline")
P("Metrik yang digunakan adalah Dice (setara F1 piksel), IoU, precision, recall, dan PR-AUC piksel. Agregasi utama bersifat **global**: "
  "TP/FP/FN/TN dijumlahkan dari seluruh piksel semua citra uji, lalu metrik dihitung. Metrik *macro* (rata-rata per citra) juga "
  "dilaporkan. Untuk perbandingan dengan [3], dihitung pula mIoU dua kelas (rata-rata IoU minyak dan latar). Dua baseline disertakan: (a) "
  "*mask* kosong (selalu memprediksi \"bukan minyak\") untuk menunjukkan bahwa akurasi piksel menyesatkan pada data tidak seimbang, dan (b) "
  "*dark-spot thresholding* klasik (blur 7×7, intensitas < 70; ambang dipilih pada data latih). Generalisasi lintas sensor diuji terpisah "
  "pada 776 citra uji PALSAR yang tidak pernah dilihat model.")

H2("2.5 Optimasi Edge AI")
P("Model diekspor ke ONNX (opset 17) lalu dibuat dua varian teroptimasi: **FP16** (bobot dan komputasi 16-bit, I/O tetap FP32) dan "
  "**INT8** melalui kuantisasi statis format QDQ per-kanal [12] dengan kalibrasi 200 citra latih. Varian untuk web dipilih dengan aturan "
  "yang ditetapkan sebelumnya: varian terkecil yang penurunan Dice **validasinya** ≤ 0,005 dibandingkan FP32. Aplikasi web berupa halaman "
  "statis di Vercel yang menjalankan model dengan onnxruntime-web [14] berbasis WebAssembly; header COOP/COEP diaktifkan agar WASM dapat "
  "berjalan multi-thread. Dengan demikian, citra pengguna tidak pernah dikirim ke server.")

# ============================ HASIL DAN PEMBAHASAN ============================
H1("3. Hasil dan Pembahasan")
H2("3.1 Proses pelatihan")
figure(FIG / "training_curves.png", 15.5, "Gambar 3. Kurva loss (kiri) serta Dice/IoU validasi pada threshold 0,5 (kanan) selama 40 epoch.")
P("Loss latih dan validasi turun bersamaan dan Dice validasi naik stabil hingga sekitar 0,86 tanpa tanda *overfitting* yang kuat "
  "(Gambar 3). Kurva yang masih sedikit naik di akhir menunjukkan bahwa pelatihan lebih lama berpotensi memberi peningkatan kecil.")

H2("3.2 Metrik segmentasi pada set uji")
table("Tabel 2. Hasil pada set uji Sentinel-1 (839 citra, threshold 0,45, agregasi global).",
      ["Model", "Dice/F1", "IoU", "Precision", "Recall", "PR-AUC", "Akurasi"],
      [["**U-Net Lite (FP32)**", "**0,8547**", "**0,7462**", "0,8058", "**0,9099**", "**0,9361**", "0,8926"],
       ["U-Net Lite, tanpa 9 near-duplicate (830 citra)", "0,8539", "0,7451", "0,8054", "0,9087", "0,9351", "0,8925"],
       ["Baseline dark-spot thresholding", "0,7259", "0,5698", "0,6669", "0,7964", "–", "0,7912"],
       ["Baseline mask kosong", "0,0000", "0,0000", "0,0000", "0,0000", "–", "0,6528"],
       ["*Lintas sensor:* U-Net Lite pada uji PALSAR (776)", "0,7774", "0,6358", "0,7276", "0,8344", "0,8680", "0,9197"],
       ["*Lintas sensor:* dark-spot pada uji PALSAR", "0,6410", "0,4717", "0,8651", "0,5092", "–", "0,9042"]],
      [5.6, 1.6, 1.5, 1.7, 1.5, 1.5, 1.6], size=8.5, bold_rows=(0,),
      note="Dice macro (rata-rata per citra) U-Net Lite = 0,7609; IoU macro = 0,6508. Baseline mask kosong mencapai akurasi 65,3% "
           "tanpa mendeteksi satu piksel minyak pun, sehingga akurasi tidak dipakai sebagai metrik utama.")
P("U-Net Lite unggul jauh atas kedua baseline: Dice naik 0,129 dan IoU naik 0,176 dibandingkan *dark-spot thresholding*. Membuang 9 citra "
  "*near-duplicate* hanya menurunkan Dice 0,0008, sehingga hasil tidak didorong oleh kebocoran data. Recall (0,910) lebih tinggi daripada "
  "precision (0,806): model cenderung sedikit melebihkan batas tumpahan (Gambar 4). Dari seluruh piksel laut, 11,7% salah ditandai sebagai "
  "minyak, sedangkan dari seluruh piksel minyak hanya 9,0% yang terlewat. Untuk sistem peringatan dini HSSE, sifat ini lebih aman karena "
  "tumpahan yang terlewat lebih mahal dampaknya daripada alarm palsu yang dapat diverifikasi analis.")
figure(FIG / "confusion_matrix_test.png", 6.0, "Gambar 4. Confusion matrix piksel pada set uji Sentinel-1 (dinormalisasi per baris).")

H2("3.3 Perbandingan dengan tolok ukur dataset SOS")
table("Tabel 3. Perbandingan pada subset uji Sentinel-1 dataset SOS.",
      ["Model", "mIoU (%)", "F1 (%)", "Recall (%)", "Precision (%)", "Ukuran model"],
      [["U-Net [3]", "81,46", "86,10", "81,22", "85,61", "tidak dilaporkan"],
       ["D-LinkNet [3]", "82,32", "87,08", "85,22", "85,22", "tidak dilaporkan"],
       ["DeepLabv3 [3]", "82,94", "87,70", "84,76", "88,08", "tidak dilaporkan"],
       ["CBD-Net [3]", "83,42", "87,87", "87,32", "91,20", "tidak dilaporkan"],
       ["**U-Net Lite (ours, FP32)**", "**79,46**", "**85,47**", "**90,99**", "**80,58**", "**7,77 MB**"],
       ["**U-Net Lite (ours, INT8)**", "–", "**85,45**", "**90,90**", "**80,62**", "**2,01 MB**"]],
      [4.6, 1.9, 1.7, 1.9, 2.1, 2.8], size=8.5, bold_rows=(4, 5),
      note="Nilai [3] dikutip dari Tabel III paper tersebut (threshold 0,5; cara agregasi tidak dirinci). mIoU kami = rata-rata IoU minyak "
           "(0,7462) dan IoU latar (0,8429). Perbedaan protokol membuat perbandingan ini bersifat indikatif.")
P("Pada subset yang sama, F1 U-Net Lite 0,6 poin di bawah U-Net standar dan 2,4 poin di bawah CBD-Net [3]. Selisih ini wajar karena "
  "model kami sangat ringan, tidak memakai *encoder* pralatih, dan tidak memakai modul *attention* maupun supervisi tepi seperti CBD-Net. "
  "Sebaliknya, recall model kami (91,0%) adalah yang tertinggi di Tabel 3, dan model INT8 berukuran hanya 2 MB sehingga dapat dijalankan "
  "langsung di browser. *Trade-off* ini sesuai dengan tujuan proyek: model yang cukup akurat untuk *screening* dan murah dioperasikan.")

H2("3.4 Efisiensi komputasi (Green/Edge AI)")
table("Tabel 4. Ukuran, akurasi, dan latensi tiap varian model.",
      ["Varian", "Ukuran", "Dice val", "Dice uji", "Latensi CPU Colab*", "Latensi browser**"],
      [["ONNX FP32", "7,77 MB", "0,8641", "0,8547", "64,4 ms", "–"],
       ["ONNX FP16", "3,89 MB", "0,8641", "0,8547", "61,6 ms", "–"],
       ["**ONNX INT8 (dipakai web)**", "**2,01 MB**", "**0,8638**", "**0,8545**", "72,5 ms (1 thread: 50,8)", "**65–74 ms**"],
       ["PyTorch GPU T4 (FP32 / AMP)", "7,8 MB", "–", "–", "2,78 / 2,69 ms", "–"]],
      [4.4, 1.8, 1.6, 1.6, 3.2, 2.6], size=8.5, bold_rows=(2,),
      note="*onnxruntime 1.30 CPU (2 vCPU Colab), batch 1, 5 warm-up + 50 run, median. **Chrome di laptop uji, onnxruntime-web 1.30 WASM "
           "4 thread di cayman-kelompok1.vercel.app, median 3 run setelah warm-up untuk 4 sampel; tanpa COOP/COEP (1 thread) ±280–300 ms. "
           "Latensi tidak termasuk pre/post-processing.")
P("Kuantisasi INT8 memperkecil model 3,9 kali dengan penurunan Dice uji hanya 0,0002, dan 99,6% piksel mask-nya identik dengan model "
  "PyTorch. Ukuran 2 MB berada jauh di bawah target panduan (20–30 MB). Uji di browser menghasilkan Dice yang sama dengan perhitungan "
  "Python pada 3 dari 4 sampel (selisih ≤ 0,0003), sedangkan satu sampel sulit berbeda 0,015. Selisih ini diduga berasal dari perbedaan "
  "kernel INT8 antara WASM dan x86. Pada CPU Colab, INT8 tidak secara konsisten lebih cepat daripada FP32, sehingga keuntungan utamanya "
  "adalah ukuran unduhan yang kecil.")
figure(FIG / "web_live.jpg", 14.0, "Gambar 5. Aplikasi web CAYMAN (cayman-kelompok1.vercel.app): inferensi di browser dengan tombol Try Sample Data.")

H2("3.5 Visualisasi dan analisis error")
figure(FIG / "pred_examples.png", 11.5, "Gambar 6. Contoh prediksi uji: kasus terburuk, median, terbaik, dan GT kosong (kolom terakhir: TP hijau, FP merah, FN biru).")
P("Dice per citra (805 citra uji yang berisi minyak) memiliki median 0,797, persentil-10 0,517, dan persentil-90 0,965; sebanyak 70 citra "
  "memiliki Dice < 0,5 (Gambar 6 dan 7). Pola kesalahan utama adalah:")
B("**Tumpahan sangat kecil.** Area GT hanya beberapa piksel sehingga Dice per citra tidak stabil. Model juga menandai garis gelap tipis "
  "yang tidak dilabeli, kemungkinan *look-alike* atau label yang terlewat.")
B("**Batas tumpahan.** Label berupa poligon kasar, sedangkan prediksi lebih halus dan sedikit melebar; FP terkumpul di tepi slick.")
B("**Citra tanpa minyak** (34 citra): rata-rata hanya 0,25% piksel salah ditandai, umumnya berupa bercak gelap kecil. Pada 20 citra yang "
  "seluruhnya minyak, Dice ≥ 0,92.")
figure(FIG / "test_dice_distribution.png", 14.5, "Gambar 7. Distribusi Dice per citra (kiri) dan hubungannya dengan luas tumpahan GT (kanan).")
P("Pada data PALSAR yang tidak pernah dilihat model, Dice turun ke 0,777 (Tabel 2) tetapi tetap di atas baseline (0,641). Hal ini "
  "menunjukkan bahwa model perlu dilatih ulang atau di-*fine-tune* sebelum dipakai pada sensor atau wilayah lain.")

# ========================= DAMPAK OPERASIONAL & BISNIS ========================
H1("4. Analisis Dampak Operasional dan Estimasi Bisnis")
P("Solusi ini menyasar **Pilar 1 HSSE** (perlindungan lingkungan laut) dan secara tidak langsung **Pilar 3** (efisiensi biaya). Skenario "
  "penggunaannya adalah *screening* otomatis citra Sentinel-1 di sekitar anjungan lepas pantai, jalur pipa bawah laut, dan terminal. "
  "Keluarannya berupa peta area tumpahan beserta estimasi luas dalam km² (luas = jumlah piksel minyak × resolusi²) sebagai dasar prioritas "
  "verifikasi dan pengerahan tim respons.")
B("**Kecepatan screening.** Latensi terukur 65–74 ms per patch 256×256 di browser. Sebagai estimasi, area 100 km × 100 km pada resolusi "
  "10 m (10.000 × 10.000 piksel ≈ 1.526 patch) dapat dipindai sekitar 1,9 menit di laptop uji. Angka ini merupakan ekstrapolasi dari "
  "pengukuran, belum termasuk pengunduhan dan pemrosesan awal citra.")
B("**Keandalan untuk peringatan dini.** Recall 0,91 berarti sekitar 9 dari 10 piksel minyak terdeteksi. Precision 0,81 menunjukkan bahwa "
  "sekitar 19% area yang ditandai perlu dikonfirmasi analis. Karena itu model diposisikan sebagai alat bantu (*human-in-the-loop*), bukan "
  "pengambil keputusan tunggal.")
B("**Biaya infrastruktur.** Model 2 MB dijalankan di browser pengguna dan halaman statis di-*host* di Vercel paket Hobby, sehingga tidak "
  "memerlukan server GPU untuk inferensi. Data Sentinel-1 tersedia terbuka melalui program Copernicus.")
B("**Pelaporan.** Peta dan luas tumpahan dapat dilampirkan pada laporan insiden HSSE dan pelaporan ke regulator.")
P("**Estimasi finansial belum dihitung** karena memerlukan data internal perusahaan. Kerangka perhitungan yang disarankan: penghematan per "
  "periode = (waktu interpretasi manual per scene − waktu screening + verifikasi) × biaya analis per jam × jumlah scene, ditambah biaya "
  "server GPU yang dihindari. Parameter tersebut perlu diisi dari data operasional sebelum angka penghematan dapat diklaim.")
P("**Risiko dan mitigasi:** (1) *look-alike* ditangani dengan verifikasi analis dan penambahan kelas *look-alike* ke data latih; (2) "
  "pergeseran domain (misalnya perairan Indonesia) ditangani dengan validasi pilot dan *fine-tuning* menggunakan citra lokal; (3) satu "
  "citra hanya memotret kondisi sesaat, sehingga pemantauan penyebaran memerlukan citra berkala dan dapat digabungkan dengan model dispersi "
  "seperti pada sistem operasional Petalas dkk. [10].")

# ================================ KESIMPULAN ==================================
H1("5. Kesimpulan dan Saran")
P("Proyek ini menghasilkan *pipeline* segmentasi tumpahan minyak dari citra Sentinel-1 SAR yang telah diaudit, dapat direproduksi, dan "
  "berjalan di browser. U-Net Lite (1,94 juta parameter) mencapai Dice 0,855, IoU 0,746, dan recall 0,910 pada 839 citra uji, jauh di atas "
  "baseline klasik, serta hanya 2,4 poin F1 di bawah CBD-Net pada dataset yang sama. Kuantisasi INT8 menghasilkan model 2,01 MB tanpa "
  "penurunan akurasi yang berarti, dan aplikasi web publik di cayman-kelompok1.vercel.app menjalankan inferensi di sisi klien dalam 65–74 ms "
  "per patch.")
P("Saran pengembangan: (1) menggunakan *encoder* ringan pralatih (misalnya MobileNet) serta modul *attention*/supervisi tepi untuk menutup "
  "selisih dengan CBD-Net; (2) menambahkan kelas *look-alike* dan data multi-sensor; (3) memproses citra Sentinel-1 berukuran penuh dengan "
  "*tiling* dan georeferensi; (4) menggunakan citra berkala untuk memantau penyebaran; (5) melakukan validasi pilot di perairan operasi "
  "Indonesia bersama analis HSSE; serta (6) menguji akselerasi WebGPU.")

# =============================== DAFTAR PUSTAKA ===============================
H1("Daftar Pustaka")
refs = [
    "M. Fingas and C. Brown, \"A review of oil spill remote sensing,\" *Sensors*, vol. 18, no. 1, p. 91, 2018, doi: 10.3390/s18010091.",
    "R. Al-Ruzouq *et al.*, \"Sensors, features, and machine learning for oil spill detection and monitoring: A review,\" *Remote Sensing*, vol. 12, no. 20, p. 3338, 2020, doi: 10.3390/rs12203338.",
    "Q. Zhu *et al.*, \"Oil spill contextual and boundary-supervised detection network based on marine SAR images,\" *IEEE Trans. Geosci. Remote Sens.*, vol. 60, pp. 1–10, 2022, doi: 10.1109/TGRS.2021.3115492.",
    "M. Krestenitis *et al.*, \"Oil spill identification from satellite images using deep neural networks,\" *Remote Sensing*, vol. 11, no. 15, p. 1762, 2019, doi: 10.3390/rs11151762.",
    "M. Shaban *et al.*, \"A deep-learning framework for the detection of oil spills from SAR data,\" *Sensors*, vol. 21, no. 7, p. 2351, 2021, doi: 10.3390/s21072351.",
    "R. Hasimoto-Beltran, M. Canul-Ku, G. M. Díaz Méndez, F. J. Ocampo-Torres, and B. Esquivel-Trava, \"Ocean oil spill detection from SAR images based on multi-channel deep learning semantic segmentation,\" *Marine Pollution Bulletin*, vol. 188, p. 114651, 2023, doi: 10.1016/j.marpolbul.2023.114651.",
    "C. Li, D. Kim, S. Park, J. Kim, and J. Song, \"A self-evolving deep learning algorithm for automatic oil spill detection in Sentinel-1 SAR images,\" *Remote Sensing of Environment*, vol. 299, p. 113872, 2023, doi: 10.1016/j.rse.2023.113872.",
    "L. Liao, Q. Zhao, and W. Song, \"Monitoring of oil spill risk in coastal areas based on polarimetric SAR satellite images and deep learning theory,\" *Sustainability*, vol. 15, no. 19, p. 14504, 2023, doi: 10.3390/su151914504.",
    "K. Das, P. Janardhan, and M. R. Singh, \"Oil spill detection in SAR images: A U-Net semantic segmentation framework with multiple backbones,\" in *Water and Environment, Volume 2*, Lecture Notes in Civil Engineering, vol. 414. Singapore: Springer, 2024, pp. 65–77, doi: 10.1007/978-981-97-7502-6_6.",
    "S. Petalas, T. Psomouli, N. Kokkos, and G. Sylaios, \"Operational oil-spill detection in the framework of digital twin using SAR imagery and deep learning,\" in *Proc. OCEANS 2025 Brest*, 2025, pp. 1–6, doi: 10.1109/OCEANS58557.2025.11104698.",
    "O. Ronneberger, P. Fischer, and T. Brox, \"U-Net: Convolutional networks for biomedical image segmentation,\" in *Proc. MICCAI 2015*, LNCS, vol. 9351. Cham: Springer, 2015, pp. 234–241, doi: 10.1007/978-3-319-24574-4_28.",
    "B. Jacob *et al.*, \"Quantization and training of neural networks for efficient integer-arithmetic-only inference,\" in *Proc. IEEE/CVF CVPR*, 2018, pp. 2704–2713, doi: 10.1109/CVPR.2018.00286.",
    "BitsandLayers, \"Deep-SAR SOS Oil Spill Detection Dataset,\" Kaggle, v1, 2026. [Online]. Available: https://www.kaggle.com/datasets/bitsandlayers/sar-oil-spill-segmentation-dataset-sos (diakses 24 Sep. 2026). Lisensi CC BY 4.0.",
    "ONNX Runtime developers, \"ONNX Runtime (onnxruntime-web) v1.30.0,\" 2026. [Online]. Available: https://onnxruntime.ai",
]
for i, ref in enumerate(refs, 1):
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.left_indent = Cm(0.9); p.paragraph_format.first_line_indent = Cm(-0.9)
    p.paragraph_format.space_after = Pt(2)
    r = p.add_run(f"[{i}]\t"); r.font.size = Pt(9.5)
    add_runs(p, ref, size=9.5)

# ================================= LAMPIRAN ===================================
from docx.enum.text import WD_BREAK
doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
H1("Lampiran A. Contribution Statement")
P("Persentase kontribusi wajib diisi oleh tim secara jujur (total 100%) dan konsisten dengan riwayat *commit* GitHub.", indent=False)
table("Tabel A1. Pembagian peran dan kontribusi anggota Kelompok 1 CAYMAN.",
      ["Nama (NPM)", "Peran", "Tanggung jawab", "Kontribusi"],
      [["Ade Rizky Darmawan (23083010080), Ketua", "Model Architect Specialist", "Arsitektur U-Net, training pipeline, threshold, evaluasi metrik", "…%"],
       ["Arkananta Daniswara Handoyo (23083010059)", "Data & Pipeline Specialist", "Akuisisi dataset, audit data, preprocessing, split", "…%"],
       ["Muhammad Arsyad Alzam (23083010082)", "Deployment & Edge Specialist", "Ekspor ONNX, kuantisasi INT8, onnxruntime-web, Vercel, GitHub", "…%"],
       ["Choirul Amin (22083010050)", "Frontend & UX Specialist", "UI web, visualisasi hasil segmentasi, landing page tim", "…%"],
       ["Hana Titania Sastrian (23083010056)", "Lead Technical Writer", "Laporan ilmiah, penelusuran referensi, README", "…%"],
       ["Zaydan Arief Athallah (23083010063)", "Research & Business Impact Analyst", "Analisis dampak HSSE, estimasi bisnis, materi presentasi", "…%"],
       ["**Total**", "", "", "**100%**"]],
      [4.6, 3.4, 5.8, 2.0], size=8.5)

H1("Lampiran B. Artefak Proyek")
B("Repositori GitHub (publik): https://github.com/aderizkydarmawan/cayman-oil-spill-sar, berisi notebook Colab, skrip model/ekspor, "
  "hasil audit, metrik (JSON/CSV), model ONNX, dan kode web.")
B("Aplikasi web: https://cayman-kelompok1.vercel.app, yang memuat demo inferensi, *Try Sample Data*, estimasi luas km², dan profil tim.")
B("Reproduksi: buka notebooks/Kasus38_SAR_OilSpill_UNetLite.ipynb di Google Colab (runtime T4 GPU) lalu jalankan *Run all*.")

doc.save(OUT)
print("saved", OUT)
