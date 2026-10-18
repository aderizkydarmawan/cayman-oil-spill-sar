# Riset lanjutan: Pantau Bercak Minyak

Lanjutan CAYMAN dari potongan citra ke **citra Sentinel-1 utuh di perairan Indonesia**: menandai dugaan bercak minyak, mengurutkan prioritas cek, dan menyatakan terang seberapa jauh hasilnya bisa dipercaya.

- Situs: https://pantau-bercak-minyak.vercel.app
- Laporan: [`laporan/Laporan_Riset_Pantau_Bercak_Minyak.pdf`](laporan/Laporan_Riset_Pantau_Bercak_Minyak.pdf) (dan `.docx`)
- Contoh laporan lapangan per lintasan: [`laporan/contoh_laporan_tumpahan.pdf`](laporan/contoh_laporan_tumpahan.pdf)
- Lembar penilaian praktisi (40 bercak): [`laporan/lembar_penilaian_bercak.pdf`](laporan/lembar_penilaian_bercak.pdf)

Status: prototipe riset dengan data satelit publik. Bukan produk atau pernyataan resmi Pertamina, dan belum divalidasi di lapangan.

## Hasil utama

| Pertanyaan | Hasil |
|---|---|
| Berapa banyak tumpahan yang tertangkap? | 73% (Yang & Singha, 2.630 tumpahan), 81% (uji independen Trujillo, 670 tumpahan); presisi piksel 92% |
| Seberapa sering alarm palsu? | 0,05 per citra di laut berangin; median 8 bercak per lintasan di perairan Indonesia hari biasa |
| Apakah skor prioritas bisa membuang look-alike? | Tidak lulus uji independen (luas minyak berprioritas tinggi 76%, target 90%), jadi hanya dipakai untuk urutan |
| Seberapa besar peran hujan? | Kecil: 11% (Balikpapan) dan 1,5% (Karawang) bercak hari biasa terjadi saat hujan |
| Apakah sebaran minyak bisa diprakirakan (OpenDrift)? | Belum: kalah dari tebakan "bercak diam" di Karawang 2019 (5% vs 18%) dan Balikpapan 2018 (4% vs 47%) |

Daftar lengkap hal yang belum pasti ada di bagian 5 laporan dan di situs (bagian "Yang belum pasti").

## Isi folder

- `scripts/`: alur 01–33, berurutan per tahap (unduh citra GEE, inferensi, alarm palsu, angin, uji kejadian, uji Trujillo, skor prioritas v2, SHAP, hujan GPM, mangrove + Sentinel-2, OpenDrift, ekspor situs). `situs.py` menyimpan konfigurasi lokasi; `saring.py` dan `fitur_objek.py` dipakai bersama.
- `web/`: situs statis (Leaflet, tanpa server) yang dideploy ke Vercel.
- `laporan/`: laporan riset, contoh laporan lapangan, dan lembar penilaian.
- `kejadian_kandidat.csv`: 14 kejadian tumpahan yang dicoba, beserta sumbernya.

Citra mentah (±15 GB), model terlatih, dan kunci lembar penilaian tidak diunggah. Script lembar penilaian juga ditahan sampai penilaian praktisi selesai, supaya penilaian tetap buta.

## Menjalankan ulang

Butuh akun Google Earth Engine; isi variabel lingkungan `EE_PROJECT` dengan ID project GEE Anda. Juga butuh Python 3.12, `earthengine-api`, `rasterio`, `onnxruntime`, `scikit-learn`, `shap`, `opendrift`. Jalankan dari folder induk yang berisi `scripts/`, misalnya:

```
python scripts/02_unduh_citra.py 2018-04-01 20
python scripts/03_inferensi.py data/s1_vv_db_2018-04-01_20m.tif fixed:-32:-17
```

Setiap angka yang dilaporkan punya ID run di log eksperimen (hash data, parameter, versi paket).
