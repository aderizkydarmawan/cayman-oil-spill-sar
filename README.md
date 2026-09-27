# Kasus 38 — Marine Oil Spill Detection & Mapping via Satellite SAR

**Kelompok 1 — CAYMAN** · Tugas Besar Deep Learning, S1 Sains Data UPN "Veteran" Jawa Timur

Segmentasi biner tumpahan minyak pada citra **Sentinel-1 SAR** memakai **U-Net ringan** (1,94 juta parameter). Model dikuantisasi ke **INT8 ONNX (2,0 MB)** dan inferensinya berjalan **di browser** memakai onnxruntime-web (WASM).
**Pilar industri:** HSSE, yaitu perlindungan lingkungan laut dan respons cepat terhadap tumpahan minyak.

> Semua angka di bawah berasal dari eksekusi nyata: notebook di Google Colab (GPU Tesla T4) pada 24 September 2026, dan uji browser lokal pada 26 September 2026. Sumber tiap angka ada di kolom terakhir tabel.

## Struktur

```
notebooks/Kasus38_SAR_OilSpill_UNetLite.ipynb   notebook Colab lengkap (audit → training → evaluasi → ONNX → artefak web)
src/unet_lite.py                               definisi model
src/export_onnx.py                             ekspor ONNX FP32/FP16/INT8 + verifikasi akurasi & latency
outputs/audit/        hasil audit data (CSV/JSON/PNG)
outputs/splits/       daftar file train/val/test (split_sentinel.csv)
outputs/checkpoints/  unet_lite_best.pt (epoch 37)
outputs/eval/         metrics.json, metrics_summary.csv, per_image_test_dice.csv, grafik
outputs/onnx/         model FP32/FP16/INT8 + edge_benchmark.json
outputs/training_log.csv, training_curves.png, train_config.json, preprocessing_config.json, val_threshold_sweep.csv
web/                  demo inferensi di browser (index.html, app.js, model/, samples/)
```

## Dataset

| Item | Nilai |
|---|---|
| Nama | Deep-SAR SOS Oil Spill Detection Dataset (SOS) |
| URL | https://www.kaggle.com/datasets/bitsandlayers/sar-oil-spill-segmentation-dataset-sos |
| Versi / akses | v1 lewat `kagglehub`, diakses 24 September 2026 |
| Pemilik | BitsandLayers (Kaggle). Halaman Kaggle tidak mencantumkan DOI maupun sitasi sumber asli. |
| Lisensi | **CC BY 4.0**, sesuai yang tertulis di halaman Kaggle |
| Isi | 8.070 pasangan PNG 256×256: PALSAR 3.101 train / 776 test, Sentinel-1A 3.354 train / 839 test |

Kemungkinan sumber asli dataset SOS adalah Zhu dkk. (2022) (lihat Referensi). Tim perlu memastikannya sebelum dikutip sebagai sumber dataset.

## Hasil audit (`outputs/audit/`)

- **Pasangan citra-mask:** semua 8.070 cocok berdasarkan nama file. Tidak ada file tanpa pasangan dan tidak ada ukuran yang tidak cocok.
- **Format:** citra RGB dengan ketiga channel identik (grayscale). Karena itu model memakai 1 channel.
- **Nilai mask:**
  - Label test murni 0/255.
  - Label train berisi ±2,2–2,5% piksel bernilai antara (ada di ±44–53% file).
  - Aturan binarisasi: piksel ≥128 dianggap minyak.
- **Kualitas citra:** tidak ada NaN/Inf maupun citra konstan.
- **Duplikat:**
  - Tidak ada duplikat eksak (md5) di dalam maupun antar split.
  - Pengecekan aHash dengan 8 variasi rotasi/flip (ambang ≤8/256 bit) menemukan 9 citra test mirip train per sensor. Setelah dicek visual, citra-citra ini bukan salinan; kemiripannya hanya pada komposisi gelap-terang. Dampaknya diuji di tabel sensitivitas.
- **Urutan ID file:** ID file tidak mencerminkan urutan scene (jarak Hamming antar ID berurutan sama dengan pasangan acak). Karena itu split berbasis grup scene tidak bisa dilakukan. Grup train/val dibentuk dari komponen near-duplicate.

## Metodologi

1. **Sensor:** Sentinel-1 dipilih karena sampelnya terbanyak, file dengan label ambigu lebih sedikit, sesuai katalog Kasus 38, dan datanya open-access.
2. **Split:** train 2.850 / val 504 dari folder `train` (seed 42, grup near-duplicate tidak dipisah). Test 839 hanya dipakai sekali untuk evaluasi final.
3. **Preprocessing:** channel 0, ukuran asli 256×256, `(x/255 − 0,38344) / 0,20197`. Mean dan std dihitung dari subset train saja.
4. **Model:** U-Net 4 level dengan channel 16–256, memakai BatchNorm dan ConvTranspose.
5. **Training:**
   - Loss 0,5·BCE + 0,5·Dice, optimizer AdamW (lr 1e-3) dengan cosine schedule, batch 16, 40 epoch, AMP.
   - Augmentasi: 8 transformasi dihedral (sama persis untuk citra dan mask) plus jitter intensitas, hanya pada train.
   - Waktu training 10,0 menit di T4. Checkpoint terbaik ada di epoch 37.
6. **Threshold:** 0,45, dipilih dari sweep di **validation** (Dice 0,8641).
7. **Baseline:** (a) mask kosong; (b) dark-spot, yaitu blur 7×7 lalu intensitas <70 (ambang dipilih di train).

## Hasil (test Sentinel-1, 839 citra, threshold 0,45) — `outputs/eval/metrics_summary.csv`

| Model | Dice | IoU | Precision | Recall | PR-AUC | Dice macro |
|---|---|---|---|---|---|---|
| **U-Net Lite** | **0,8547** | **0,7462** | 0,8058 | 0,9099 | 0,9361 | 0,7609 |
| U-Net Lite, tanpa 9 near-dup (830) | 0,8539 | 0,7451 | 0,8054 | 0,9087 | 0,9351 | 0,7594 |
| Dark-spot threshold | 0,7259 | 0,5698 | 0,6669 | 0,7964 | – | 0,5605 |
| Mask kosong (akurasi 65,3%) | 0 | 0 | 0 | 0 | – | 0,0405 |
| *Lintas sensor:* U-Net Lite pada PALSAR test (776) | 0,7774 | 0,6358 | 0,7276 | 0,8344 | 0,8680 | 0,7408 |

- **Agregasi:**
  - *Global:* TP/FP/FN/TN dijumlahkan dari semua piksel semua citra, baru metrik dihitung.
  - *Macro:* metrik dihitung per citra lalu dirata-rata. Jika GT dan prediksi sama-sama kosong, Dice dihitung 1.
  - *PR-AUC:* average precision piksel dari histogram skor dengan 1000 bin.
- **Confusion matrix piksel (test):** TP 17.370.333 · FP 4.186.980 · FN 1.720.879 · TN 31.706.512
- **Proporsi foreground:** 34,7% di test, 29,3% di train.

### Analisis error (`outputs/eval/test_predictions_best_median_worst.png`)

- **Sebaran Dice per citra** (805 citra yang GT-nya berisi minyak): median 0,797, p10 0,517, p90 0,965. Ada 70 citra dengan Dice <0,5.
- **Kasus terburuk:** citra dengan area GT sangat kecil. Model menandai garis gelap tipis yang tidak dilabeli; kemungkinan *look-alike* atau label yang terlewat.
- **Kasus median:** GT berupa poligon kasar, sedangkan prediksi lebih halus dan sedikit melebar. FP terkumpul di tepi slick, jadi precision lebih rendah daripada recall.
- **GT kosong** (34 citra): rata-rata hanya 0,25% piksel yang diprediksi sebagai minyak.

## Edge AI — ONNX & kuantisasi (`outputs/onnx/edge_benchmark.json`)

| Varian | Ukuran | Dice val | Dice test | IoU test | Latency CPU Colab, semua thread (median/p90) | Latency 1 thread |
|---|---|---|---|---|---|---|
| FP32 | 7,77 MB | 0,8641 | 0,8547 | 0,7462 | 64,4 / 70,6 ms | 63,4 ms |
| FP16 | 3,89 MB | 0,8641 | 0,8547 | 0,7462 | 61,6 / 66,1 ms | 62,8 ms |
| **INT8 QDQ** (dipakai web) | **2,01 MB** | 0,8638 | 0,8545 | 0,7459 | 72,5 / 82,9 ms | 50,8 ms |
| PyTorch GPU T4 (FP32 / AMP) | – | – | – | – | 2,78 / 2,69 ms | – |

- **Cara ukur latency:** batch 1, input float32 1×1×256×256, onnxruntime 1.30 CPUExecutionProvider di CPU Colab. Ada 5 warm-up lalu 50 run, dan pre/post-processing tidak ikut dihitung.
- **Hasil INT8:** tidak lebih cepat secara konsisten di CPU ini, tetapi ukurannya 3,9× lebih kecil.
- **Kesetaraan dengan PyTorch:** selisih probabilitas ONNX FP32 vs PyTorch maksimal 9,5e-7.
- **Aturan pemilihan varian web:** varian terkecil yang penurunan Dice validation-nya ≤0,005 dibanding FP32.

### Uji inferensi di browser (sudah dites)

Lingkungan uji: Chrome di laptop pengguna (Windows 11), onnxruntime-web 1.30.0 WASM dengan 1 thread (tanpa cross-origin isolation), halaman `web/` disajikan dari `localhost`.

| Sampel | Catatan | Dice browser | Dice Python (ORT CPU) | Latency (median 3 run setelah warm-up) |
|---|---|---|---|---|
| 1 (test/807) | mudah | 0,9044 | 0,9047 | 292 ms |
| 2 (test/187) | tipikal | 0,7627 | 0,7628 | 288 ms |
| 3 (test/513) | sulit | 0,5908 | 0,6060 | 304 ms |
| 4 (test/814) | tanpa minyak | 1,0000 | 1,0000 | 278 ms |

Dengan header COOP/COEP (`web/vercel.json`, atau lokal lewat `python src/serve_local.py` dari folder `web/`), `crossOriginIsolated` aktif sehingga WASM berjalan 4 thread. Latency per sampel menjadi 122 / 105 / 104 / 112 ms (median 3 run setelah warm-up), dengan Dice identik dengan tabel di atas.

Selisih kecil pada sampel 3 kemungkinan berasal dari perbedaan kernel INT8 antara WASM dan x86. Latency di browser sangat bergantung pada perangkat.

## Menjalankan

**Notebook (Colab):**
1. Unggah notebook ke Colab.
2. Pilih Runtime ▸ Change runtime type ▸ **T4 GPU**.
3. Jalankan Run all. Dataset terunduh otomatis lewat kagglehub, tanpa token.
4. Hasil tersimpan di `/content/outputs`, dan sel terakhir mengunduh file zip-nya.

**Demo web lokal:**
```bash
cd web
python -m http.server 8000   # buka http://localhost:8000
```

## Kontrak integrasi frontend (`web/model/model_metadata.json`)

| Bagian | Spesifikasi |
|---|---|
| **Input** | `image`, float32, shape `[1,1,256,256]` (NCHW, grayscale). Grayscale = rata-rata RGB, sama dengan channel R untuk citra dataset. Resize ke 256×256 bila ukurannya berbeda. Nilai = `(x/255 − mean)/std`. |
| **Output** | `logits`, float32, `[1,1,256,256]`. Mask = `sigmoid(logits) ≥ 0,45`. |
| **Label** | 0 = laut / bukan minyak, 1 = oil spill |
| **Sampel** | `web/samples/samples.json`: 4 citra test Sentinel beserta GT-nya, tanpa diubah. Atribusi di `ATTRIBUTION.txt`. |

## Batasan

- Model hanya dilatih pada patch Sentinel-1A di Persian Gulf. Pada PALSAR, Dice turun ke 0,777, dan wilayah atau sensor lain belum diuji.
- Scene/lokasi asal tiap patch tidak diketahui, sehingga kebocoran spasial antar patch tidak bisa sepenuhnya disingkirkan.
- Label train mengandung piksel antara, dan label berbentuk poligon kasar, sehingga batas atas Dice dibatasi oleh kualitas label.
- Tidak ada kelas *look-alike*. Area gelap seperti angin lemah atau biogenic slick berpotensi menimbulkan false positive.
- Latency diukur di CPU Colab dan 1 laptop (browser). Ini belum mewakili perangkat lapangan, dan multi-thread WASM (COOP/COEP) belum diuji.
- Penghematan biaya atau manfaat di lapangan **belum diukur**.

## Referensi kandidat (metadata diverifikasi lewat Crossref; relevansi isi **wajib dibaca tim**)

1. Zhu, Q. dkk. (2022). Oil Spill Contextual and Boundary-Supervised Detection Network Based on Marine SAR Images. *IEEE TGRS*. doi:10.1109/TGRS.2021.3115492. Kemungkinan sumber dataset SOS; perlu dicek.
2. Hasimoto-Beltran, R. dkk. (2023). Ocean oil spill detection from SAR images based on multi-channel deep learning semantic segmentation. *Marine Pollution Bulletin*. doi:10.1016/j.marpolbul.2023.114651
3. Chang, … (2024). A Modified U-Net for Oil Spill Semantic Segmentation in SAR Images. *IGARSS 2024*. doi:10.1109/IGARSS53475.2024.10642291
4. Li, … (2023). A Deep Learning Based Self-Evolving Oil Spill Detection Algorithm Using Sentinel-1 SAR Images. *IGARSS 2023*. doi:10.1109/IGARSS52108.2023.10281695
5. Liao, … (2023). Monitoring of Oil Spill Risk in Coastal Areas Based on Polarimetric SAR Satellite Images and Deep Learning Theory. *Sustainability*. doi:10.3390/su151914504
6. Petalas, … (2025). Operational Oil-Spill Detection in the Framework of Digital Twin Using SAR Imagery and Deep Learning. *OCEANS 2025 Brest*. doi:10.1109/OCEANS58557.2025.11104698

Hasil pencarian yang **tidak** dimasukkan karena berupa preprint (belum peer-review), yaitu dari Research Square, SSRN, dan Preprints.org.

## Live demo & tim

- **Live demo:** https://cayman-kelompok1.vercel.app (alias: https://cayman-seven.vercel.app)
- **Tim:** data ada di `web/team.json`, foto di `web/img/team/`.

| Nama | NPM | Peran | LinkedIn |
|---|---|---|---|
| Ade Rizky Darmawan (Ketua) | 23083010080 | Model Architect Specialist (Modelling & Algoritma) | https://www.linkedin.com/in/aderizkydarmawan/ |
| Arkananta Daniswara Handoyo | 23083010059 | Data & Pipeline Specialist | https://www.linkedin.com/in/arkanadinata |
| Muhammad Arsyad Alzam | 23083010082 | Deployment & Edge Specialist | https://www.linkedin.com/in/arsyad-alzam/ |
| Choirul Amin | 22083010050 | Frontend & UX Specialist | https://www.linkedin.com/in/choirul-amin-hvu |
| Hana Titania Sastrian | 23083010056 | Lead Technical Writer | https://www.linkedin.com/in/hanatitaniaa/ |
| Zaydan Arief Athallah | 23083010063 | Research & Business Impact Analyst | https://www.linkedin.com/in/zaydan-arief-athallah-21ab03295 |

## Deploy ke Vercel

1. Push repo ini ke GitHub (Public).
2. Di Vercel: **New Project → import repo**, lalu set **Root Directory = `web`**. Framework: *Other*, tanpa build command.
3. Project Vercel: `cayman` (team CAYMAN) → https://cayman-kelompok1.vercel.app. Setiap push ke `main` otomatis deploy ulang.
4. `web/vercel.json` sudah mengatur header COOP/COEP untuk WASM multi-thread.

## Laporan ilmiah

- `docs/laporan/Tubes_DL_Kelompok01_Oil_Spill_SAR.pdf`: laporan final (cover + 10 halaman isi; single column, A4, spasi 1.15, margin 2.5 cm).
- `docs/laporan/Tubes_DL_Kelompok01_Oil_Spill_SAR.docx`: versi Word yang bisa diedit.
- `docs/laporan/referensi.bib`: 14 referensi dalam format BibTeX, bisa diimpor ke Mendeley/Zotero.
- `docs/laporan/build_laporan.py`: skrip penyusun laporan; semua angka diambil dari `outputs/`.

## Yang masih harus diisi tim

- Tiap anggota wajib commit sendiri ke repo ini (undang sebagai collaborator).
