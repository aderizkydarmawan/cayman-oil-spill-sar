"""CMOD5.N (Hersbach 2010), disalin dari xsarsea 2.1.2 xsarsea/windspeed/gmfs_impl.py (gmf_cmod5_generic, neutral=True),
diubah ke bentuk vektor numpy. Satuan sigma0 linear, inc derajat, phi derajat (0 = angin menuju radar/upwind).
"""
import numpy as np

C = np.array([0.0, -0.6878, -0.7957, 0.338, -0.1728, 0.0, 0.004, 0.1103, 0.0159, 6.7329, 2.7713, -2.2885, 0.4971,
              -0.725, 0.045, 0.0066, 0.3222, 0.012, 22.7, 2.0813, 3.0, 8.3659, -3.3428, 1.3236, 6.2437, 2.3893,
              0.3249, 4.159, 1.693])


def sigma0(inc, wspd, phi):
    c = C
    inc, wspd, phi = np.broadcast_arrays(np.asarray(inc, float), np.asarray(wspd, float), np.asarray(phi, float))
    zpow, thetm, thethr = 1.6, 40.0, 25.0
    y0, pn = c[19], c[20]
    a = y0 - (y0 - 1.0) / pn
    b = 1.0 / (pn * (y0 - 1.0) ** (pn - 1.0))
    cosphi = np.cos(np.deg2rad(phi))
    x = (inc - thetm) / thethr; x2 = x ** 2
    a0 = c[1] + c[2] * x + c[3] * x2 + c[4] * x * x2
    a1 = c[5] + c[6] * x
    a2 = c[7] + c[8] * x
    gam = c[9] + c[10] * x + c[11] * x2
    s0 = c[12] + c[13] * x
    s = a2 * wspd
    a3 = 1.0 / (1.0 + np.exp(-s0))
    a3 = np.where(s < s0, a3 * (np.maximum(s, 1e-12) / s0) ** (s0 * (1.0 - a3)), 1.0 / (1.0 + np.exp(-s)))
    b0 = (a3 ** gam) * 10.0 ** (a0 + a1 * wspd)
    b1 = c[15] * wspd * (0.5 + x - np.tanh(4.0 * (x + c[16] + c[17] * wspd)))
    b1 = (c[14] * (1.0 + x) - b1) / (np.exp(0.34 * (wspd - c[18])) + 1.0)
    v0 = c[21] + c[22] * x + c[23] * x2
    d1 = c[24] + c[25] * x + c[26] * x2
    d2 = c[27] + c[28] * x
    v2 = wspd / v0 + 1.0
    v2 = np.where(v2 < y0, a + b * np.maximum(v2 - 1.0, 0) ** pn, v2)
    b2 = (-d1 + d2 * v2) * np.exp(-v2)
    return b0 * (1.0 + b1 * cosphi + b2 * (2.0 * cosphi ** 2 - 1.0)) ** zpow


_W = np.round(np.arange(0.2, 30.01, 0.05), 2)   # dibulatkan: hindari 2.9999999999999996 di ambang


def invert(s0_lin, inc, phi):
    """Kecepatan angin (m/s) dengan pencarian tabel; sigma0 di bawah GMF(0,2 m/s) -> 0,2 (batas bawah)."""
    s0_lin, inc, phi = map(np.atleast_1d, (s0_lin, inc, phi))
    out = np.empty(len(s0_lin))
    for i, (s, t, p) in enumerate(zip(s0_lin, inc, phi)):
        g = sigma0(t, _W, p)                      # monoton naik pada rentang angin rendah-sedang
        out[i] = _W[np.argmin(np.abs(10 * np.log10(g) - 10 * np.log10(s)))]
    return out
