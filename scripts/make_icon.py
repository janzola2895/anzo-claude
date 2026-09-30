"""Generates ui/anzo.ico: a glowing orange orb on a dark rounded square
(orange for ANZO + Claude, so it isn't confused with the original ANZO's blue one).

Stdlib only (struct + zlib), like the rest of the project -- no Pillow.
Run once; the .ico is committed. `python scripts/make_icon.py`"""
import math
import os
import random
import struct
import zlib

SIZES = (16, 32, 48, 64, 128, 256)
BG = (7, 9, 15)
ACCENT = (217, 119, 87)


def render(n):
    rnd = random.Random(7)
    dots = []
    for _ in range(90):  # particle shell, same idea as the live orb
        th, ph = rnd.random() * 2 * math.pi, math.acos(2 * rnd.random() - 1)
        r = 0.36 * (0.92 + rnd.random() * 0.16)
        dots.append((r * math.sin(ph) * math.cos(th), r * math.sin(ph) * math.sin(th),
                     r * math.cos(ph), 0.5 + 0.5 * rnd.random()))
    px = [[[0.0, 0.0, 0.0, 0.0] for _ in range(n)] for _ in range(n)]
    corner = 0.22 * n
    for y in range(n):
        for x in range(n):
            u, v = (x + 0.5) / n - 0.5, (y + 0.5) / n - 0.5
            # rounded-square mask with 1px feathering
            qx, qy = abs(x + 0.5 - n / 2) - (n / 2 - corner), abs(y + 0.5 - n / 2) - (n / 2 - corner)
            d = math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - corner
            mask = min(1.0, max(0.0, 0.5 - d))
            if mask <= 0:
                continue
            dist = math.hypot(u, v)
            glow = math.exp(-((dist / 0.30) ** 2)) * 0.85 + math.exp(-((dist / 0.5) ** 2)) * 0.25
            col = [BG[i] + (ACCENT[i] - BG[i]) * min(1.0, glow) for i in range(3)]
            core = math.exp(-((dist / 0.09) ** 2))
            col = [c + (255 - c) * core * 0.9 for c in col]
            px[y][x] = [col[0], col[1], col[2], mask]
    for dx, dy, dz, b in dots:  # soft dots, front-most brightest
        cx, cy = (0.5 + dx) * n, (0.5 + dy) * n
        rad = max(0.7, n * 0.012 * (1.1 + dz))
        for y in range(max(0, int(cy - 3)), min(n, int(cy + 4))):
            for x in range(max(0, int(cx - 3)), min(n, int(cx + 4))):
                if px[y][x][3] <= 0:
                    continue
                a = math.exp(-(((x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2) / (rad * rad))) * b * (0.55 + 0.45 * (dz / 0.36 + 1) / 2)
                for i in range(3):
                    px[y][x][i] += (255 - px[y][x][i]) * min(1.0, a) * 0.8
    return px


def png(px, n):
    raw = bytearray()
    for row in px:
        raw.append(0)
        for r, g, b, a in row:
            raw += bytes((int(min(255, r)), int(min(255, g)), int(min(255, b)), int(min(1.0, a) * 255)))
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))


def main():
    images = [(n, png(render(n), n)) for n in SIZES]
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ui", "anzo.ico")
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for n, data in images:
        entries += struct.pack("<BBBBHHII", 0 if n == 256 else n, 0 if n == 256 else n, 0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)
    with open(out, "wb") as f:
        f.write(header + entries + blobs)
    with open(out.replace(".ico", ".png"), "wb") as f:
        f.write(images[-1][1])
    print("wrote", os.path.normpath(out))


if __name__ == "__main__":
    main()
