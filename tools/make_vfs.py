#!/usr/bin/env python3
"""Build a LittleFS image from app/ and flash it to the VFS partition."""
import os, sys, struct
from littlefs import LittleFS

APP   = os.path.join(os.path.dirname(__file__), '..', 'app')
OUT   = os.path.join(os.path.dirname(__file__), 'vfs.img')

# Must match MicroPython ESP32 VFS partition: 0x200000 bytes, 4096-byte blocks
BLOCK_SIZE  = 4096
BLOCK_COUNT = 0x200000 // BLOCK_SIZE   # 512

fs = LittleFS(block_size=BLOCK_SIZE, block_count=BLOCK_COUNT,
              prog_size=256, read_size=256, lookahead_size=32, disk_version=0x00020000)

FILES = [
    ('config.py',           'config.py'),
    ('secrets.py',          'secrets.py'),
    ('hal_kb.py',           'hal_kb.py'),
    ('display.py',          'display.py'),
    ('writer.py',           'writer.py'),
    ('history.py',          'history.py'),
    ('ui.py',               'ui.py'),
    ('wifi_mgr.py',         'wifi_mgr.py'),
    ('api.py',              'api.py'),
    ('repl_term.py',        'repl_term.py'),
    ('getprog.py',          'getprog.py'),
    ('main.py',             'main.py'),
]

FONT_FILES = [
    ('fonts/dejavu14.py',    'fonts/dejavu14.py'),
    ('fonts/dejavu14_ru.py', 'fonts/dejavu14_ru.py'),
    ('fonts/dejavu24bold_ru.py', 'fonts/dejavu24bold_ru.py'),
    ('fonts/mono13.py',      'fonts/mono13.py'),
]

fs.mkdir('fonts')

for src_rel, dst in FILES + FONT_FILES:
    src = os.path.normpath(os.path.join(APP, src_rel))
    if not os.path.exists(src):
        print(f'  SKIP  {src_rel} (not found)')
        continue
    with open(src, 'rb') as f:
        data = f.read()
    with fs.open(dst, 'wb') as f:
        f.write(data)
    print(f'  ADD   {dst} ({len(data)} bytes)')

image = bytes(fs.context.buffer)
with open(OUT, 'wb') as f:
    f.write(image)

print(f'\nWrote {OUT} ({len(image)} bytes)')
print()
print('Now put the board into download mode (hold BOOT, tap RESET, release BOOT)')
print('then run:')
print(f'  esptool --chip esp32s2 --port /dev/ttyACM0 write_flash 0x200000 {OUT}')
