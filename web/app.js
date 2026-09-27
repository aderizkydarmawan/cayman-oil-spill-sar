// Inferensi segmentasi oil spill di browser dengan onnxruntime-web (WASM).
// Kontrak input/output dibaca dari model/model_metadata.json (dihasilkan notebook Colab).
ort.env.wasm.wasmPaths = "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.30.0/dist/";

const $ = (id) => document.getElementById(id);
// Status + lampu indikator
const statusEl = document.getElementById("status");
new MutationObserver(() => {
  const t = statusEl.textContent, led = $("led");
  led.className = "led" + (t === "siap" || t === "selesai" ? " ready" : t.startsWith("inferensi") ? " busy" : "");
}).observe(statusEl, { childList: true, characterData: true, subtree: true });
let session, meta, threshold, last = null; // last = {prob, gray, gt, refDice}

async function init() {
  try {
    meta = await (await fetch("model/model_metadata.json")).json();
    threshold = meta.threshold;
    $("thr").value = threshold;
    $("thr-val").textContent = threshold.toFixed(2);
    $("model-name").textContent = `${meta.model_name} (${meta.model_file})`;
    $("model-size").textContent = `${meta.model_size_mb.toFixed(2)} MB`;
    session = await ort.InferenceSession.create(`model/${meta.model_file}`, {
      executionProviders: ["wasm"],
      graphOptimizationLevel: "all",
    });
    $("backend").textContent = `onnxruntime-web ${ort.env.versions?.web ?? ""} · WASM · threads=${ort.env.wasm.numThreads ?? "auto"}`;
    $("status").textContent = "siap";
    await loadSamples();
  } catch (e) {
    $("status").textContent = "gagal memuat model: " + e.message;
    console.error(e);
  }
}

async function loadSamples() {
  const samples = await (await fetch("samples/samples.json")).json();
  const box = $("sample-buttons");
  samples.forEach((s, i) => {
    const b = document.createElement("button");
    b.innerHTML = `Try Sample ${i + 1}<small>${(s.note || "").split(" (")[0]}</small>`;
    b.title = s.source || s.image;
    b.onclick = () => {
      box.querySelectorAll("button").forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      runOnUrl(`samples/${s.image}`, s.mask ? `samples/${s.mask}` : null, s.dice_python);
    };
    box.appendChild(b);
  });
}

function loadImage(url) {
  return new Promise((res, rej) => {
    const im = new Image();
    im.onload = () => res(im);
    im.onerror = rej;
    im.src = url;
  });
}

// Citra -> grayscale 256x256 (rata-rata RGB; sama dengan kanal R untuk citra dataset yang R=G=B)
function toGray(img, S) {
  const c = document.createElement("canvas");
  c.width = S; c.height = S;
  const ctx = c.getContext("2d", { willReadFrequently: true });
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(img, 0, 0, S, S);
  const d = ctx.getImageData(0, 0, S, S).data;
  const g = new Uint8ClampedArray(S * S);
  for (let i = 0; i < S * S; i++) g[i] = Math.round((d[4 * i] + d[4 * i + 1] + d[4 * i + 2]) / 3);
  return g;
}

function toTensor(gray, S) {
  const { mean, std } = meta.preprocessing;
  const x = new Float32Array(S * S);
  for (let i = 0; i < S * S; i++) x[i] = (gray[i] / 255 - mean) / std;
  return new ort.Tensor("float32", x, [1, 1, S, S]);
}

async function infer(gray, S) {
  const feeds = { [session.inputNames[0]]: toTensor(gray, S) };
  const times = [];
  let out;
  for (let r = 0; r < 4; r++) { // run pertama = warm-up, dilaporkan terpisah
    const t0 = performance.now();
    out = await session.run(feeds);
    times.push(performance.now() - t0);
  }
  const logits = out[session.outputNames[0]].data;
  const prob = new Float32Array(logits.length);
  for (let i = 0; i < logits.length; i++) prob[i] = 1 / (1 + Math.exp(-logits[i]));
  const warm = times.slice(1).sort((a, b) => a - b);
  return { prob, first: times[0], median: warm[Math.floor(warm.length / 2)] };
}

async function runOnUrl(url, maskUrl, refDice) {
  $("status").textContent = "inferensi…";
  const S = meta.preprocessing.input_shape[2];
  const img = await loadImage(url);
  const gray = toGray(img, S);
  let gt = null;
  if (maskUrl) {
    const g = toGray(await loadImage(maskUrl), S);
    gt = new Uint8Array(S * S);
    for (let i = 0; i < S * S; i++) gt[i] = g[i] >= 128 ? 1 : 0;
  }
  const { prob, first, median } = await infer(gray, S);
  last = { prob, gray, gt, refDice, S, origW: img.naturalWidth, origH: img.naturalHeight };
  $("latency").textContent = `${median.toFixed(0)} ms · median 3 run (run pertama ${first.toFixed(0)} ms)`;
  render();
  $("status").textContent = "selesai";
}

function render() {
  if (!last) return;
  const { prob, gray, gt, refDice, S } = last;
  const put = (id, fn) => {
    const ctx = $(id).getContext("2d");
    const im = ctx.createImageData(S, S);
    for (let i = 0; i < S * S; i++) {
      const [r, g, b] = fn(i);
      im.data.set([r, g, b, 255], 4 * i);
    }
    ctx.putImageData(im, 0, 0);
  };
  let fg = 0, tp = 0, fp = 0, fn = 0;
  const pred = new Uint8Array(S * S);
  for (let i = 0; i < S * S; i++) {
    pred[i] = prob[i] >= threshold ? 1 : 0;
    fg += pred[i];
    if (gt) { if (pred[i] && gt[i]) tp++; else if (pred[i]) fp++; else if (gt[i]) fn++; }
  }
  put("c-input", (i) => [gray[i], gray[i], gray[i]]);
  put("c-prob", (i) => { const p = prob[i]; return [20 + 235 * Math.min(1, p * 1.6), 20 + 200 * Math.max(0, p - 0.4), 40 + 90 * (1 - p)]; });
  put("c-overlay", (i) => pred[i]
    ? [0.55 * gray[i] + 0.45 * 255, 0.55 * gray[i] + 0.45 * 38, 0.55 * gray[i] + 0.45 * 25]
    : [gray[i], gray[i], gray[i]]);
  // Luas: jumlah piksel minyak × (resolusi)². Piksel dihitung di grid 256×256 → skala ke ukuran citra asli.
  const px = parseFloat($("px").value);
  let km2 = "";
  if (px > 0 && last.origW) {
    const pixelsOrig = (fg / (S * S)) * last.origW * last.origH;
    const a = (pixelsOrig * px * px) / 1e6, total = (last.origW * last.origH * px * px) / 1e6;
    km2 = ` ≈ ${a.toFixed(3)} km² dari ${total.toFixed(3)} km² area citra (${last.origW}×${last.origH} px @ ${px} m)`;
  }
  $("area").textContent = `${(100 * fg / (S * S)).toFixed(1)}% piksel (threshold ${threshold.toFixed(2)})${km2}`;
  $("fig-gt").hidden = !gt;
  $("dice-row").hidden = !gt;
  if (gt) {
    put("c-gt", (i) => gt[i] ? [255, 255, 255] : [0, 0, 0]);
    const denom = 2 * tp + fp + fn;
    const dice = denom === 0 ? 1 : (2 * tp) / denom;
    $("dice").textContent = dice.toFixed(4);
    $("dice-ref").textContent = refDice != null && Math.abs(threshold - meta.threshold) < 1e-9
      ? `referensi Python: ${refDice.toFixed(4)}` : "";
  }
}

$("thr").addEventListener("input", (e) => {
  threshold = parseFloat(e.target.value);
  $("thr-val").textContent = threshold.toFixed(2);
  render();
});

$("px").addEventListener("input", render);

$("file").addEventListener("change", (e) => {
  $("sample-buttons").querySelectorAll("button").forEach((x) => x.classList.remove("active"));
  const f = e.target.files[0];
  if (f) runOnUrl(URL.createObjectURL(f), null, null);
});

init();

// Landing page profil tim (data di team.json)
fetch("team.json").then((r) => r.json()).then((team) => {
  const box = $("team");
  team.forEach((m) => {
    const card = document.createElement("div");
    card.className = "member";
    const img = m.foto ? `<img src="${m.foto}" alt="${m.nama}">` : `<div class="avatar">${m.nama.charAt(0)}</div>`;
    card.innerHTML = `${img}<b>${m.nama}</b><span>NIM ${m.nim}</span><span class="muted">${m.peran}</span><a href="${m.linkedin}" target="_blank" rel="noopener">LinkedIn</a>`;
    box.appendChild(card);
  });
});
