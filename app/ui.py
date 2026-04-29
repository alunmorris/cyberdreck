# app/ui.py
import history, config
import fonts.dejavu14_ru as font14

_tft = None

def init(tft):
    global _tft
    _tft = tft

def _measure(text):
    return _tft.write_len(font14, text)

def _bg():
    return 0x0000   # black background

def draw_history():
    bg = _bg()
    _tft.fill_rect(0, 0, config.SCREEN_W, config.HIST_H, bg)
    if not history.lines:
        return
    n = len(history.lines)
    first = max(0, n - config.MAX_VIS - history.scroll_offset)
    last  = min(n, first + config.MAX_VIS)
    y = 0
    for i in range(first, last):
        ln = history.lines[i]
        if ln['is_user']:
            col = config.COL_USER
            tw  = _measure(ln['text'])
            x   = config.SCREEN_W - tw - 2
        else:
            col = config.COL_ERROR if ln['color'] == config.COL_ERROR else config.COL_AI
            x   = 2
        _tft.write(font14, ln['text'], x, y, col, bg)
        y += config.LINE_H

# WiFi bars: 4 bars × 2px wide + 3 × 1px gap = 11px total
_BAR_W   = 2
_BAR_GAP = 1
_N_BARS  = 4
_IND_W   = _N_BARS * _BAR_W + (_N_BARS - 1) * _BAR_GAP   # 11
_IND_X   = config.SCREEN_W - _IND_W - 2
_DIM     = 0x4208   # dark grey for inactive bars

def _draw_wifi_bars(rssi, bg):
    h  = config.LINE_H - 4
    y0 = config.INPUT_Y + 2
    if rssi is None:
        levels, col, dim = 0, 0x0000, 0xF800   # disconnected — red inactive
    elif rssi >= -65:
        levels, col, dim = 4, 0x07E0, _DIM     # green
    elif rssi >= -72:
        levels, col, dim = 3, 0x07E0, _DIM
    elif rssi >= -80:
        levels, col, dim = 2, 0xFFE0, _DIM     # yellow
    else:
        levels, col, dim = 1, 0xF800, _DIM     # red
    for i in range(_N_BARS):
        bh = max(2, h * (i + 1) // _N_BARS)
        bx = _IND_X + i * (_BAR_W + _BAR_GAP)
        by = y0 + h - bh
        _tft.fill_rect(bx, by, _BAR_W, bh, col if i < levels else dim)

def draw_input_bar(input_buf, cursor_pos, rssi=None):
    bg         = _bg()
    fg         = 0xFFFF
    prompt_col = 0xFFFF if rssi is not None else config.COL_ERROR

    _tft.fill_rect(0, config.INPUT_Y, config.SCREEN_W, config.LINE_H, bg)

    prompt = '> '
    _tft.write(font14, prompt, 2, config.INPUT_Y, prompt_col, bg)
    prompt_w = _measure(prompt) + 2

    avail = config.SCREEN_W - prompt_w - _IND_W - 6
    start = cursor_pos
    while start > 0:
        if _measure(input_buf[start - 1:cursor_pos]) > avail - 2:
            break
        start -= 1
    disp = input_buf[start:]
    _tft.write(font14, disp, prompt_w, config.INPUT_Y, fg, bg)

    cur_x = prompt_w + _measure(input_buf[start:cursor_pos])
    _tft.fill_rect(cur_x, config.INPUT_Y + 2, 1, config.LINE_H - 4, fg)

    _draw_wifi_bars(rssi, bg)
