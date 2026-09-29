// Simulasi skenario (what-if) pergerakan & penyebaran slick + estimasi kebutuhan oil boom.
// Model sederhana yang lazim dipakai untuk perencanaan awal respons:
//  - Drift  : kecepatan slick = 3% kecepatan angin (searah angin bertiup) + 100% arus permukaan.
//  - Spread : Fay (1971) rezim gravitasi-viskos, A(t) ∝ (Δ g V² / √ν)^(1/3) · t^(1/2),
//             ditambah difusi turbulen permukaan laut: ΔA = 8πKt, K dari hukum skala Okubo (1971).
//  - Volume : luas terdeteksi × ketebalan (kode penampakan Bonn Agreement, dipilih pengguna).
// Ini BUKAN ramalan operasional: angin/arus diisi pengguna, tidak memodelkan pelapukan, garis pantai, turbulensi.
"use strict";

const Sim = (() => {
  const G = 9.81, NU = 1.0e-6, K2 = 1.45, RHO_W = 1025;
  const knots = (ms) => ms * 1.943844;
  const vec = (speed, deg) => [speed * Math.sin((deg * Math.PI) / 180), speed * Math.cos((deg * Math.PI) / 180)]; // [timur, utara]

  function drift(p) {
    const w = vec(0.03 * p.wind, (p.windFrom + 180) % 360), c = vec(p.current, p.currentTo);
    const v = [w[0] + c[0], w[1] + c[1]], speed = Math.hypot(v[0], v[1]);
    return { v, speed, dir: ((Math.atan2(v[0], v[1]) * 180) / Math.PI + 360) % 360 };
  }

  // Luas (m²) sebagai fungsi waktu (jam sejak deteksi) untuk satu slick
  function spread(A0, thickUm, rhoOil, hours, kMul = 0) {
    const V = A0 * thickUm * 1e-6, delta = (RHO_W - rhoOil) / RHO_W;
    const c = Math.PI * K2 * K2 * Math.cbrt((delta * G * V * V) / Math.sqrt(NU));
    const t0 = (A0 / c) ** 2;                       // "umur ekuivalen" slick saat terdeteksi (detik)
    // Okubo (1971): K [cm²/s] = 0,0103 · L^1,15, L = skala patch [cm] (di sini diameter ekuivalen slick)
    const L = 2 * Math.sqrt(A0 / Math.PI) * 100, K = (kMul * 0.0103 * L ** 1.15) / 1e4;   // m²/s
    const A = A0 * Math.sqrt((t0 + hours * 3600) / t0) + 8 * Math.PI * K * hours * 3600;
    const hMin = 0.04e-6;                           // batas bawah sheen (0,04 µm): penyebaran berhenti
    return { A: Math.min(A, V / hMin), V, K, t0h: t0 / 3600 };
  }

  const n = (x, d = 2) => x.toLocaleString("id-ID", { minimumFractionDigits: d, maximumFractionDigits: d });
  const dirName = (d) => ["utara", "timur laut", "timur", "tenggara", "selatan", "barat daya", "barat", "barat laut"][Math.round(d / 45) % 8];

  let st = null, playing = null;

  function setup(el) {
    st = { el, slicks: [], S: 256, mpp: 10, gray: null, hour: 0 };
    const inputs = el.querySelectorAll("[data-sim]");
    inputs.forEach((i) => i.addEventListener("input", () => { if (i.id === "sim-hour") st.hour = +i.value; update(); }));
    el.querySelectorAll("[data-preset]").forEach((b) => b.addEventListener("click", () => {
      const [w, wf, c, ct] = b.dataset.preset.split(",").map(Number);
      Object.entries({ "sim-wind": w, "sim-wdir": wf, "sim-cur": c, "sim-cdir": ct }).forEach(([id, v]) => (el.querySelector("#" + id).value = v));
      update();
    }));
    el.querySelector("#sim-play").addEventListener("click", togglePlay);
  }

  function params() {
    const q = (id) => +st.el.querySelector("#" + id).value;
    return { wind: q("sim-wind"), windFrom: q("sim-wdir"), current: q("sim-cur"), currentTo: q("sim-cdir"), thick: q("sim-thick"),
             rho: q("sim-oil"), K: q("sim-k"), resp: q("sim-resp"), horizon: q("sim-horizon") };
  }

  function togglePlay() {
    const btn = st.el.querySelector("#sim-play"), slider = st.el.querySelector("#sim-hour");
    if (playing) { clearInterval(playing); playing = null; btn.textContent = "▶ Putar"; return; }
    if (+slider.value >= +slider.max) slider.value = 0;
    btn.textContent = "⏸ Jeda";
    playing = setInterval(() => {
      slider.value = Math.min(+slider.max, +slider.value + +slider.max / 60); st.hour = +slider.value; update();
      if (+slider.value >= +slider.max) togglePlay();
    }, 60);
  }

  function setSlicks(slicks, S, mpp, gray) {
    Object.assign(st, { slicks, S, mpp: mpp || 10, gray, mppGuessed: !mpp });
    update();
  }

  // Poligon slick (piksel) -> dunia (meter, x timur / y utara) pada jam ke-h
  function worldPoly(s, h, p, d) {
    const { S, mpp } = st, A0 = s.px * mpp * mpp, sp = spread(A0, p.thick, p.rho, h, p.K);
    const k = Math.sqrt(sp.A / A0), cx = s.cx * mpp, cy = (S - s.cy) * mpp, dx = d.v[0] * h * 3600, dy = d.v[1] * h * 3600;
    return { pts: s.poly.map(([x, y]) => [cx + (x * mpp - cx) * k + dx, cy + ((S - y) * mpp - cy) * k + dy]), A: sp.A, k, c: [cx + dx, cy + dy], sp };
  }

  function update() {
    if (!st) return;
    const p = params(), d = drift(p), out = st.el.querySelector("#sim-out");
    const slider = st.el.querySelector("#sim-hour");
    slider.max = p.horizon; if (st.hour > p.horizon) st.hour = p.horizon; slider.value = st.hour;
    st.el.querySelector("#sim-hour-val").textContent = `+${n(st.hour, 1)} jam`;
    st.el.querySelector("#sim-wind-val").textContent = `${n(p.wind, 1)} m/s (${n(knots(p.wind), 0)} knot)`;
    st.el.querySelector("#sim-cur-val").textContent = `${n(p.current)} m/s (${n(knots(p.current), 1)} knot)`;
    draw(p, d);
    if (!st.slicks.length) { out.innerHTML = `<p class="muted">Jalankan deteksi dengan hasil berisi minyak untuk memulai simulasi.</p>`; return; }

    const tot = (h) => st.slicks.reduce((a, s) => a + worldPoly(s, h, p, d).A, 0);
    const A0 = tot(0), Ah = tot(st.hour), Ar = tot(p.resp), A1 = tot(1);
    const perimR = st.slicks.reduce((a, s) => a + Geo.perimeter(Geo.hull(worldPoly(s, p.resp, p, d).pts)), 0);
    const K0 = worldPoly(st.slicks[0], 0, p, d).sp.K;
    const boomEncircle = 1.3 * perimR;              // keliling convex hull + kelonggaran 30% untuk tambatan & lekukan boom
    const V = st.slicks.reduce((a, s) => a + s.px * st.mpp * st.mpp * p.thick * 1e-6, 0);
    const distR = d.speed * p.resp * 3.6;          // km
    const warn = [];
    if (knots(d.speed) > 0.7) warn.push(`Kecepatan relatif slick ${n(knots(d.speed))} knot &gt; 0,7 knot: boom penahan biasa mulai bocor (oil entrainment). Pertimbangkan boom defleksi bersudut atau skimmer yang ikut bergerak.`);
    if (p.wind > 10) warn.push(`Angin ${n(p.wind, 1)} m/s (~${n(knots(p.wind), 0)} knot) biasanya disertai gelombang yang membuat boom kurang efektif; utamakan keselamatan kru.`);
    if (st.mppGuessed) warn.push(`Resolusi piksel belum diisi, dipakai asumsi 10 m/piksel. Isi di panel kiri agar luas & jarak sesuai citra Anda.`);
    out.innerHTML = `
      <div class="sim-stats">
        <div><span>Arah gerak slick</span><b>${n(d.dir, 0)}° · ke ${dirName(d.dir)}</b></div>
        <div><span>Kecepatan drift</span><b>${n(d.speed, 2)} m/s · ${n(d.speed * 3.6, 2)} km/jam</b></div>
        <div><span>Luas saat deteksi</span><b>${n(A0 / 1e6, 3)} km²</b></div>
        <div><span>Luas pada +${n(st.hour, 1)} jam</span><b>${n(Ah / 1e6, 3)} km² <em>(×${n(Ah / A0, 2)})</em></b></div>
        <div><span>Laju melebar (jam pertama)</span><b>${n((A1 - A0) / 1e6, 3)} km²/jam</b></div>
        <div><span>Estimasi volume minyak</span><b>${V < 1 ? n(V * 1000, 0) + " liter" : n(V, 1) + " m³"}</b></div>
      </div>
      <div class="boom-box">
        <div class="boom-ico" aria-hidden="true"></div>
        <div>
          <b>Saat tim tiba (+${n(p.resp, 1)} jam)</b>: slick sudah bergeser ±${n(distR, 2)} km ke ${dirName(d.dir)} dengan luas ±${n(Ar / 1e6, 3)} km².
          Kebutuhan <b>oil boom</b> untuk mengurung seluruh slick: <b class="big">±${boomEncircle >= 1000 ? n(boomEncircle / 1000, 2) + " km" : n(boomEncircle, 0) + " m"}</b>
          <small>(1,3 × keliling convex hull slick prediksi; K difusi slick terbesar ≈ ${n(K0)} m²/s). Pasang di sisi hilir arah gerak (garis oranye pada peta).</small>
        </div>
      </div>
      ${warn.map((w) => `<p class="warn">⚠ ${w}</p>`).join("")}`;
  }

  function draw(p, d) {
    const cv = st.el.querySelector("#sim-canvas"), ctx = cv.getContext("2d");
    const W = cv.width, H = cv.height, { S, mpp } = st, L = S * mpp;
    ctx.clearRect(0, 0, W, H);
    // batas dunia: footprint citra + posisi slick sampai horizon
    let xs = [0, L], ys = [0, L];
    const frames = [0, p.horizon / 3, (2 * p.horizon) / 3, p.horizon, p.resp];
    st.slicks.forEach((s) => frames.forEach((h) => worldPoly(s, h, p, d).pts.forEach(([x, y]) => { xs.push(x); ys.push(y); })));
    const pad = 0.12, x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    const span = Math.max(x1 - x0, y1 - y0) * (1 + 2 * pad), sc = Math.min(W, H) / span;
    const ox = (x0 + x1) / 2, oy = (y0 + y1) / 2;
    const tx = (x) => W / 2 + (x - ox) * sc, ty = (y) => H / 2 - (y - oy) * sc;

    // laut
    const g = ctx.createLinearGradient(0, 0, 0, H); g.addColorStop(0, "#dff3fb"); g.addColorStop(1, "#bfe3f2");
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
    ctx.strokeStyle = "rgba(14,116,144,0.10)"; ctx.lineWidth = 1;
    const step = niceStep(span / 6);
    for (let x = Math.floor((ox - span) / step) * step; x < ox + span; x += step) { ctx.beginPath(); ctx.moveTo(tx(x), 0); ctx.lineTo(tx(x), H); ctx.stroke(); }
    for (let y = Math.floor((oy - span) / step) * step; y < oy + span; y += step) { ctx.beginPath(); ctx.moveTo(0, ty(y)); ctx.lineTo(W, ty(y)); ctx.stroke(); }

    // footprint citra SAR
    if (st.gray) {
      if (!st.imgCanvas || st.imgCanvas._src !== st.gray) {
        const c = document.createElement("canvas"); c.width = c.height = S; const cx = c.getContext("2d"), im = cx.createImageData(S, S);
        for (let i = 0; i < S * S; i++) im.data.set([st.gray[i], st.gray[i], st.gray[i], 255], 4 * i);
        cx.putImageData(im, 0, 0); c._src = st.gray; st.imgCanvas = c;
      }
      ctx.globalAlpha = 0.55; ctx.drawImage(st.imgCanvas, tx(0), ty(L), L * sc, L * sc); ctx.globalAlpha = 1;
      ctx.strokeStyle = "rgba(15,23,42,0.35)"; ctx.setLineDash([4, 4]); ctx.strokeRect(tx(0), ty(L), L * sc, L * sc); ctx.setLineDash([]);
    }
    if (!st.slicks.length) return label(ctx, W, H, step, sc);

    // jejak waktu (bayangan) + posisi saat ini
    const path = (pts) => { ctx.beginPath(); pts.forEach(([x, y], i) => (i ? ctx.lineTo(tx(x), ty(y)) : ctx.moveTo(tx(x), ty(y)))); ctx.closePath(); };
    st.slicks.forEach((s) => {
      for (let i = 1; i <= 3; i++) {
        const w = worldPoly(s, (i * p.horizon) / 3, p, d); path(w.pts);
        ctx.strokeStyle = `rgba(124,58,237,${0.25 + 0.1 * i})`; ctx.setLineDash([5, 4]); ctx.lineWidth = 1.2; ctx.stroke(); ctx.setLineDash([]);
      }
      const w0 = worldPoly(s, 0, p, d); path(w0.pts); ctx.fillStyle = "rgba(15,23,42,0.35)"; ctx.fill();
      // oil boom pada saat tim tiba: rangkaian pelampung oranye mengelilingi slick prediksi
      const wr = worldPoly(s, p.resp, p, d), rEq = Math.sqrt(wr.A / Math.PI), grow = 1 + Math.max(30, 0.08 * rEq) / rEq;
      const ring = Geo.hull(wr.pts).map(([x, y]) => [wr.c[0] + (x - wr.c[0]) * grow, wr.c[1] + (y - wr.c[1]) * grow]);
      path(ring); ctx.strokeStyle = "#f97316"; ctx.lineWidth = 2.2; ctx.stroke();
      const per = Geo.perimeter(ring) * sc, nDots = Math.max(8, Math.min(90, Math.round(per / 9)));
      pointsAlong(ring, nDots).forEach(([x, y]) => { ctx.beginPath(); ctx.arc(tx(x), ty(y), 2.6, 0, 7); ctx.fillStyle = "#fb923c"; ctx.fill(); ctx.strokeStyle = "#9a3412"; ctx.lineWidth = 0.8; ctx.stroke(); });
      // slick pada jam terpilih dengan kilau minyak
      const wh = worldPoly(s, st.hour, p, d); path(wh.pts);
      const gr = ctx.createLinearGradient(tx(wh.c[0] - rEq), ty(wh.c[1] - rEq), tx(wh.c[0] + rEq), ty(wh.c[1] + rEq));
      ["#7c3aed", "#db2777", "#f59e0b", "#10b981", "#0ea5e9"].forEach((c, i) => gr.addColorStop(i / 4, c));
      ctx.globalAlpha = 0.55; ctx.fillStyle = gr; ctx.fill(); ctx.globalAlpha = 1; ctx.strokeStyle = "#1e1b4b"; ctx.lineWidth = 1.5; ctx.stroke();
    });
    // panah arah drift
    const c0 = st.slicks[0], a = [c0.cx * mpp, (S - c0.cy) * mpp], b = [a[0] + d.v[0] * p.horizon * 3600, a[1] + d.v[1] * p.horizon * 3600];
    if (d.speed > 1e-4) arrow(ctx, tx(a[0]), ty(a[1]), tx(b[0]), ty(b[1]));
    label(ctx, W, H, step, sc);
  }

  function pointsAlong(poly, n) {
    const segs = poly.map((p, i) => [p, poly[(i + 1) % poly.length]]), lens = segs.map(([a, b]) => Math.hypot(b[0] - a[0], b[1] - a[1]));
    const total = lens.reduce((x, y) => x + y, 0), out = []; let si = 0, acc = 0;
    for (let k = 0; k < n; k++) {
      const t = (k / n) * total;
      while (si < segs.length - 1 && acc + lens[si] < t) acc += lens[si++];
      const f = lens[si] ? (t - acc) / lens[si] : 0, [p, q] = segs[si];
      out.push([p[0] + (q[0] - p[0]) * f, p[1] + (q[1] - p[1]) * f]);
    }
    return out;
  }

  function arrow(ctx, x1, y1, x2, y2) {
    const ang = Math.atan2(y2 - y1, x2 - x1);
    ctx.strokeStyle = "#0f172a"; ctx.fillStyle = "#0f172a"; ctx.lineWidth = 2; ctx.setLineDash([2, 3]);
    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke(); ctx.setLineDash([]);
    ctx.beginPath(); ctx.moveTo(x2, y2); ctx.lineTo(x2 - 11 * Math.cos(ang - 0.4), y2 - 11 * Math.sin(ang - 0.4)); ctx.lineTo(x2 - 11 * Math.cos(ang + 0.4), y2 - 11 * Math.sin(ang + 0.4)); ctx.closePath(); ctx.fill();
  }

  function niceStep(x) { const e = 10 ** Math.floor(Math.log10(x)), f = x / e; return (f < 1.5 ? 1 : f < 3.5 ? 2 : f < 7.5 ? 5 : 10) * e; }

  function label(ctx, W, H, step, sc) {
    ctx.fillStyle = "rgba(255,255,255,0.85)"; ctx.fillRect(12, H - 34, step * sc + 16, 24);
    ctx.fillStyle = "#0f172a"; ctx.fillRect(20, H - 18, step * sc, 4);
    ctx.font = "600 11px Inter, sans-serif"; ctx.fillText(step >= 1000 ? `${step / 1000} km` : `${step} m`, 20, H - 22);
    // mata angin
    ctx.save(); ctx.translate(W - 30, 34); ctx.fillStyle = "#0f172a"; ctx.beginPath(); ctx.moveTo(0, -18); ctx.lineTo(7, 6); ctx.lineTo(0, 1); ctx.lineTo(-7, 6); ctx.closePath(); ctx.fill();
    ctx.font = "700 11px Inter, sans-serif"; ctx.textAlign = "center"; ctx.fillText("U", 0, 20); ctx.restore();
  }

  return { setup, setSlicks, update, drift, spread };
})();
