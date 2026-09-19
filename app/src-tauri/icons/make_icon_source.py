"""生成图标源图 1024x1024 PNG（只用标准库 + numpy，不引入额外依赖）。

设计：深色底 + 居中对称的波形竖条，呼应「音频剪切」。
生成后交给 `npx tauri icon` 派生各平台图标。
"""

import struct
import zlib
from pathlib import Path

import numpy as np

SIZE = 1024
BG = (0x12, 0x14, 0x1C)
ACCENT = (0x5E, 0xEA, 0xD4)

img = np.zeros((SIZE, SIZE, 4), dtype=np.uint8)
img[..., 0], img[..., 1], img[..., 2], img[..., 3] = (*BG, 255)

# 竖条：中间高、两侧低，模拟波形包络
bar_width = 56
gap = 34
heights = [0.22, 0.42, 0.66, 0.88, 1.0, 0.88, 0.66, 0.42, 0.22]
total = len(heights) * bar_width + (len(heights) - 1) * gap
left = (SIZE - total) // 2

for index, ratio in enumerate(heights):
    x0 = left + index * (bar_width + gap)
    x1 = x0 + bar_width
    half = int(SIZE * 0.34 * ratio)
    y0, y1 = SIZE // 2 - half, SIZE // 2 + half
    img[y0:y1, x0:x1, 0] = ACCENT[0]
    img[y0:y1, x0:x1, 1] = ACCENT[1]
    img[y0:y1, x0:x1, 2] = ACCENT[2]


def write_png(path: Path, array: np.ndarray) -> None:
    height, width, _ = array.shape
    # 每条扫描线前面加一个 filter 字节 0（None）
    raw = b"".join(b"\x00" + array[y].tobytes() for y in range(height))

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9))
    png += chunk(b"IEND", b"")
    path.write_bytes(png)


out = Path(__file__).resolve().parent / "source.png"
write_png(out, img)
print(f"wrote {out} ({out.stat().st_size} bytes)")
