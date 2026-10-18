"""Laporan riset lanjutan 'Pantau Bercak Minyak' (docx + pdf). Angka diambil dari STATUS-RISET.md / experiments/log.jsonl."""
import os
from docx import Document
from docx.shared import Pt, Cm, RGBColor

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, "aplikasi-web", "data"); RES = os.path.join(ROOT, "uji-gee-balikpapan", "results_pembeda")
d = Document()
d.styles["Normal"].font.name = "Calibri"; d.styles["Normal"].font.size = Pt(11)
for s in d.sections:
    s.left_margin = s.right_margin = Cm(2.3)
NAVY = RGBColor(0x0B, 0x25, 0x45)


def H(t, l=1):
    h = d.add_heading(t, l)
    for r in h.runs:
        r.font.color.rgb = NAVY


def P(t, b=False):
    d.add_paragraph().add_run(t).bold = b


def L(items):
    for t in items:
        d.add_paragraph(t, style="List Bullet")


def F(path, cap, w=16):
    d.add_picture(path, width=Cm(w))
    r = d.add_paragraph().add_run(cap); r.italic = True; r.font.size = Pt(9)


def T(rows, cap):
    r = d.add_paragraph().add_run(cap); r.bold = True; r.font.size = Pt(10)
    t = d.add_table(rows=len(rows), cols=len(rows[0])); t.style = "Light Grid Accent 1"
    for i, row in enumerate(rows):
        for j, v in enumerate(row):
            t.cell(i, j).text = str(v)
    d.add_paragraph()


d.add_heading("Pantau Bercak Minyak", 0)
P("Laporan riset lanjutan CAYMAN: deteksi dugaan tumpahan minyak dari citra radar Sentinel-1 di perairan Indonesia, beserta tingkat kepercayaannya")
P("Ade Rizky Darmawan · 18 Oktober 2026 · Situs: https://pantau-bercak-minyak.vercel.app")
P("Status: prototipe riset dengan data satelit publik. Bukan produk atau pernyataan resmi Pertamina. Semua hasil adalah dugaan dari citra satelit dan belum dicocokkan dengan pengecekan lapangan.", True)

H("Ringkasan")
P("Tumpahan minyak di laut perlu ditemukan cepat, tetapi patroli udara dan laut mahal dan terbatas. Satelit radar Sentinel-1 memotret laut Indonesia setiap ±6–12 hari, menembus awan dan gelap malam; minyak meredam riak permukaan sehingga tampak gelap di citra radar. Riset ini melanjutkan model CAYMAN menjadi alur kerja utuh: mengambil citra, menandai bercak gelap, memberi skor prioritas beserta alasannya, menambahkan konteks (hujan, mangrove, foto satelit biasa), dan menguji model sebaran minyak. Pada dua kumpulan data berlabel ahli yang terpisah (±3.300 tumpahan), alat menangkap 73–81% tumpahan, dan 92% area yang ditandai memang minyak pada data independen. Alarm palsu hampir tidak ada di laut berangin (±1 dari 20 citra), tetapi di perairan Indonesia pada hari biasa muncul median 8 bercak per lintasan, terutama karena angin lemah dan kondisi pesisir. Skor prioritas tidak lulus uji independen sehingga hanya dipakai untuk mengurutkan, bukan membuang bercak. Model sebaran (OpenDrift) belum lebih baik daripada tebakan 'bercak diam di tempat'. Langkah penentu berikutnya adalah penilaian praktisi dan data lapangan.")

H("1. Latar belakang dan tujuan")
P("CAYMAN (proyek sebelumnya) menunjukkan bahwa model segmentasi ringan dapat menandai minyak pada potongan citra radar. Untuk dipakai di lapangan, pertanyaannya bergeser: apakah alat bekerja pada citra utuh di perairan Indonesia, seberapa sering ia salah alarm, dan bagaimana keluarannya bisa langsung dipakai tim HSSE. Tujuan riset ini:")
L(["Mengukur kemampuan menemukan tumpahan pada data independen (bukan data latih).",
   "Mengukur alarm palsu dalam satuan operasional: bercak per lintasan satelit.",
   "Mencoba alat pada kejadian nyata di Indonesia dan sekitarnya.",
   "Menyediakan keluaran siap pakai: peta, prioritas, alasan, dan konteks lokasi.",
   "Menguji apakah arah sebaran minyak dapat diprakirakan dengan data terbuka."])

H("2. Data")
T([["Data", "Kegunaan", "Sumber / lisensi"],
   ["Sentinel-1 GRD, VV, 20 m", "Citra radar utama", "ESA Copernicus via Google Earth Engine"],
   ["Dataset SOS", "Melatih pendeteksi (U-Net)", "Kaggle, CC BY 4.0"],
   ["Yang & Singha 2025 (±20 ribu bercak)", "Melatih skor prioritas; uji pendeteksi", "PANGAEA 10.1594/PANGAEA.980773, CC BY 4.0"],
   ["Trujillo-Acatitla dkk. (670 tumpahan)", "Uji independen", "Zenodo 13761290, CC BY 4.0"],
   ["CSIRO Sentinel-1 oil/no-oil", "Uji tambahan", "CC BY-SA 4.0"],
   ["ERA5 per jam", "Angin", "ECMWF"],
   ["GPM IMERG V07", "Penanda hujan", "NASA"],
   ["Global Mangrove Watch v3", "Pesisir sensitif", "Bunting dkk. 2022, CC BY 4.0"],
   ["Sentinel-2 L2A", "Foto satelit biasa pembanding", "ESA Copernicus"],
   ["HYCOM; Copernicus Marine", "Arus laut untuk model sebaran", "HYCOM; CMEMS"]],
  "Tabel 1. Data yang dipakai.")
P("Kejadian lokal yang dicoba: Teluk Balikpapan 2018, Karawang (YYA-1) 2019, Karawang 2021, Kepulauan Seribu 2020, Batam, Bintan, Lampung, dan Singapura (Marine Honour) 2024; total 14 kejadian. Selain itu 82 citra Balikpapan dan 77 citra Karawang tanpa kejadian tercatat dipakai untuk mengukur alarm palsu.")

H("3. Metode")
L(["Pengambilan citra: Sentinel-1 VV 20 m lewat Google Earth Engine. Skala intensitas dikunci −32 sampai −17 dB untuk semua citra; skala per citra memicu alarm palsu ±219 km² per citra bersih, skala tetap menurunkannya ke 4,8 km².",
   "Penandaan bercak: U-Net ringan (ONNX), ambang 0,45, ubin 256 piksel dengan langkah 128; bercak < 0,1 km² dan tepi citra dibuang.",
   "Skor prioritas: model gradient boosting (HistGradientBoosting) dengan 9 ukuran per bercak (luas, bentuk, kontras terhadap laut sekitar, jarak ke pantai, dll.), dilatih pada data Yang & Singha dengan batasan monoton pada luas. Ambang 0,255 (recall 90% di validasi silang). Bercak ≥ 10 km² selalu prioritas tinggi. Aturan uji dikunci sebelum melihat hasil uji independen.",
   "Alasan skor: nilai SHAP eksak per bercak; dua kontribusi terbesar ditampilkan dalam bahasa awam.",
   "Konteks: hujan GPM IMERG ≥ 1 mm/jam dalam 5 km saat lintasan; jarak ke mangrove GMW v3 (≤ 5 km = sensitif); Sentinel-2 ±1 hari, awan < 60%, cakupan ≥ 25%.",
   "Model sebaran: OpenDrift/OpenOil, 3.000 partikel dari bercak awal, arus HYCOM harian + angin ERA5 per jam; dibandingkan dengan bercak pada lintasan berikutnya dan dua pembanding sederhana (bercak diam; geser 3% angin).",
   "Pencatatan: setiap angka yang dilaporkan punya ID run di experiments/log.jsonl (hash data, parameter, versi paket)."])

H("4. Hasil")
H("4.1 Menemukan tumpahan", 2)
T([["Uji", "Hasil"],
   ["Yang & Singha (2.630 tumpahan)", "73% tumpahan tersentuh"],
   ["Trujillo (150 gambar, 670 tumpahan; independen)", "81% tumpahan tertangkap; 74% piksel minyak [CI 67–81%]; presisi 92%"],
   ["Laut berangin tanpa minyak (Trujillo)", "0,05 alarm per gambar"],
   ["14 kejadian lokal", "Terlihat jelas 3, mungkin 2; gumpalan di pantai tidak terlihat"]],
  "Tabel 2. Kemampuan pendeteksi.")
F(os.path.join(WEB, "hero_balikpapan.jpg"), "Gambar 1. Teluk Balikpapan, 1 April 2018. Latar: citra radar Sentinel-1; garis merah: bercak yang ditandai otomatis.")
H("4.2 Alarm palsu", 2)
L(["Pada citra perairan Indonesia hari biasa: median 8 bercak per lintasan.",
   "Angin lemah adalah penyebab paling kuat (korelasi Spearman −0,81 di Karawang), konsisten di dua lokasi.",
   "Hujan hanya menjelaskan sebagian kecil: 11% bercak hari biasa di Balikpapan dan 1,5% di Karawang terjadi saat hujan; 0% pada bercak minyak.",
   "Aturan 'laut tenang' (> 15% laut gelap) menandai 51% gambar look-alike, tetapi juga 16% gambar berisi tumpahan."])
H("4.3 Skor prioritas", 2)
P("Versi pertama skor tampak sangat baik di validasi silang (AUC 0,934) tetapi gagal di data independen: hanya 29% luas minyak yang lolos, karena model memakai 'jalan pintas' berupa kegelapan seluruh citra. Versi kedua tanpa jalan pintas: AUC 0,871 di validasi silang dan 0,788 di Trujillo; luas minyak berprioritas tinggi 76% [CI 62–90%], bercak > 10 km² 86%, dan 73% look-alike turun ke prioritas rendah. Target terkunci 90% tidak tercapai, sehingga skor hanya dipakai untuk mengurutkan. Sebagai pembanding, aturan sederhana 'kontras terhadap laut sekitar' saja mencapai AUC 0,744 di Trujillo; model hanya menambah sedikit di atasnya.")
F(os.path.join(RES, "shap_v2_beeswarm.png"), "Gambar 2. Pengaruh tiap ukuran terhadap skor (SHAP). Kontras terhadap laut sekitar paling berpengaruh di semua kumpulan data.", 14)
H("4.4 Konteks lokasi", 2)
L(["Bercak ≤ 5 km dari mangrove: Balikpapan 2, Karawang hari biasa 4, Singapura 6, Batam 10.",
   "Foto Sentinel-2 yang memenuhi syarat tersedia pada 3 dari 8 lintasan di situs."])
H("4.5 Prakiraan sebaran", 2)
T([["Uji", "OpenDrift", "Bercak diam", "Catatan"],
   ["Karawang 2019, 3,5 hari, laut terbuka", "5% luas bercak laut terjangkau", "18%", "95% partikel terdampar di pantai"],
   ["Balikpapan 2018, 12 hari, teluk", "4% partikel kena", "47%", "94% partikel keluar batas data arus"]],
  "Tabel 3. Uji model sebaran.")
F(os.path.join(WEB, "sebaran_karawang_2019.png"), "Gambar 3. Uji sebaran. Oranye: bercak awal; merah: bercak lintasan berikutnya; biru: jalur partikel; hitam: posisi akhir.")
P("Arus per jam yang memasukkan pasang surut (Copernicus Marine) baru tersedia sejak November 2020. Kasus setelah itu (Karawang 2021, Singapura 2024) tidak punya pasangan citra yang bisa dinilai, sehingga uji dengan arus berpasut belum bisa dilakukan. Aturan penilaian ulang Karawang (hanya bercak di laut) ditetapkan setelah ditemukan bahwa sebagian bercak sasaran berada di darat.")

H("5. Yang belum pasti dan perlu tinjauan ahli")
L(["Belum ada pengecekan lapangan: tidak ada bercak di Indonesia yang dicocokkan dengan pengamatan langsung pada waktu yang sama. Perlu data patroli/insiden internal.",
   "Contoh lokal sangat sedikit (24 bercak berlabel minyak). Perlu penilaian praktisi atas 40 bercak contoh (lembar penilaian tersedia).",
   "Skor prioritas belum lulus uji independen (76% vs target 90%).",
   "Beda kondisi pesisir: 97% bercak lokal < 10 km dari pantai, data latih hanya 10%; tambak kadang ikut tertandai. Perlu tinjauan ahli penginderaan jauh.",
   "Penanda laut tenang ikut menandai ±16% citra bertumpahan.",
   "Prakiraan sebaran belum bisa dipakai untuk menunjuk posisi bercak; hanya peringatan kasar pantai yang mungkin terkena.",
   "Beberapa ambang (mis. angin 4 m/s) dipilih setelah melihat data dan belum diuji di kejadian baru."])

H("6. Kesimpulan dan langkah lanjut")
P("Alat ini layak sebagai penyaring awal: ia menemukan sebagian besar tumpahan yang terlihat di radar dan jarang salah di laut berangin, tetapi di perairan pesisir Indonesia masih memunculkan banyak bercak yang perlu dinilai manusia. Nilai utamanya adalah mengurutkan dan memberi konteks, bukan memastikan. Langkah lanjut, berurutan menurut dampaknya:")
L(["Penilaian 40 bercak oleh praktisi HSSE, lalu latih ulang skor dengan label lokal.",
   "Mencocokkan deteksi dengan catatan insiden/patroli internal untuk validasi lapangan.",
   "Pada kejadian berikutnya: jalankan model sebaran dengan arus berpasut Copernicus Marine sebagai uji prospektif.",
   "Tinjauan ahli penginderaan jauh untuk perilaku di pesisir dan tambak."])

H("Referensi")
for r in ["Bunting, P. dkk. (2022). Global Mangrove Watch: updated 2010 mangrove forest extent (v2.5). Remote Sensing, 14(4), 1034.",
          "Dagestad, K.-F., Röhrs, J., Breivik, Ø., Ådlandsvik, B. (2018). OpenDrift v1.0: a generic framework for trajectory modelling. Geoscientific Model Development, 11, 1405–1420.",
          "Hersbach, H. dkk. (2020). The ERA5 global reanalysis. Quarterly Journal of the Royal Meteorological Society, 146, 1999–2049.",
          "Huffman, G. J. dkk. GPM IMERG Final Precipitation L3 Half Hourly, Version 07. NASA GES DISC.",
          "Lundberg, S. M., Lee, S.-I. (2017). A unified approach to interpreting model predictions. Advances in Neural Information Processing Systems 30.",
          "Ronneberger, O., Fischer, P., Brox, T. (2015). U-Net: convolutional networks for biomedical image segmentation. MICCAI 2015.",
          "Trujillo-Acatitla, R. dkk. Dataset tumpahan minyak Sentinel-1. Zenodo, record 13761290.",
          "Yang, Y., Singha, S. (2025). Dataset tumpahan minyak dan look-alike Sentinel-1. PANGAEA, doi:10.1594/PANGAEA.980773."]:
    d.add_paragraph(r)

out = os.path.join(HERE, "Laporan_Riset_Pantau_Bercak_Minyak.docx"); d.save(out)
import win32com.client
w = win32com.client.DispatchEx("Word.Application"); w.Visible = False
try:
    dd = w.Documents.Open(out); dd.SaveAs(out[:-5] + ".pdf", FileFormat=17); dd.Close(False)
finally:
    w.Quit()
print(out)
