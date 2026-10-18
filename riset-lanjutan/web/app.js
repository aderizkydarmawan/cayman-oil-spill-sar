// Pantau Bercak Minyak — peta lintasan statis (data dari scripts/26_ekspor_web.py)
const fmt = (x, d = 1) => Number(x).toFixed(d).replace(".", ",");
const BLN = "Jan Feb Mar Apr Mei Jun Jul Agu Sep Okt Nov Des".split(" ");
const tgl = s => { const [y, m, d] = s.split("-"); return `${+d} ${BLN[m - 1]} ${y}`; };
const JENIS = { kejadian: "kejadian nyata", biasa: "hari biasa", tenang: "laut tenang" };
const alasanAwam = a => a.split("; ").map(x => x.replace(/^↑ /, "menaikkan skor: ").replace(/^↓ /, "menurunkan skor: ")).join("<br>");

const map = L.map("map", { zoomControl: true });
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 15, attribution: "© OpenStreetMap" }).addTo(map);
let radar = null, optik = null, bercak = null, data = null, aktif = null;
const elDaftar = document.getElementById("daftar"), elInfo = document.getElementById("info");
const tbody = document.querySelector("#tabel tbody"), cbPalsu = document.getElementById("tampil-palsu"), cbOptik = document.getElementById("tampil-optik"), elOptik = document.getElementById("label-optik");

fetch("data/kejadian.json").then(r => r.json()).then(j => {
  data = j;
  j.lintasan.forEach((l, i) => {
    const b = document.createElement("button");
    b.className = "lin"; b.dataset.i = i;
    b.innerHTML = `<b>${l.judul}</b><span class="badge ${l.jenis}">${JENIS[l.jenis]}</span>
      <span class="meta">${tgl(l.tanggal)}, ${l.n_bercak} bercak, ${l.n_perlu_dicek} prioritas tinggi</span>`;
    b.onclick = () => pilih(i);
    elDaftar.appendChild(b);
  });
  pilih(0);
});

function gaya(f) {
  const cek = f.properties.status === "prioritas tinggi";
  return { color: cek ? "#dc2626" : "#94a3b8", weight: cek ? 2 : 1.5, fillColor: cek ? "#ef4444" : "#cbd5e1", fillOpacity: cek ? .45 : .3 };
}

function pilih(i) {
  const l = data.lintasan[i]; aktif = i;
  document.querySelectorAll(".lin").forEach(b => b.classList.toggle("aktif", +b.dataset.i === i));
  elInfo.innerHTML = `<b>${l.judul} — ${tgl(l.tanggal)}</b><br><span class="muted">${l.keterangan}</span>
    ${l.laut_tenang ? '<br><b style="color:var(--warn)">Laut sangat tenang saat satelit lewat: hampir semua bercak belum bisa dinilai, perlu dilihat manusia.</b>' : ""}
    <div class="angka"><span>${l.n_bercak} bercak</span><span>${l.n_perlu_dicek} prioritas tinggi</span><span>${fmt(l.luas_total_km2)} km² total</span>
    <span>${Math.round(l.cakupan_laut * 100)}% laut terpotret</span>${l.n_dekat_mangrove ? `<span>${l.n_dekat_mangrove} dekat mangrove (≤5 km)</span>` : ""}</div>
    ${l.sumber ? `<span class="small">Berita/laporan kejadian: <a href="${l.sumber}" target="_blank" rel="noopener">buka sumber</a></span>` : ""}`;
  if (radar) map.removeLayer(radar);
  radar = L.imageOverlay(`data/${l.kunci}.png`, l.bounds, { opacity: .9 }).addTo(map);
  if (optik) { map.removeLayer(optik); optik = null; }
  elOptik.style.display = l.s2 ? "block" : "none";
  if (l.s2) {
    elOptik.querySelector("span").textContent = `Tampilkan foto satelit biasa Sentinel-2 (${l.s2.tanggal.map(tgl).join(", ")}; tertutup awan ±${Math.round(l.s2.awan_persen)}%)`;
    if (cbOptik.checked) optik = L.imageOverlay(`data/${l.kunci}_s2.png`, l.bounds, { opacity: 1 }).addTo(map);
  }
  map.fitBounds(l.bounds);
  fetch(`data/${l.kunci}.geojson`).then(r => r.json()).then(g => { gambar(g); });
}

function gambar(g) {
  if (bercak) map.removeLayer(bercak);
  const fs = g.features.filter(f => cbPalsu.checked || f.properties.status === "prioritas tinggi");
  bercak = L.geoJSON({ type: "FeatureCollection", features: fs }, {
    style: gaya,
    onEachFeature: (f, ly) => {
      const p = f.properties;
      ly.bindPopup(`<b>Bercak ${p.id}</b> — ${p.status}<br>Luas ${fmt(p.luas_km2, 2)} km² · ${fmt(p.jarak_pantai_km)} km dari pantai<br>
        ${fmt(p.kontras_db)} dB lebih gelap dari laut sekitar<br>Skor ${fmt(p.skor, 2)} dari 1 (prioritas tinggi bila ≥ ${fmt(data.ambang, 2)} atau luas ≥10 km²)
        ${p.alasan ? `<br><span class="small"><b>Alasan utama skor</b><br>${alasanAwam(p.alasan)}</span>` : ""}
        ${p.mangrove_km !== null && p.mangrove_km <= 5 ? `<br><b style="color:#15803d">Mangrove ${fmt(p.mangrove_km)} km: pesisir sensitif, sebaiknya didahulukan.</b>` : ""}
        ${p.hujan_mmjam >= 1 ? `<br><b style="color:var(--warn)">Hujan ${fmt(p.hujan_mmjam)} mm/jam saat satelit lewat: bercak ini bisa jadi jejak hujan, bukan minyak.</b>` : ""}`);
      f._ly = ly;
    }
  }).addTo(map);
  tbody.innerHTML = "";
  if (!fs.length) { tbody.innerHTML = '<tr><td colspan="6" style="text-align:center">Tidak ada bercak terdeteksi di lintasan ini.</td></tr>'; return; }
  fs.forEach(f => {
    const p = f.properties, tr = document.createElement("tr");
    tr.innerHTML = `<td>${p.id}</td><td><span class="tag ${p.status === "prioritas tinggi" ? "cek" : "palsu"}">${p.status}</span></td>
      <td>${fmt(p.luas_km2, 2)}</td><td>${fmt(p.jarak_pantai_km)}</td><td>${fmt(p.kontras_db)}</td><td>${fmt(p.skor, 2)}</td>`;
    tr.onclick = () => { map.fitBounds(f._ly.getBounds(), { maxZoom: 12 }); f._ly.openPopup(); };
    tbody.appendChild(tr);
  });
}
cbPalsu.onchange = () => pilih(aktif);
cbOptik.onchange = () => pilih(aktif);
