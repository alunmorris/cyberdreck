# Cyberdreck

MicroPython firmware for an ESP32-S2 AI handheld device. Chat with AI models, run a Python REPL, manage files, and extend the device with downloadable user programs.

![Cyberdreck](docs/Cyberdrek%20label.png)

## Hardware

| Component | Details |
|-----------|---------|
| MCU | ESP32-S2 |
| Display | ST7789 320×240 colour TFT |
| Input | USB HID keyboard (OTG host) |
| Connectivity | WiFi 802.11 b/g/n |
| MicroPython | v1.24.1 |

## Features

- **AI chat** — Gemini, Grok, and Groq models selectable from the menu
- **Python REPL** — interactive MicroPython shell with history and line-wrap
- **File manager** — two-column browser, new folder, rename, execute `.py` files
- **WiFi manager** — scan, connect, and store credentials in NVS
- **User programs** — download and run community programs from GitHub
- **Proportional font rendering** — DejaVu 14px (body) and 24px bold (title)

## Repository Layout

```
app/            MicroPython application source
  main.py       Boot sequence and main loop
  config.py     Hardware constants, colours, API endpoints
  repl_term.py  REPL terminal + file manager
  api.py        Gemini / Grok / Groq HTTPS clients
  wifi_mgr.py   WiFi credential management
  fonts/        Pre-converted russhughes-format bitmap fonts
firmware/       ESP32-S2 board config and build scripts
userapp/        Community user programs (downloaded via getprog.py)
tools/          Upload scripts and VFS image builder
tests/          Host-side unit tests
```

## Setup

### 1. Flash MicroPython

Build custom firmware (includes ST7789 and usbhid C extensions) or flash a pre-built `.bin`:

```bash
cd firmware
bash build.sh
```

### 2. Configure secrets

Copy `app/secrets_example.py` to `app/secrets.py` and add your WiFi credentials and API keys:

```python
WIFI = [{"ssid": "MyNetwork", "pass": "password"}]
GEMINI_KEY = "..."
GROK_KEY   = "..."
GROQ_KEY   = "..."
```

### 3. Upload application

```bash
bash tools/upload.sh /dev/ttyACM0   # or /dev/ttyUSB0
```

## User Programs

User programs live in `userapp/` and are listed in `userapp/manifest.json`. They can be downloaded directly to the device via the **Get Program** menu option, which fetches from [cyberdreck-programs](https://github.com/alunmorris/cyberdreck-programs).

Current programs:

| File | Description |
|------|-------------|
| `sysinfo.py` | Memory and WiFi status |
| `airquality.py` | Air quality for Lecco, Italy |
| `oled-i2c-test.py` | SSD1306 128×32 OLED test (SDA=GPIO6, SCL=GPIO7) |
| `sim800l-sms.py` | SIM800L GSM — list received SMS (TX=GPIO8, RX=GPIO9) |

## Key Bindings

| Key | Action |
|-----|--------|
| Scroll wheel | Scroll history / navigate menus |
| Enter | Send message / confirm |
| Esc / Menu key | Open model menu |
| Delete | Delete file (file manager) |

## License

MIT
