# Writing User Programs for CRACK

User programs are plain MicroPython `.py` files stored in the root of the device filesystem. They are launched from the model menu via **r → Run a program**.

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
| `font14` | module | DejaVu 14px font |
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

`print()` writes to the TFT terminal, not UART. All standard keyword arguments work:

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

The TFT terminal understands a useful subset of VT100 escapes. All use `print(..., end="")` so no extra newline is added.

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

In the terminal, `\n` moves the write position **down one line** (or appends a new line if already at the bottom). This means the cursor position after a `print()` call depends on whether the string contains `\n`.

```python
print("Line A")             # writes "Line A", then \n moves cursor down
print("\x1b[1A", end="")   # move up 1 — now on "Line A" again
print("\x1b[2K", end="")   # erase "Line A"
print("Line A updated", end="")  # write replacement, no \n — stay here
```

If you include an explicit `\n` in the string **and** let `print` add one (`end="\n"`), the cursor moves twice. Use `end=""` with explicit `\n` in the string when you need precise control.

### Multi-line status display example

```python
import time

# Draw a fixed layout (ASCII only — font has no box-drawing characters)
print("+-------------------+")
print("| Counter:          |")
print("| Status:           |")
print("+-------------------+")

for i in range(100):
    # Update counter on row 2, col 11 (1-indexed)
    print(f"\x1b[2;11H{i:5}", end="")
    # Update status on row 3, col 11
    print(f"\x1b[3;11H{'running' if i < 99 else 'done   '}", end="")
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

You can bypass `print` and draw directly using `tft`:

```python
tft.fill(0x0000)                                    # clear screen (black)
tft.fill_rect(x, y, w, h, colour)                  # filled rectangle
tft.write(font14, "text", x, y, fg, bg)            # text at pixel position
tft.write_len(font14, "text")                       # pixel width of text

# Common RGB565 colours (from config)
config.COL_AI       # 0xF760  yellow
config.COL_USER     # 0x07FF  cyan
config.COL_ERROR    # 0xF800  red
```

Mix `tft` drawing with `print` freely — they share the same display.

---

## Error handling

If your program raises an unhandled exception the terminal clears, the exception type and message are shown in red, and **"Enter to exit"** appears. Press **Enter** to return to the file picker.

To catch errors yourself:

```python
try:
    risky_operation()
except Exception as e:
    print(f"Error: {e}", end="\n")
```

---

## Tips

- **Characters**: the font (`dejavu14_ru`) contains ASCII and Cyrillic only. Unicode box-drawing characters, arrows, emoji, etc. will not render — use ASCII equivalents (`+`, `-`, `|`).
- **Memory**: call `gc.collect()` before allocating large buffers. `gc.mem_free()` returns available heap bytes.
- **Padding**: when overwriting with `\r`, pad shorter strings with spaces so remnants of longer text don't show: `f"{value:<20}"`.
- **Exit early**: `return` at the top level of a script raises `SystemExit` in CPython but in MicroPython simply ends execution — the file picker will resume normally.
- **Avoid `input()`**: there is no stdin; use the keyboard via `hal_kb` if you need interactive input (import it and call `hal_kb.poll()`).
