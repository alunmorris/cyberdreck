#!/usr/bin/env python3
"""Convert font_to_py hmap font to russhughes write() format.
Reads app/fonts/dejavu24.py, writes app/fonts/dejavu24_ru.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app', 'fonts'))
import dejavu24 as src

HEIGHT = src.height()
_codepoints = list(range(0x20, 0x7F))   # ASCII printable only
CHARS = ''.join(chr(c) for c in _codepoints)

def extract_bits(glyph, w, h):
    bits = []
    row_bytes = (w + 7) // 8
    for row in range(h):
        for col in range(w):
            b = glyph[row * row_bytes + col // 8]
            bits.append((b >> (7 - col % 8)) & 1)
    return bits

def pack_bits(bits):
    result = bytearray()
    for i in range(0, len(bits), 8):
        byte = 0
        for j in range(min(8, len(bits) - i)):
            byte |= bits[i + j] << (7 - j)
        result.append(byte)
    return bytes(result)

widths   = bytearray()
all_bits = []
offsets  = []
map_str  = ''
max_width = 0

for ch in CHARS:
    try:
        glyph, h, w = src.get_ch(ch)
    except Exception:
        continue
    map_str += ch
    widths.append(w)
    offsets.append(len(all_bits))
    all_bits.extend(extract_bits(glyph, w, h))
    if w > max_width:
        max_width = w

bitmap_bytes = pack_bits(all_bits)
OFFSET_WIDTH = 2

def fmt_bytes(data, name):
    lines = []
    row = []
    for b in data:
        row.append(f'\\x{b:02x}')
        if len(row) == 16:
            lines.append("    b'" + ''.join(row) + "'\\")
            row = []
    if row:
        lines.append("    b'" + ''.join(row) + "'")
    if lines:
        lines[-1] = lines[-1].rstrip('\\')
    return f'{name} = \\\n' + '\n'.join(lines)

offsets_bytes = bytearray()
for o in offsets:
    offsets_bytes.append((o >> 8) & 0xFF)
    offsets_bytes.append(o & 0xFF)

out = f'''# Auto-converted from dejavu24.py (font_to_py) to russhughes write() format
# {HEIGHT}px DejaVu Sans, ASCII 0x20-0x7e
MAP = {repr(map_str)}
BPP = 1
HEIGHT = {HEIGHT}
MAX_WIDTH = {max_width}
OFFSET_WIDTH = {OFFSET_WIDTH}
{fmt_bytes(widths, "WIDTHS")}
{fmt_bytes(bytes(offsets_bytes), "OFFSETS")}
{fmt_bytes(bitmap_bytes, "BITMAPS")}
'''

out_path = os.path.join(os.path.dirname(__file__), '..', 'app', 'fonts', 'dejavu24bold_ru.py')
with open(out_path, 'w') as f:
    f.write(out)

print(f'Written {out_path}')
print(f'  {len(map_str)} chars, height={HEIGHT}, max_width={max_width}')
print(f'  WIDTHS={len(widths)}B  OFFSETS={len(offsets_bytes)}B  BITMAPS={len(bitmap_bytes)}B')
