// Inferensi segmentasi oil spill di browser dengan onnxruntime-web (WASM), beberapa model (ML & DL).
// Daftar model + kontrak input/output dibaca dari model/models.json (dihasilkan notebook Colab, bagian 18).
"use strict";
ort.env.wasm.wasmPaths = "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.30.0/dist/";

const $ = (id) => document.getElementById(id);
const S = 256;
const FAMILY = { baseline: "Baseline", machine_learning: "Machine Learning", deep_learning: "Deep Learning" };
const fmt = (x, d = 3) => (x == null ? "–" : x.toLocaleString("id-ID", { minimumFractionDigits: d, maximumFractionDigits: d }));

const statusEl = $("status");
new MutationObserver(() => {
  const t = statusEl.textContent;
  $("led").className = "led" + (t === "siap" || t === "selesai" ? " ready" : /^(inferensi|memuat)/.test(t) ? " busy" : "");
}).observe(statusEl, { childList: true, characterData: true, subtree: true });

let REG, model, threshold, last = null;          // last = {gray, gt, refDice, origW, origH, runs:{id:{prob,median,first}}}
const sessions = {};

async function getSession(m) {
  if (!sessions[m.id]) sessions[m.id] = ort.InferenceSession.create(`model/${m.file}`, { executionProviders: ["wasm"], graphOptimizationLevel: "all" });
  return sessions[m.id];
}

async function init() {
  try {
    REG = await (await fetch("model/models.json", { cache: "no-cache" })).json();
    buildModelPicker();
    buildResults();
    await selectModel(REG.default);
    $("backend").textContent = `onnxruntime-web ${ort.env.versions?.web ?? ""} · WASM · ${self.crossOriginIsolated ? "multi-thread" : "1 thread"}`;
    await loadSamples();
  } catch (e) {
    $("status").textContent = "gagal memuat model (koneksi lambat?)";
    $("status").insertAdjacentHTML("afterend", ` <button class="btn small ghost" onclick="location.reload()">Coba lagi</button>`);
    console.error(e);
  }
}

// ---------- pemilihan model ----------
function buildModelPicker() {
  const box = $("model-picker");
  Object.keys(FAMILY).forEach((fam) => {
    const ms = REG.models.filter((m) => m.family === fam);
    if (!ms.length) return;
    box.insertAdjacentHTML("beforeend", `<div class="mp-group"><span class="fam ${fam}">${FAMILY[fam]}</span></div>`);
    const g = box.lastElementChild;
    ms.forEach((m) => {
      const b = document.createElement("button");
      b.className = "mp"; b.dataset.id = m.id;
      b.innerHTML = `<b>${m.name}</b><small>Dice ${fmt(m.metrics_test_sentinel.dice)} · ${m.size_mb < 0.1 ? "<0,1" : fmt(m.size_mb, 1)} MB</small>`;
      b.onclick = () => selectModel(m.id, true);
      g.appendChild(b);
    });
  });
}

async function selectModel(id, rerun) {
  model = REG.models.find((m) => m.id === id);
  document.querySelectorAll(".mp").forEach((b) => b.classList.toggle("active", b.dataset.id === id));
  threshold = model.threshold;
  $("thr").value = threshold; $("thr-val").textContent = threshold.toFixed(2);
  $("thr").disabled = model.id === "dark_spot";
  $("model-desc").innerHTML = `<b>${model.name}</b> · ${FAMILY[model.family]}<br>${model.description}`;
  $("model-size").textContent = `${fmt(model.size_mb, 2)} MB · ${model.file}`;
  $("status").textContent = "memuat model…";
  await getSession(model);
  $("status").textContent = "siap";
  if (rerun && last) { await runModel(model); render(); $("status").textContent = "selesai"; }
}

// ---------- input ----------
async function loadSamples() {
  const samples = await (await fetch("samples/samples.json")).json();
  const box = $("sample-buttons");
  samples.forEach((s, i) => {
    const b = document.createElement("button");
    b.innerHTML = `<img src="samples/${s.image}" alt=""><span>Sampel ${i + 1}<small>${(s.note || "").split(" (")[0]}</small></span>`;
    b.title = s.source || s.image;
    b.onclick = () => {
      box.querySelectorAll("button").forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      runOnUrl(`samples/${s.image}`, s.mask ? `samples/${s.mask}` : null, s.dice_python);
    };
    box.appendChild(b);
  });
}

const loadImage = (url) => new Promise((res, rej) => { const im = new Image(); im.onload = () => res(im); im.onerror = rej; im.src = url; });

// Citra -> grayscale 256x256 (rata-rata RGB; sama dengan kanal R untuk citra dataset yang R=G=B)
function toGray(img) {
  const c = document.createElement("canvas"); c.width = c.height = S;
  const ctx = c.getContext("2d", { willReadFrequently: true });
  ctx.imageSmoothingQuality = "high"; ctx.drawImage(img, 0, 0, S, S);
  const d = ctx.getImageData(0, 0, S, S).data, g = new Uint8ClampedArray(S * S);
  for (let i = 0; i < S * S; i++) g[i] = Math.round((d[4 * i] + d[4 * i + 1] + d[4 * i + 2]) / 3);
  return g;
}

function toTensor(gray, m) {
  const x = new Float32Array(S * S), { mean, std } = REG.preprocessing;
  for (let i = 0; i < S * S; i++) x[i] = m.input === "raw" ? gray[i] : (gray[i] / 255 - mean) / std;
  return new ort.Tensor("float32", x, [1, 1, S, S]);
}

async function infer(gray, m, runs = 4) {
  const sess = await getSession(m), feeds = { [sess.inputNames[0]]: toTensor(gray, m) }, times = [];
  let out;
  for (let r = 0; r < runs; r++) { const t0 = performance.now(); out = await sess.run(feeds); times.push(performance.now() - t0); }
  const y = out[sess.outputNames[0]].data, prob = new Float32Array(y.length);
  for (let i = 0; i < y.length; i++) prob[i] = m.output === "logits" ? 1 / (1 + Math.exp(-y[i])) : y[i];
  const warm = times.slice(1).sort((a, b) => a - b);
  return { prob, first: times[0], median: warm.length ? warm[Math.floor(warm.length / 2)] : times[0] };
}

async function runModel(m) {
  $("status").textContent = `inferensi ${m.name}…`;
  last.runs[m.id] = await infer(last.gray, m);
}

async function runOnUrl(url, maskUrl, refDice) {
  $("status").textContent = "inferensi…";
  const img = await loadImage(url), gray = toGray(img);
  let gt = null;
  if (maskUrl) { const g = toGray(await loadImage(maskUrl)); gt = new Uint8Array(S * S); for (let i = 0; i < S * S; i++) gt[i] = g[i] >= 128 ? 1 : 0; }
  last = { gray, gt, refDice, origW: img.naturalWidth, origH: img.naturalHeight, runs: {} };
  $("compare").hidden = true;
  await runModel(model);
  render();
  $("status").textContent = "selesai";
}

// ---------- tampilan hasil ----------
const mpp = () => { const px = parseFloat($("px").value); return px > 0 && last ? (px * last.origW) / S : null; };   // meter per piksel grid 256

function predMask(prob, thr) { const p = new Uint8Array(S * S); for (let i = 0; i < S * S; i++) p[i] = prob[i] >= thr ? 1 : 0; return p; }
function diceOf(pred, gt) {
  let tp = 0, fp = 0, fn = 0;
  for (let i = 0; i < S * S; i++) { if (pred[i] && gt[i]) tp++; else if (pred[i]) fp++; else if (gt[i]) fn++; }
  const d = 2 * tp + fp + fn; return d === 0 ? 1 : (2 * tp) / d;
}
function putImage(cv, fn) {
  const ctx = cv.getContext("2d"), im = ctx.createImageData(S, S);
  for (let i = 0; i < S * S; i++) { const [r, g, b] = fn(i); im.data[4 * i] = r; im.data[4 * i + 1] = g; im.data[4 * i + 2] = b; im.data[4 * i + 3] = 255; }
  ctx.putImageData(im, 0, 0);
}

// Kanvas resolusi tinggi agar garis poligon & label tajam
function drawDetection(cv, gray, pred, slicks, opts) {
  const k = cv.width / S, ctx = cv.getContext("2d");
  const base = document.createElement("canvas"); base.width = base.height = S;
  putImage(base, (i) => (opts.fill && pred[i] ? [0.5 * gray[i] + 0.5 * 30, 0.5 * gray[i] + 0.5 * 20, 0.5 * gray[i] + 0.5 * 60] : [gray[i], gray[i], gray[i]]));
  ctx.imageSmoothingEnabled = false; ctx.drawImage(base, 0, 0, cv.width, cv.height);
  if (opts.fill) { // kilau minyak (iridescent) di area terdeteksi
    const sheen = document.createElement("canvas"); sheen.width = sheen.height = S; const sc = sheen.getContext("2d"), im = sc.createImageData(S, S);
    for (let i = 0; i < S * S; i++) if (pred[i]) {
      const x = i % S, y = (i / S) | 0, t = 0.5 + 0.5 * Math.sin((x + 0.6 * y) / 2.6 + 2.2 * Math.sin(y / 13 + x / 29));   // pita tipis seperti interferensi lapisan tipis
      const c = [[124, 58, 237], [219, 39, 119], [245, 158, 11], [16, 185, 129], [14, 165, 233]], f = t * 4, j = Math.min(3, f | 0), u = f - j;
      im.data.set([c[j][0] + (c[j + 1][0] - c[j][0]) * u, c[j][1] + (c[j + 1][1] - c[j][1]) * u, c[j][2] + (c[j + 1][2] - c[j][2]) * u, 78], 4 * i);
    }
    sc.putImageData(im, 0, 0); ctx.imageSmoothingEnabled = true; ctx.drawImage(sheen, 0, 0, cv.width, cv.height);
  }
  if (opts.poly) slicks.forEach((s) => {
    ctx.beginPath(); s.poly.forEach(([x, y], i) => (i ? ctx.lineTo(x * k, y * k) : ctx.moveTo(x * k, y * k))); ctx.closePath();
    ctx.lineWidth = 2.5 * (k / 2); ctx.strokeStyle = "#fde047"; ctx.stroke();
    ctx.lineWidth = 1 * (k / 2); ctx.strokeStyle = "#7c2d12"; ctx.stroke();
    s.poly.forEach(([x, y]) => { ctx.fillStyle = "#fde047"; ctx.fillRect(x * k - 2, y * k - 2, 4, 4); });
  });
  if (opts.labels) slicks.slice(0, 12).forEach((s) => {
    const x = s.cx * k, y = s.cy * k; ctx.beginPath(); ctx.arc(x, y, 11, 0, 7); ctx.fillStyle = "#0f172a"; ctx.fill();
    ctx.fillStyle = "#fff"; ctx.font = "700 12px Inter, sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(s.no, x, y + 0.5);
  });
}

function render() {
  if (!last || !last.runs[model.id]) return;
  const { gray, gt, refDice } = last, { prob, first, median } = last.runs[model.id];
  const pred = predMask(prob, threshold), m = mpp(), mEff = m || 10;
  const slicks = Geo.slicks(pred, S, { minPx: +$("minpx").value });
  last.slicks = slicks; last.pred = pred;
  const opts = { fill: $("ly-fill").checked, poly: $("ly-poly").checked, labels: $("ly-label").checked };

  putImage($("c-input"), (i) => [gray[i], gray[i], gray[i]]);
  drawDetection($("c-overlay"), gray, pred, slicks, opts);
  putImage($("c-prob"), (i) => { const p = prob[i]; return [255 - 170 * p, 255 - 200 * Math.max(0, p - 0.2), 255 - 80 * p]; });
  $("fig-gt").hidden = !gt;
  if (gt) putImage($("c-gt"), (i) => (gt[i] ? [30, 27, 75] : [241, 245, 249]));

  const fg = pred.reduce((a, b) => a + b, 0);
  $("area").innerHTML = m ? `<b>${fmt((fg * m * m) / 1e6)} km²</b><small>${(100 * fg / (S * S)).toFixed(1)}% citra · ${slicks.length} slick</small>`
                          : `<b>${(100 * fg / (S * S)).toFixed(1)}% citra</b><small>${slicks.length} slick · isi resolusi piksel untuk km²</small>`;
  $("latency").innerHTML = `<b>${median.toFixed(0)} ms</b><small>median 3 run · run pertama ${first.toFixed(0)} ms</small>`;
  $("dice-row").hidden = !gt;
  if (gt) {
    $("dice").textContent = fmt(diceOf(pred, gt), 4);
    $("dice-ref").textContent = model.id === "unet_lite" && refDice != null && Math.abs(threshold - model.threshold) < 1e-9 ? `referensi Python: ${fmt(refDice, 4)}` : "";
  }
  renderSlicks(slicks, gray, pred, m);
  Sim.setSlicks(slicks, S, m, gray);
}

function renderSlicks(slicks, gray, pred, m) {
  const box = $("slick-list");
  if (!slicks.length) { box.innerHTML = `<p class="muted">Tidak ada slick di atas ambang ukuran minimum. Laut tampak bersih pada citra ini.</p>`; return; }
  box.innerHTML = "";
  slicks.slice(0, 8).forEach((s) => {
    const [x0, y0, x1, y1] = s.bbox, pad = 8, bx0 = Math.max(0, x0 - pad), by0 = Math.max(0, y0 - pad), bw = Math.min(S, x1 + pad) - bx0, bh = Math.min(S, y1 + pad) - by0;
    const side = Math.max(bw, bh), cv = document.createElement("canvas"); cv.width = cv.height = 160;
    const full = document.createElement("canvas"); full.width = full.height = S * 2;
    drawDetection(full, gray, pred, [s], { fill: true, poly: true, labels: false });
    const ctx = cv.getContext("2d"); ctx.fillStyle = "#0f172a"; ctx.fillRect(0, 0, 160, 160);
    ctx.drawImage(full, bx0 * 2, by0 * 2, side * 2, side * 2, 0, 0, 160, 160);
    const area = m ? `${fmt((s.px * m * m) / 1e6)} km²` : `${s.px} piksel`, per = m ? `${fmt((s.perimPx * m) / 1000, 2)} km` : `${s.perimPx.toFixed(0)} px`;
    const card = document.createElement("div"); card.className = "slick";
    card.innerHTML = `<i class="no">${s.no}</i><div class="info"><b>Slick ${s.no}</b><span>Luas <b>${area}</b></span><span>Keliling <b>${per}</b></span><span>Titik poligon <b>${s.poly.length}</b></span></div>`;
    card.prepend(cv); box.appendChild(card);
  });
  if (slicks.length > 8) box.insertAdjacentHTML("beforeend", `<p class="muted">+${slicks.length - 8} slick kecil lainnya (ada di GeoJSON).</p>`);
}

// ---------- bandingkan semua model ----------
async function compareAll() {
  if (!last) { $("status").textContent = "pilih sampel dulu"; return; }
  const box = $("compare"); box.hidden = false; box.innerHTML = `<p class="muted">Menjalankan ${REG.models.length} model…</p>`;
  for (const m of REG.models) if (!last.runs[m.id]) await runModel(m);
  box.innerHTML = "";
  REG.models.forEach((m) => {
    const r = last.runs[m.id], pred = predMask(r.prob, m.threshold), sl = Geo.slicks(pred, S, { minPx: +$("minpx").value });
    const cv = document.createElement("canvas"); cv.width = cv.height = 256;
    drawDetection(cv, last.gray, pred, sl, { fill: true, poly: true, labels: false });
    const fig = document.createElement("figure"); fig.className = "card cmp" + (m.id === model.id ? " on" : "");
    const d = last.gt ? `Dice ${fmt(diceOf(pred, last.gt), 3)}` : `${sl.length} slick`;
    fig.innerHTML = `<figcaption><span class="fam ${m.family}">${FAMILY[m.family]}</span><b>${m.name}</b><small>${d} · ${r.median.toFixed(0)} ms</small></figcaption>`;
    fig.prepend(cv); fig.onclick = () => selectModel(m.id, true); box.appendChild(fig);
  });
  $("status").textContent = "selesai";
}

function downloadGeoJSON() {
  if (!last?.slicks) return;
  const gj = Geo.toGeoJSON(last.slicks, S, mpp(), { model: model.name, threshold, generated: new Date().toISOString() });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([JSON.stringify(gj, null, 1)], { type: "application/geo+json" }));
  a.download = "cayman_oil_spill_polygons.geojson"; a.click();
}

// ---------- tabel performa dari registry ----------
function buildResults() {
  const best = Math.max(...REG.models.map((m) => m.metrics_test_sentinel.dice));
  $("results-body").innerHTML = REG.models.map((m) => {
    const t = m.metrics_test_sentinel;
    return `<tr class="${t.dice === best ? "hl" : ""}"><td><span class="fam ${m.family}">${FAMILY[m.family]}</span>${m.name}</td>
      <td>${fmt(t.dice, 4)}</td><td>${fmt(t.iou, 4)}</td><td>${fmt(t.precision, 3)}</td><td>${fmt(t.recall, 3)}</td>
      <td>${fmt(m.metrics_palsar_cross_sensor.dice, 3)}</td><td>${m.size_mb < 0.1 ? "<0,1" : fmt(m.size_mb, 2)} MB</td>
      <td>${fmt(m.cpu_latency_ms_colab.one_thread.median, 0)} ms</td></tr>`;
  }).join("");
  $("chart").innerHTML = REG.models.map((m) => `<div class="bar-row"><span>${m.name}</span><div class="bar"><i class="${m.family}" style="width:${(100 * m.metrics_test_sentinel.dice).toFixed(1)}%"></i></div><b>${fmt(m.metrics_test_sentinel.dice, 3)}</b></div>`).join("");
  const top = REG.models.find((m) => m.metrics_test_sentinel.dice === best);
  $("kpi-dice").textContent = fmt(best, 3); $("kpi-dice-lbl").textContent = `Dice test terbaik (${top.name.split(" ")[0]})`;
  $("kpi-recall").textContent = `${Math.round(100 * top.metrics_test_sentinel.recall)}%`;
  $("kpi-models").textContent = REG.models.length;
}

// ---------- event ----------
$("thr").addEventListener("input", (e) => { threshold = parseFloat(e.target.value); $("thr-val").textContent = threshold.toFixed(2); render(); });
["px", "minpx", "ly-fill", "ly-poly", "ly-label"].forEach((id) => $(id).addEventListener("input", render));
$("file").addEventListener("change", (e) => {
  $("sample-buttons").querySelectorAll("button").forEach((x) => x.classList.remove("active"));
  const f = e.target.files[0]; if (f) runOnUrl(URL.createObjectURL(f), null, null);
});
$("btn-compare").addEventListener("click", compareAll);
$("btn-geojson").addEventListener("click", downloadGeoJSON);

Sim.setup($("sim"));
HSE.setup($("hse"));
init();

// Profil tim (data di team.json)
fetch("team.json").then((r) => r.json()).then((team) => {
  const box = $("team");
  team.forEach((m) => {
    const card = document.createElement("div"); card.className = "member";
    const ok = (v) => v && !String(v).startsWith("ISI_");
    const img = m.foto ? `<img src="${m.foto}" alt="Foto ${m.nama}" loading="lazy">` : `<div class="avatar">${m.nama.charAt(0)}</div>`;
    card.innerHTML = (m.ketua ? `<span class="badge">Ketua Kelompok</span>` : "") + `${img}<b>${m.nama}</b>` +
      (ok(m.npm) ? `<span>NPM ${m.npm}</span>` : "") + (ok(m.peran) ? `<span class="muted">${m.peran}</span>` : "") +
      (ok(m.linkedin) ? `<a href="${m.linkedin}" target="_blank" rel="noopener">LinkedIn</a>` : "");
    box.appendChild(card);
  });
});
