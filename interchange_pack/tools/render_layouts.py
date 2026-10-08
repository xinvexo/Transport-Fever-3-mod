"""Render exact Lua road layouts for inspection and artwork references."""
from pathlib import Path
import struct
import sys
import zlib

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tests'))
from geometry_support import CONTENT, KINDS, generator, sample

DIGITS = {
    '1': ('010', '110', '010', '010', '111'),
    '2': ('110', '001', '010', '100', '111'),
    '3': ('110', '001', '010', '001', '110'),
    '4': ('101', '101', '111', '001', '001'),
}


def disk(canvas, x, y, radius, color):
    x0, x1 = max(0, int(x-radius-1)), min(len(canvas), int(x+radius+2))
    y0, y1 = max(0, int(y-radius-1)), min(len(canvas), int(y+radius+2))
    yy, xx = np.mgrid[y0:y1, x0:x1]
    canvas[y0:y1, x0:x1][(xx-x)**2+(yy-y)**2 <= radius**2] = color


def line(canvas, p, q, radius, color):
    steps = max(2, int(np.linalg.norm(q-p)*2))
    for x, y in np.linspace(p, q, steps):
        disk(canvas, x, y, radius, color)


def render(kind, size):
    net = generator()(kind)
    canvas = np.full((size, size, 4), (20, 29, 40, 255), dtype=np.uint8)
    factor = (size-44)/(2*net['l'])

    def project(points):
        return np.column_stack((size/2+points[:, 0]*factor, size/2-points[:, 1]*factor))

    pieces = [(r, s, sample(s, 97)[0]) for r in net['roads'] for s in r['segments']]
    pieces.sort(key=lambda item: np.mean(item[2][:, 2]))
    for road, segment, points in pieces:
        path = project(points)
        width = (7 if road['role'] in ('main', 'cross') else 4)*size/512
        height = np.mean(points[:, 2])
        color = (204, 220, 231, 255) if height < 3 else (83, 194, 208, 255) if height < 12 else (241, 183, 80, 255)
        for p, q in zip(path, path[1:]):
            line(canvas, p, q, width/2+1.2*size/512, (20,29,40,255))
        for p, q in zip(path, path[1:]):
            line(canvas, p, q, width/2, color)
    if size >= 256:
        positions = []
        if kind == 'cloverleaf':
            positions = [(-net['b'], net['b']), (net['b'], net['b']),
                         (net['b'], -net['b']), (-net['b'], -net['b'])]
        elif kind == 'diamond':
            positions = [(-net['a']*.42, net['b']*.9), (net['a']*.42, net['b']*.9),
                         (net['a']*.42, -net['b']*.9), (-net['a']*.42, -net['b']*.9)]
        elif kind == 'trumpet':
            positions = [(-net['b'], net['b']), (net['b'], net['b'])]
        for number, (x, y) in enumerate(positions, 1):
            center = project(np.array([[x, y, 0]]))[0]
            unit = max(2, round(size/170))
            disk(canvas, *center, unit*3.7, (231, 105, 70, 255))
            for row, bits in enumerate(DIGITS[str(number)]):
                for col, bit in enumerate(bits):
                    if bit == '1':
                        xx, yy = int(center[0]+(col-1.5)*unit), int(center[1]+(row-2.5)*unit)
                        canvas[yy:yy+unit, xx:xx+unit] = (255,255,255,255)
    return canvas


def tga(path, pixels):
    height, width, _ = pixels.shape
    header = struct.pack('<BBBHHBHHHHBB', 0, 0, 2, 0, 0, 0, 0, 0, width, height, 32, 0x28)
    path.write_bytes(header + pixels[:, :, [2,1,0,3]].tobytes())


def png(path, pixels):
    height, width, _ = pixels.shape
    def chunk(kind, data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
    scanlines = b''.join(b'\0'+row.tobytes() for row in pixels)
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,6,0,0,0))+
                     chunk(b'IDAT',zlib.compress(scanlines))+chunk(b'IEND',b''))


if __name__ == '__main__':
    directory = CONTENT.parents[2] / 'test-results' / 'icon-layouts'
    directory.mkdir(parents=True,exist_ok=True)
    previews = []
    for kind in KINDS:
        preview = render(kind, 512)
        previews.append(preview)
        png(directory / f'{kind}.png', preview)
    atlas = np.concatenate((np.concatenate(previews[:3], axis=1), np.concatenate(previews[3:], axis=1)))
    png(directory / 'interchanges.png', atlas)
    print(directory / 'interchanges.png')
