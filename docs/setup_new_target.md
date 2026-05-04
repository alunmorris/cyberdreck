# Setting Up a New CRACK Target via USB

This covers flashing firmware and all Python files onto a fresh ESP32-S2 board
using only the native USB port — no UART adapter required.

---

## Prerequisites

- USB-C cable connected to the board's native USB port
- `esptool` installed (`pip install esptool`)
- `littlefs-python` installed: `pip install littlefs-python`
- Firmware already built (see `firmware/build.sh`), or use the existing build at
  `~/micropython/ports/esp32/build/`

---

## Step 1 — Edit secrets.py

Fill in your credentials before flashing:

```python
# app/secrets.py
GEMINI_KEY = "..."
GROK_KEY   = "..."
GROQ_KEY   = "..."

WIFI_SSID_DEFAULT = "your_ssid"    # optional: pre-load one WiFi network
WIFI_PASS_DEFAULT = "your_pass"
```

---

## Step 2 — Flash the firmware

Put the board into bootloader mode: **hold BOOT, press RST, release BOOT**.
The board appears as `/dev/ttyACM0`.

```bash
firmware/flash.sh
```

This flashes:
- `bootloader.bin` → `0x001000`
- `partition-table.bin` → `0x008000`
- `micropython.bin` → `0x010000`

Press **RST** when done to boot into MicroPython.

---

## Step 3 — Flash the Python files

Put the board into bootloader mode again (**hold BOOT, press RST, release BOOT**).

```bash
tools/flash_vfs.sh
```

This runs `make_vfs.py` to build a LittleFS image from `app/`, then flashes it
to the VFS partition at `0x200000`.

Press **RST** when done. The device boots and runs `main.py` immediately.

---

## What gets flashed

| File | Purpose |
|---|---|
| `config.py` | Screen, pins, API model names |
| `secrets.py` | API keys, default WiFi credentials |
| `hal_kb.py` | USB keyboard driver wrapper |
| `display.py` | TFT display init |
| `writer.py` | Font rendering |
| `history.py` | Chat message store and word wrap |
| `ui.py` | Screen layout — history and input bar |
| `wifi_mgr.py` | WiFi scan, connect, NVS credential storage |
| `api.py` | Gemini / Grok / Groq HTTPS calls |
| `repl_term.py` | MicroPython REPL + file manager |
| `getprog.py` | Download user programs from GitHub |
| `main.py` | Boot sequence and main event loop |
| `fonts/dejavu14.py` | Proportional 14px font |
| `fonts/dejavu14_ru.py` | Proportional 14px font with Cyrillic |
| `fonts/mono13.py` | Monospaced 13px font |

---

## Updating files after initial setup

For day-to-day development use `mpremote` (faster, no reboot needed):

```bash
tools/upload.sh          # uploads all files via UART (/dev/ttyUSB0)
mpremote cp app/foo.py :/foo.py   # upload a single file
```

To do a full USB-only reflash (e.g. on a new board or after a firmware change):
repeat Steps 2 and/or 3 above.
