// Kalkulator efisiensi biaya & matriks risiko HSSE (5x5, Likelihood x Severity).
// Semua angka default adalah ASUMSI ILUSTRATIF yang bisa diubah pengguna, bukan data kontrak nyata.
"use strict";

const HSE = (() => {
  const rp = (x) => "Rp " + Math.round(x).toLocaleString("id-ID");
  const rpShort = (x) => (Math.abs(x) >= 1e9 ? `Rp ${(x / 1e9).toLocaleString("id-ID", { maximumFractionDigits: 2 })} M` : `Rp ${(x / 1e6).toLocaleString("id-ID", { maximumFractionDigits: 1 })} jt`);

  // Bahaya pada kegiatan pemantauan/pengecekan tumpahan. L = kemungkinan (1-5), S = keparahan (1-5).
  // exp: true bila risikonya sebanding dengan jam paparan personel di lapangan (turun bila pengecekan lapangan berkurang).
  const HAZARDS = [
    { h: "Paparan uap hidrokarbon (VOC, benzena, H₂S) saat inspeksi jarak dekat", S: 4, L: 3, exp: true },
    { h: "Kecelakaan penerbangan pengintaian (helikopter/pesawat)", S: 5, L: 2, exp: true },
    { h: "Insiden kapal patroli: orang jatuh ke laut, tabrakan, cuaca buruk", S: 4, L: 3, exp: true },
    { h: "Kebakaran/ledakan di dekat minyak segar (uap mudah terbakar)", S: 5, L: 2, exp: true },
    { h: "Kelelahan kru akibat patroli panjang & operasi malam", S: 3, L: 4, exp: true },
    { h: "Tumpahan terlambat diketahui (malam/berawan) sehingga meluas", S: 4, L: 3, exp: false, cv: -1,
      note: "SAR menembus awan & bekerja malam hari; setiap citra baru langsung dianalisis" },
    { h: "Risiko BARU: model salah deteksi (look-alike) atau melewatkan slick", S: 3, L: 0, L2: 3, exp: false, isNew: true,
      note: "dikendalikan dengan verifikasi analis & sortie konfirmasi" },
  ];
  const level = (r) => (r >= 15 ? ["Ekstrem", "ext"] : r >= 10 ? ["Tinggi", "high"] : r >= 5 ? ["Sedang", "med"] : ["Rendah", "low"]);

  let root;
  function setup(el) {
    root = el;
    el.querySelectorAll("input,select").forEach((i) => i.addEventListener("input", update));
    update();
  }
  const v = (id) => +root.querySelector("#" + id).value;

  function update() {
    // --- Biaya per bulan ---
    const sorties = v("c-sorties"), hrs = v("c-hours"), costHr = v("c-costhr") * 1e6, crew = v("c-crew");
    const confirmPct = v("c-confirm") / 100, analystHr = v("c-analyst"), analystCost = v("c-analystcost") * 1e3, scenes = v("c-scenes");
    const conv = sorties * hrs * costHr;
    const cvSorties = sorties * confirmPct;                         // sortie konfirmasi saat model memberi alarm
    const cvCost = cvSorties * hrs * costHr + scenes * analystHr * analystCost;   // citra Sentinel-1 gratis; komputasi di browser ≈ Rp 0
    const save = conv - cvCost, savePct = conv ? (100 * save) / conv : 0;
    const expConv = sorties * hrs * crew, expCv = cvSorties * hrs * crew, expRed = expConv ? 1 - expCv / expConv : 0;

    root.querySelector("#c-out").innerHTML = `
      <div class="cost-bars">
        ${bar("Patroli konvensional", conv, conv, "conv")}
        ${bar("Dengan CV + verifikasi", cvCost, conv, "cv")}
      </div>
      <div class="cost-kpis">
        <div><span>Penghematan per bulan</span><b>${rpShort(save)}</b><em>${savePct.toFixed(0)}%</em></div>
        <div><span>Penghematan per tahun</span><b>${rpShort(save * 12)}</b></div>
        <div><span>Jam paparan personel di lapangan</span><b>${expConv.toFixed(0)} → ${expCv.toFixed(0)} jam</b><em>−${(100 * expRed).toFixed(0)}%</em></div>
        <div><span>Biaya per citra yang dianalisis</span><b>${rp((scenes * analystHr * analystCost) / Math.max(scenes, 1))}</b></div>
      </div>
      <div class="formula">
        <b>Rincian perhitungan</b>
        <code>Konvensional = ${sorties} sortie × ${hrs} jam × ${rp(costHr)} = ${rp(conv)}</code>
        <code>Dengan CV = ${(cvSorties).toLocaleString("id-ID", { maximumFractionDigits: 1 })} sortie konfirmasi × ${hrs} jam × ${rp(costHr)} + ${scenes} citra × ${analystHr} jam × ${rp(analystCost)} = ${rp(cvCost)}</code>
        <code>Jam paparan = sortie × durasi × ${crew} personel → ${expConv.toFixed(0)} jam vs ${expCv.toFixed(0)} jam per bulan</code>
      </div>`;

    // --- Matriks risiko: sebelum vs sesudah CV ---
    const drop = expRed >= 0.75 ? 2 : expRed >= 0.4 ? 1 : 0;     // turunkan kemungkinan sesuai pengurangan paparan
    const rows = HAZARDS.map((z) => {
      const L1 = z.L, L2 = z.isNew ? z.L2 : z.exp ? Math.max(1, z.L - drop) : Math.max(1, z.L + (z.cv || 0));
      return { ...z, L1, L2, R1: L1 * z.S, R2: L2 * z.S };
    });
    const tot1 = rows.reduce((a, r) => a + r.R1, 0), tot2 = rows.reduce((a, r) => a + r.R2, 0);
    root.querySelector("#risk-table").innerHTML = `
      <thead><tr><th>Bahaya</th><th>S</th><th>Sebelum (L×S)</th><th>Sesudah CV (L×S)</th></tr></thead>
      <tbody>${rows.map((r, i) => `<tr>
        <td><i class="hz">${i + 1}</i>${r.h}${r.note ? `<small>${r.note}</small>` : ""}</td><td>${r.S}</td>
        <td>${r.isNew ? "–" : cell(r.L1, r.S)}</td><td>${cell(r.L2, r.S)}</td></tr>`).join("")}</tbody>
      <tfoot><tr><td colspan="2">Total skor risiko</td><td><b>${tot1}</b></td><td><b>${tot2}</b> <em>(−${((100 * (tot1 - tot2)) / tot1).toFixed(0)}%)</em></td></tr></tfoot>`;
    matrix(rows);
    root.querySelector("#risk-note").textContent =
      `Pengurangan jam paparan ${(100 * expRed).toFixed(0)}% menurunkan kemungkinan (L) bahaya berbasis paparan sebanyak ${drop} tingkat. ` +
      `Keparahan (S) tidak berubah karena konsekuensinya tetap sama bila kejadian terjadi.`;
  }

  const cell = (L, S) => { const r = L * S, [t, c] = level(r); return `<span class="rk ${c}">${L}×${S} = ${r} · ${t}</span>`; };
  const bar = (label, x, max, cls) => `<div class="cbar"><span>${label}</span><div><i class="${cls}" style="width:${Math.max(2, (100 * x) / max)}%"></i></div><b>${rpShort(x)}</b></div>`;

  function matrix(rows) {
    const g = root.querySelector("#risk-matrix");
    let h = `<div class="rm-y">Kemungkinan (L) →</div><div class="rm-grid">`;
    for (let L = 5; L >= 1; L--) for (let S = 1; S <= 5; S++) {
      const [, c] = level(L * S);
      const before = rows.map((r, i) => (!r.isNew && r.L1 === L && r.S === S ? `<i class="dot b">${i + 1}</i>` : "")).join("");
      const after = rows.map((r, i) => (r.L2 === L && r.S === S ? `<i class="dot a">${i + 1}</i>` : "")).join("");
      h += `<div class="rm ${c}" title="L${L} × S${S} = ${L * S}">${before}${after}</div>`;
    }
    g.innerHTML = h + `</div><div class="rm-x">Keparahan (S) →</div>`;
  }

  return { setup, update };
})();
