// Mask biner -> slick (komponen terhubung) -> poligon batas yang disederhanakan.
// Semua koordinat dalam piksel citra (0..S); konversi ke meter memakai resolusi piksel dari pengguna.
"use strict";

const Geo = (() => {
  // Label komponen terhubung (8-tetangga) dengan flood fill berbasis stack
  function components(mask, S, minPx) {
    const lab = new Int32Array(S * S).fill(-1), comps = [];
    const stack = new Int32Array(S * S);
    for (let s = 0; s < S * S; s++) {
      if (!mask[s] || lab[s] !== -1) continue;
      const id = comps.length; let top = 0, n = 0, sx = 0, sy = 0, x0 = S, y0 = S, x1 = 0, y1 = 0;
      stack[top++] = s; lab[s] = id;
      while (top) {
        const p = stack[--top], x = p % S, y = (p / S) | 0;
        n++; sx += x; sy += y;
        if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y;
        for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
          const nx = x + dx, ny = y + dy;
          if ((dx || dy) && nx >= 0 && ny >= 0 && nx < S && ny < S) {
            const q = ny * S + nx;
            if (mask[q] && lab[q] === -1) { lab[q] = id; stack[top++] = q; }
          }
        }
      }
      comps.push({ id, n, cx: sx / n + 0.5, cy: sy / n + 0.5, bbox: [x0, y0, x1 + 1, y1 + 1] });
    }
    return { lab, comps: comps.filter((c) => c.n >= minPx) };
  }

  // Batas luar satu komponen: telusuri sisi-sisi piksel (crack following), ambil loop terpanjang
  function outline(lab, S, id, bbox) {
    const inside = (x, y) => x >= 0 && y >= 0 && x < S && y < S && lab[y * S + x] === id;
    const next = new Map(); // vertex "x,y" -> daftar vertex berikutnya (arah searah jarum jam)
    const add = (ax, ay, bx, by) => {
      const k = ax * 1024 + ay;
      if (!next.has(k)) next.set(k, []);
      next.get(k).push(bx * 1024 + by);
    };
    for (let y = bbox[1]; y < bbox[3]; y++) for (let x = bbox[0]; x < bbox[2]; x++) {
      if (!inside(x, y)) continue;
      if (!inside(x, y - 1)) add(x, y, x + 1, y);
      if (!inside(x + 1, y)) add(x + 1, y, x + 1, y + 1);
      if (!inside(x, y + 1)) add(x + 1, y + 1, x, y + 1);
      if (!inside(x - 1, y)) add(x, y + 1, x, y);
    }
    let best = [];
    while (next.size) {
      const start = next.keys().next().value; const loop = []; let k = start;
      while (next.has(k)) {
        const arr = next.get(k), n = arr.pop();
        if (!arr.length) next.delete(k);
        loop.push([(k / 1024) | 0, k % 1024]); k = n;
        if (k === start) break;
      }
      if (loop.length > best.length) best = loop;
    }
    return best;
  }

  // Douglas-Peucker untuk poligon tertutup
  function simplify(pts, eps) {
    if (pts.length < 8) return pts;
    const dp = (a, b, out) => {
      const [x1, y1] = pts[a], [x2, y2] = pts[b]; let dmax = 0, idx = -1;
      const L = Math.hypot(x2 - x1, y2 - y1) || 1e-9;
      for (let i = a + 1; i < b; i++) {
        const d = Math.abs((y2 - y1) * pts[i][0] - (x2 - x1) * pts[i][1] + x2 * y1 - y2 * x1) / L;
        if (d > dmax) { dmax = d; idx = i; }
      }
      if (dmax > eps) { dp(a, idx, out); dp(idx, b, out); } else out.push(pts[a]);
    };
    const far = pts.reduce((m, p, i) => (Math.hypot(p[0] - pts[0][0], p[1] - pts[0][1]) > Math.hypot(pts[m][0] - pts[0][0], pts[m][1] - pts[0][1]) ? i : m), 0);
    const out = [];
    dp(0, far, out); dp(far, pts.length - 1, out); out.push(pts[pts.length - 1]);
    return out;
  }

  // Convex hull (monotone chain): bentuk yang realistis untuk dikurung oil boom
  function hull(pts) {
    const P = [...pts].sort((a, b) => a[0] - b[0] || a[1] - b[1]), cr = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
    const lo = [], up = [];
    for (const p of P) { while (lo.length >= 2 && cr(lo[lo.length - 2], lo[lo.length - 1], p) <= 0) lo.pop(); lo.push(p); }
    for (const p of P.reverse()) { while (up.length >= 2 && cr(up[up.length - 2], up[up.length - 1], p) <= 0) up.pop(); up.push(p); }
    return lo.slice(0, -1).concat(up.slice(0, -1));
  }
  const perimeter = (poly) => poly.reduce((s, p, i) => s + Math.hypot(p[0] - poly[(i + 1) % poly.length][0], p[1] - poly[(i + 1) % poly.length][1]), 0);
  const shoelace = (poly) => Math.abs(poly.reduce((s, p, i) => s + p[0] * poly[(i + 1) % poly.length][1] - poly[(i + 1) % poly.length][0] * p[1], 0)) / 2;

  // Ekstraksi slick terurut dari yang terbesar
  function slicks(mask, S, { minPx = 30, eps = 1.2 } = {}) {
    const { lab, comps } = components(mask, S, minPx);
    return comps.sort((a, b) => b.n - a.n).map((c, i) => {
      const poly = simplify(outline(lab, S, c.id, c.bbox), eps);
      return { no: i + 1, px: c.n, cx: c.cx, cy: c.cy, bbox: c.bbox, poly, perimPx: perimeter(poly) };
    });
  }

  // Poligon -> GeoJSON (koordinat lokal meter: x ke timur, y ke utara, asal di pojok kiri-bawah citra)
  function toGeoJSON(list, S, mpp, extra = {}) {
    const k = mpp || 1;
    return {
      type: "FeatureCollection",
      properties: { crs_note: mpp ? "koordinat lokal meter (x timur, y utara) relatif pojok kiri-bawah citra" : "koordinat piksel citra", ...extra },
      features: list.map((s) => ({
        type: "Feature",
        properties: { slick: s.no, area_px: s.px, area_km2: mpp ? (s.px * k * k) / 1e6 : null, perimeter_km: mpp ? (s.perimPx * k) / 1000 : null },
        geometry: { type: "Polygon", coordinates: [[...s.poly, s.poly[0]].map(([x, y]) => [+(x * k).toFixed(2), +((S - y) * k).toFixed(2)])] },
      })),
    };
  }

  return { slicks, toGeoJSON, perimeter, shoelace, hull };
})();
