# === 6. Model U-Net ringan (modul, dipakai notebook & skrip ekspor ONNX) ===
import torch, torch.nn as nn, torch.nn.functional as F

class DoubleConv(nn.Sequential):
    def __init__(self, i, o):
        super().__init__(nn.Conv2d(i, o, 3, padding=1, bias=False), nn.BatchNorm2d(o), nn.ReLU(inplace=True),
                         nn.Conv2d(o, o, 3, padding=1, bias=False), nn.BatchNorm2d(o), nn.ReLU(inplace=True))

class UNetLite(nn.Module):
    """U-Net 4 level, kanal base*[1,2,4,8,16]; hanya Conv/BN/ReLU/MaxPool/ConvTranspose/Concat -> ramah ONNX & onnxruntime-web."""
    def __init__(self, in_ch=1, base=16, depth=4):
        super().__init__()
        ch = [base * 2 ** i for i in range(depth + 1)]
        self.enc = nn.ModuleList([DoubleConv(in_ch if i == 0 else ch[i - 1], ch[i]) for i in range(depth + 1)])
        self.up = nn.ModuleList([nn.ConvTranspose2d(ch[i + 1], ch[i], 2, stride=2) for i in reversed(range(depth))])
        self.dec = nn.ModuleList([DoubleConv(ch[i] * 2, ch[i]) for i in reversed(range(depth))])
        self.head = nn.Conv2d(ch[0], 1, 1)

    def forward(self, x):
        skips = []
        for i, enc in enumerate(self.enc):
            x = enc(x if i == 0 else F.max_pool2d(x, 2)); skips.append(x)
        x = skips.pop()
        for up, dec in zip(self.up, self.dec):
            x = dec(torch.cat([up(x), skips.pop()], 1))
        return self.head(x)   # logits
