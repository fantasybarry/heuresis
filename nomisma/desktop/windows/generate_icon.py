"""Rebuild Nomisma.ico from the app's simple N monogram (stdlib only)."""
from pathlib import Path
import struct
import zlib


def inside_polygon(x, y, polygon):
    inside = False
    previous = polygon[-1]
    for current in polygon:
        x1, y1 = previous
        x2, y2 = current
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
        previous = current
    return inside


def png(size):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    polygons = [
        [(0.265, 0.255), (0.33, 0.255), (0.33, 0.755), (0.265, 0.755)],
        [(0.67, 0.255), (0.735, 0.255), (0.735, 0.755), (0.67, 0.755)],
        [(0.28, 0.255), (0.395, 0.255), (0.72, 0.745), (0.605, 0.745)],
        [(0.22, 0.225), (0.405, 0.225), (0.405, 0.28), (0.22, 0.28)],
        [(0.59, 0.225), (0.78, 0.225), (0.78, 0.28), (0.59, 0.28)],
        [(0.22, 0.73), (0.405, 0.73), (0.405, 0.785), (0.22, 0.785)],
        [(0.59, 0.73), (0.78, 0.73), (0.78, 0.785), (0.59, 0.785)],
    ]
    rows = bytearray()
    samples = 4
    for row in range(size):
        rows.append(0)
        for column in range(size):
            channels = [0, 0, 0, 0]
            for dy in range(samples):
                for dx in range(samples):
                    x, y = (column + (dx + 0.5) / samples) / size, (row + (dy + 0.5) / samples) / size
                    corner_x, corner_y = max(0.21 - x, 0, x - 0.79), max(0.21 - y, 0, y - 0.79)
                    if corner_x * corner_x + corner_y * corner_y > 0.19 ** 2:
                        color = (0, 0, 0, 0)
                    elif any(inside_polygon(x, y, polygon) for polygon in polygons):
                        color = (241, 231, 205, 255)
                    else:
                        color = (33, 70, 54, 255)
                    channels = [first + second for first, second in zip(channels, color)]
            rows.extend(round(value / (samples * samples)) for value in channels)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(bytes(rows), 9)) + chunk(b"IEND", b"")


def main():
    sizes = (16, 32, 48, 64, 128, 256)
    images = [png(size) for size in sizes]
    offset = 6 + 16 * len(sizes)
    entries = bytearray()
    for size, data in zip(sizes, images):
        entries.extend(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset))
        offset += len(data)
    Path(__file__).with_name("Nomisma.ico").write_bytes(struct.pack("<HHH", 0, 1, len(sizes)) + entries + b"".join(images))


if __name__ == "__main__":
    main()
