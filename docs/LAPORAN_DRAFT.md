# Segmentasi Tumpahan Minyak pada Citra Sentinel-1 SAR Menggunakan U-Net Ringan Terkuantisasi INT8 untuk Inferensi Edge di Browser

*Draft laporan (single column, A4, spasi 1.15, margin 2.5 cm). Semua angka diambil dari `outputs/` hasil eksekusi nyata. Bagian bertanda [TIM] harus dilengkapi.*

## Abstrak

Tumpahan minyak di laut harus dipetakan secepat mungkin agar respons HSSE tepat sasaran. Kami melatih U-Net ringan (1,94 juta parameter) untuk segmentasi biner oil spill pada 3.354 patch Sentinel-1A dari dataset SOS. Model dievaluasi pada 839 patch test yang sama sekali tidak disentuh selama training dan pemilihan model. Hasilnya: Dice 0,855, IoU 0,746, precision 0,806, recall 0,910, dan PR-AUC 0,936. Angka ini jauh di atas baseline dark-spot thresholding (Dice 0,726).

Model dikuantisasi ke INT8 (QDQ) sehingga ukurannya turun dari 7,77 MB menjadi 2,01 MB, dengan penurunan Dice hanya 0,0002. Inferensinya berjalan di browser lewat onnxruntime-web (WASM) dengan latency ±104–122 ms per patch 256×256 pada laptop uji (4 thread), tanpa server GPU.

## 1. Pendahuluan

- **Urgensi operasional (HSSE):** kebocoran pipa bawah laut atau tanker perlu dipetakan sebelum mencemari pesisir. SAR bisa mengamati laut siang-malam dan menembus awan, dan slick minyak tampak sebagai area gelap karena meredam gelombang kapiler.
- **State of the art:** [TIM] Bandingkan dengan rujukan di README, bagian "Referensi kandidat". Baca paper-nya, lalu catat metode, dataset, dan metrik masing-masing. Hanya bandingkan angka yang dievaluasi pada dataset dan split yang sama; kalau berbeda, tulis perbedaannya secara eksplisit.
- **Kontribusi / novelty:**
  1. Pipeline yang diaudit: pasangan citra-mask, duplikat dengan 8 variasi rotasi/flip, dan kebocoran antar split.
  2. Model ringan terkuantisasi INT8 berukuran 2 MB yang divalidasi pada test set.
  3. Inferensi client-side di browser yang diuji langsung.

## 2. Metodologi

### 2.1 Dataset & audit

- **Sumber:** dataset SOS di Kaggle (CC BY 4.0), berisi 8.070 pasangan PNG 256×256 dari PALSAR (Gulf of Mexico) dan Sentinel-1A (Persian Gulf).
- **Hasil audit:**
  - Semua pasangan citra-mask cocok.
  - Citra berformat grayscale yang disimpan sebagai RGB.
  - Label train mengandung ±2,5% piksel bernilai antara, lalu dibinarisasi dengan aturan ≥128.
  - Tidak ada duplikat eksak.
  - Ada 9 citra test yang mirip citra train. Setelah dicek visual, citra-citra ini bukan salinan.

### 2.2 Pipeline

```
kagglehub → audit → pilih Sentinel-1 → split grup (train 2.850 / val 504 / test 839)
→ normalisasi (statistik train) → U-Net Lite + augmentasi dihedral → checkpoint terbaik (Dice val)
→ threshold dari val (0,45) → evaluasi test sekali → ONNX FP32 → FP16 / INT8 QDQ
→ pilih varian via val → onnxruntime-web (browser)
```

### 2.3 Arsitektur & training

- **Arsitektur:** U-Net 4 level dengan channel 16–256, memakai Conv-BN-ReLU, MaxPool, dan ConvTranspose.
- **Training:**
  - Loss 0,5·BCE + 0,5·Dice.
  - Optimizer AdamW (lr 1e-3) dengan cosine schedule, batch 16, 40 epoch, mixed precision.
  - Waktu training 10 menit di GPU Tesla T4. Checkpoint terbaik di epoch 37.

### 2.4 Optimasi efisiensi

- Model diekspor ke ONNX (opset 17).
- Konversi FP16 dengan `keep_io_types`.
- Kuantisasi INT8 statis QDQ per-channel, dikalibrasi dengan 200 citra train.
- Aturan pemilihan varian web: varian terkecil dengan penurunan Dice validation ≤0,005.

## 3. Hasil dan Pembahasan

### 3.1 Metrik segmentasi (test Sentinel, 839 citra)

| Model | Dice | IoU | Precision | Recall | PR-AUC |
|---|---|---|---|---|---|
| U-Net Lite (FP32) | 0,8547 | 0,7462 | 0,8058 | 0,9099 | 0,9361 |
| U-Net Lite (INT8, web) | 0,8545 | 0,7459 | 0,8062 | 0,9090 | – |
| Dark-spot threshold | 0,7259 | 0,5698 | 0,6669 | 0,7964 | – |
| Mask kosong | 0 | 0 | 0 | 0 | – |

- Mask kosong punya akurasi piksel 65,3% padahal tidak mendeteksi apa pun. Ini menunjukkan akurasi tidak layak dipakai sebagai metrik untuk kasus ini.
- Uji lintas sensor pada PALSAR (tidak dilatih): Dice 0,777, dibanding 0,641 untuk baseline dark-spot.
- Confusion matrix: lihat `outputs/eval/confusion_matrix_test.png`.

### 3.2 Efisiensi komputasi

| Varian | Ukuran | Latency CPU Colab (median) | Latency browser (laptop uji, WASM 4 thread) |
|---|---|---|---|
| FP32 | 7,77 MB | 64,4 ms | – |
| FP16 | 3,89 MB | 61,6 ms | – |
| INT8 | 2,01 MB | 72,5 ms (semua thread) / 50,8 ms (1 thread) | 104–122 ms |

Sebagai pembanding, PyTorch di GPU T4 butuh 2,7 ms. Artinya, inferensi di browser menukar kecepatan dengan tidak adanya biaya server GPU.

### 3.3 Visualisasi & analisis error

- Gambar: `outputs/eval/test_predictions_best_median_worst.png` dan `test_dice_distribution.png`.
- Dice per citra: median 0,797, dan 70 dari 805 citra Dice-nya <0,5.
- Pola kegagalan utama:
  - slick yang sangat kecil;
  - area gelap tipis yang tidak dilabeli (kemungkinan *look-alike*);
  - batas GT berupa poligon kasar, sehingga precision lebih rendah daripada recall.

## 4. Analisis Dampak Operasional (Pilar HSSE)

- **Kontribusi:**
  - Screening otomatis citra SAR untuk memprioritaskan area yang perlu diverifikasi.
  - Recall tinggi (0,91) cocok untuk tahap deteksi dini.
  - Model 2 MB bisa dijalankan di laptop tim respons tanpa server GPU.
- **Estimasi bisnis:** [TIM] Isi dengan sumber terverifikasi, misalnya biaya sewa GPU cloud dibanding biaya nol untuk inferensi di browser, atau waktu interpretasi manual per scene. **Jangan cantumkan angka tanpa sumber.** Penghematan di lapangan belum diukur dalam proyek ini.

## 5. Kesimpulan & Saran

- **Kesimpulan:** U-Net ringan yang dikuantisasi INT8 (2 MB) mencapai Dice 0,855 pada test Sentinel-1 dan berjalan di browser.
- **Saran:**
  - Tambahkan kelas *look-alike*.
  - Latih ulang pada data multi-region atau multi-sensor.
  - Uji pada scene Sentinel-1 berukuran penuh dengan tiling.
  - Validasi bersama operator.

## Daftar Pustaka

[TIM] Kelola dengan Mendeley/Zotero; minimal 8–10 entri. Kandidat yang sudah terverifikasi DOI-nya ada di README, dan dataset SOS juga wajib disitasi.

## Lampiran: Contribution Statement

Lihat `CONTRIBUTION_STATEMENT.md`.
