# === 15. Fitur per piksel untuk model Machine Learning ===
# Ditulis dengan operasi PyTorch agar fitur yang sama persis bisa diekspor ke ONNX dan dihitung di browser.
import torch, torch.nn as nn, torch.nn.functional as F

FEATURE_NAMES = ["intensitas", "mean_5", "mean_11", "mean_21", "mean_41", "std_5", "std_11", "std_21",
                 "gradien_sobel", "kontras_5_41", "selisih_mean_citra", "min_11", "max_11"]

def box(x, k):  # rata-rata lokal k x k dengan padding reflect
    return F.avg_pool2d(F.pad(x, (k // 2,) * 4, mode="reflect"), k, 1)

class SARFeatures(nn.Module):
    """Citra (B,1,H,W) bernilai 0-255 -> matriks fitur (B*H*W, 13), satu baris per piksel."""
    def __init__(self):
        super().__init__()
        sx = torch.tensor([[-1., 0., 1.], [-2., 0., 2.], [-1., 0., 1.]]) / 8
        self.register_buffer("sobel", torch.stack([sx, sx.t()])[:, None])

    def forward(self, img):
        x = img / 255.0
        m = {k: box(x, k) for k in (5, 11, 21, 41)}                                           # tingkat kegelapan multi-skala
        std = [torch.sqrt(F.relu(box(x * x, k) - m[k] * m[k]) + 1e-8) for k in (5, 11, 21)]  # tekstur (slick = halus)
        g = F.conv2d(F.pad(m[5], (1, 1, 1, 1), mode="reflect"), self.sobel)
        grad = torch.sqrt((g * g).sum(1, keepdim=True) + 1e-8)                               # tepi slick
        gmean = x.mean((2, 3), keepdim=True)                                                  # konteks: lebih gelap dari rata-rata citra?
        p = F.pad(m[5], (5,) * 4, mode="reflect")
        mn, mx = -F.max_pool2d(-p, 11, 1), F.max_pool2d(p, 11, 1)
        f = torch.cat([x, m[5], m[11], m[21], m[41], *std, grad, m[5] - m[41], m[5] - gmean, mn, mx], 1)
        return f.permute(0, 2, 3, 1).reshape(-1, f.shape[1])
