"""Genera los iconos de distribución a partir de geometría; sin imágenes binarias en Git."""

from pathlib import Path
import struct
import zlib


def chunk(kind, data):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))


def png(size):
    polygon = [(151,352),(151,160),(185,160),(328,317),(328,160),(361,160),(361,352),(327,352),(184,195),(184,352)]
    rows = bytearray()
    for row in range(size):
        rows.append(0)
        y = (row + .5) * 512 / size
        for column in range(size):
            x = (column + .5) * 512 / size
            cx, cy = min(382, max(130, x)), min(382, max(130, y))
            if not 16 <= x <= 496 or not 16 <= y <= 496 or (x-cx)**2 + (y-cy)**2 > 114**2:
                rows.extend((0,0,0,0))
                continue
            inside = False
            previous = polygon[-1]
            for point in polygon:
                if (point[1] > y) != (previous[1] > y) and x < (previous[0]-point[0]) * (y-point[1]) / (previous[1]-point[1]) + point[0]:
                    inside = not inside
                previous = point
            rows.extend((226,245,188,255) if inside else (23,59,54,255))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR',struct.pack('>IIBBBBB',size,size,8,6,0,0,0)) + chunk(b'IDAT',zlib.compress(bytes(rows),9)) + chunk(b'IEND',b'')


def generate(folder: Path):
    folder.mkdir(parents=True, exist_ok=True)
    images = {size:png(size) for size in (16,32,48,64,128,256,512,1024)}
    sizes = (16,32,48,64,128,256)
    offset = 6 + 16 * len(sizes)
    entries, data = [], []
    for size in sizes:
        blob = images[size]
        entries.append(struct.pack('<BBBBHHII',size % 256,size % 256,0,0,1,32,len(blob),offset))
        data.append(blob)
        offset += len(blob)
    (folder/'icon.ico').write_bytes(struct.pack('<HHH',0,1,len(sizes)) + b''.join(entries+data))
    data = b''.join(kind + struct.pack('>I',8+len(images[size])) + images[size] for kind,size in ((b'ic07',128),(b'ic08',256),(b'ic09',512),(b'ic10',1024)))
    (folder/'icon.icns').write_bytes(b'icns' + struct.pack('>I',8+len(data)) + data)
