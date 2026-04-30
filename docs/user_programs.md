# Writing User Programs for CRACK
##Date: 30 Apr 2026

User programs are plain MicroPython (v1.24.1)`.py` files stored in the root of the device filesystem. 
They are launched from the model menu via **r → Run a program**.

---

## Running a program

1. Press the **menu key** to open the model menu.
2. Press **r** — the file picker lists all user `.py` files.
3. Use the **scroll keys** to move the cursor, **Enter** to run.
4. When the program ends, **"Enter to exit"** appears at the bottom. Press **Enter** to return to the file picker.
5. **Menu key** at any time returns to the model menu.

Scroll keys work while the program is running, letting you review output that has scrolled off screen.

---

## Available globals

These names are available without importing:

| Name | Type | Notes |
|---|---|---|
| `print` | function | Writes to TFT display (see below) |
| `tft` | object | Raw display driver |
| `font14` | module | DejaVu Sans 14px — proportional |
| `mono13` | module | NotoSansMono 13px — monospaced |
| `_TFTTerminal` | class | Terminal emulator (see below) |
| `config` | module | Screen dimensions, colours, etc. |
| `time` | module | `sleep`, `sleep_ms`, `ticks_ms`, … |
| `sys` | module | |
| `gc` | module | `gc.collect()`, `gc.mem_free()` |
| `machine` | module | `Pin`, `I2C`, `SPI`, `reset()`, … |
| `network` | module | WiFi (already connected at app level) |

Everything else must be imported normally:

```python
import uos
import _thread
import ubinascii
```

---

## print()

`print()` writes to the TFT terminal using the proportional `font14`. All standard keyword arguments work:

```python
print("hello")                  # yellow text, newline at end
print("a", "b", sep=", ")      # "a, b"
print("no newline", end="")    # stay on same line
print("overwrite", end="\r")   # move to col 0, ready to overwrite
```

### Overwriting a line with `\r`

`\r` moves the write cursor to column 0 **without clearing** the line. Subsequent characters overwrite existing text in place:

```python
import time
for i in range(101):
    print(f"Progress: {i}%   ", end="\r")   # spaces pad over shorter previous text
    time.sleep_ms(50)
print()                                      # move to next line when done
```

---

## ANSI escape sequences

Both `print()` and the monospaced terminal understand a subset of VT100 escapes.
Use `end=""` to suppress the automatic newline.

### Cursor movement

| Sequence | Effect |
|---|---|
| `\x1b[nA` | Move cursor up *n* lines (default 1) |
| `\x1b[nB` | Move cursor down *n* lines (default 1) |
| `\x1b[H` | Move to top-left of visible screen |
| `\x1b[r;cH` | Move to row *r*, column *c* (1-indexed) |

### Line editing

| Sequence | Effect |
|---|---|
| `\x1b[2K` | Erase entire current line, col → 0 |

### Important: `\n` advances the cursor

`\n` moves the write position **down one line** (appending a new line if at the bottom).
The cursor position after `print()` depends on whether the string contains `\n`.

```python
print("Line A")             # writes "Line A", then \n moves cursor down
print("\x1b[1A", end="")   # move up 1 — now on "Line A" again
print("\x1b[2K", end="")   # erase "Line A"
print("Line A updated", end="")  # write replacement, no \n — stay here
```

If you include an explicit `\n` in the string **and** let `print` add one (`end="\n"`), the cursor moves twice. Use `end=""` with explicit `\n` when you need precise control.

---

## Monospaced terminal

`print()` uses proportional `font14`, so column positions don't align visually.
For aligned columns and box drawing, create a `_TFTTerminal` with `mono13`:

```python
tft.fill(0x0000)
term = _TFTTerminal(tft, None, font=mono13)

def mprint(*args, **kwargs):
    sep = kwargs.get('sep', ' ')
    end = kwargs.get('end', '\n')
    term.write(sep.join(str(a) for a in args) + end)
```

Pass `None` for `kb` — the terminal class does not poll the keyboard itself.

All ANSI escapes and `\r` overwrite work identically through `mprint`.

### Box drawing example

```python
import time

tft.fill(0x0000)
term = _TFTTerminal(tft, None, font=mono13)

def mprint(*args, **kwargs):
    sep = kwargs.get('sep', ' ')
    end = kwargs.get('end', '\n')
    term.write(sep.join(str(a) for a in args) + end)

mprint("+-------------------+")
mprint("| Counter:          |")
mprint("| Status:           |")
mprint("+-------------------+", end="")   # no \n — cursor stays on this line

for i in range(100):
    done = (i == 99)
    # cursor is on bottom line; up 2 reaches counter line
    mprint(f"\x1b[2A\x1b[2K| Counter: {i:<9}|", end="\n")
    mprint(f"\x1b[2K| Status:  {'done   ' if done else 'running':<9}|", end="\n")
    mprint("\x1b[2K+-------------------+", end="")
    time.sleep_ms(100)
```

---

## Screen dimensions

From `config`:

| Constant | Value | Meaning |
|---|---|---|
| `config.SCREEN_W` | 320 | Pixels wide |
| `config.SCREEN_H` | 240 | Pixels tall |
| `config.LINE_H` | 16 | Pixels per text row |
| `config.MAX_VIS` | 14 | Visible text rows |

The terminal occupies the full screen (14 rows of 42 characters). The bottom row is reserved for the **"Enter to exit"** prompt when the program ends.

---

## Direct display access

Bypass `print` and draw directly using `tft`:

```python
tft.fill(0x0000)                                    # clear screen (black)
tft.fill_rect(x, y, w, h, colour)                  # filled rectangle
tft.write(font14, "text", x, y, fg, bg)            # proportional text
tft.write(mono13, "text", x, y, fg, bg)            # monospaced text
tft.write_len(font14, "text")                       # pixel width of string

# Common RGB565 colours (from config)
config.COL_AI       # 0xF760  yellow
config.COL_USER     # 0x07FF  cyan
config.COL_ERROR    # 0xF800  red
```

---

## Network / API access

WiFi is usually already connected when a user program runs. Check first with `wifi_mgr`:

```python
import wifi_mgr

if not wifi_mgr.is_connected():
    wifi_mgr.load_creds()
    c = wifi_mgr._creds[0]
    wifi_mgr.connect(c['ssid'], c['pass'])
```

### HTTPS JSON API

`api._https_post` handles SSL, chunked transfer encoding, and memory-efficient reads.
Use it for any HTTPS JSON API:

```python
import api, json

resp = api._https_post(
    "api.example.com",                      # host
    "/v1/endpoint",                         # path
    {"Authorization": "Bearer TOKEN"},      # extra headers (dict)
    {"key": "value"}                        # request body (dict → JSON)
)
data = json.loads(resp)
print(data["result"])
```

### Call the built-in AI APIs

The app's API keys are in `secrets`. You can call Gemini, Grok, or Groq directly:

```python
import api, secrets

msgs = [{"role": "user", "text": "Hello"}]

# Gemini
reply = api.call_gemini(msgs, "gemini-3.1-flash-lite-preview", secrets.GEMINI_KEY)

# Grok
reply = api.call_grok(msgs, secrets.GROK_KEY)

# Groq
reply = api.call_groq(msgs, secrets.GROQ_KEY)

print(reply)
```

### Plain HTTP GET

No helper exists for plain HTTP — use raw sockets:

```python
import socket

s = socket.socket()
s.connect(socket.getaddrinfo("example.com", 80)[0][-1])
s.send(b"GET / HTTP/1.0\r\nHost: example.com\r\n\r\n")
print(s.recv(1024).decode())
s.close()
```

---

## Error handling

If your program raises an unhandled exception the exception type and message are shown in red, and **"Enter to exit"** appears. Press **Enter** to return to the file picker.

To catch errors yourself:

```python
try:
    risky_operation()
except Exception as e:
    print(f"Error: {e}")
```

---

## Tips

- **Characters**: `font14` contains ASCII and Cyrillic. `mono13` contains ASCII only (0x20–0x7e). Unicode box-drawing characters, arrows, and emoji will not render in either font.
- **Padding**: when overwriting with `\r`, pad shorter strings with spaces so remnants of longer text don't show: `f"{value:<20}"`.
- **Memory**: call `gc.collect()` before allocating large buffers. `gc.mem_free()` returns available heap bytes.
- **Exit cleanly**: at the top level of a MicroPython script, execution simply ends — the file picker resumes normally.
- **Avoid `input()`**: there is no stdin; use the keyboard via `hal_kb` if you need interactive input (`import hal_kb; hal_kb.poll()`).
- **GPIO**: `machine.Pin`, `I2C`, `SPI`, `ADC`, `PWM`, `UART`, and `Timer` are all available via `from machine import ...`. GPIO15 is the app status LED on ESP32-S2 mini (`config.LED_PIN`) — avoid it in user programs.
