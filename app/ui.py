# app/ui.py
import display, history, config
from writer import Writer
import fonts.dejavu14 as font14

_tft    = None
_writer = None
_invert = True   # True = light theme

def init(tft):
    global _tft, _writer
    _tft = tft
    _writer = Writer(tft, font14)

def _bg():
    return config.COL_INVERT_BG if _invert else config.COL_BG

def _measure(text):
    return _writer.stringlen(text)

def draw_history():
    """Render the chat history area."""
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
            col = config.COL_USER_LIGHT if _invert else config.COL_USER
            tw  = _measure(ln['text'])
            x   = config.SCREEN_W - tw - 2
        else:
            col = 0x0000 if _invert else config.COL_AI
            if ln['color'] == config.COL_ERROR:
                col = config.COL_ERROR
            x = 2
        Writer.set_textpos(_tft, y, x)
        _writer.printstring(ln['text'])
        y += config.LINE_H

def draw_input_bar(input_buf, cursor_pos, wifi_ok=True):
    """Render the input bar at the bottom of the screen."""
    bg  = _bg()
    fg  = 0x0000 if _invert else 0xFFFF
    prompt_col = config.COL_PROMPT if wifi_ok else config.COL_ERROR

    _tft.fill_rect(0, config.INPUT_Y, config.SCREEN_W, config.LINE_H, bg)

    Writer.set_textpos(_tft, config.INPUT_Y, 2)
    _writer.set_textcolor(prompt_col, bg)
    _writer.printstring('> ')
    prompt_w = _measure('> ') + 2

    _writer.set_textcolor(fg, bg)
    avail = config.SCREEN_W - prompt_w - 4
    start = cursor_pos
    while start > 0:
        test = input_buf[start-1:cursor_pos]
        if _measure(test) > avail - 2:
            break
        start -= 1
    disp = input_buf[start:]
    Writer.set_textpos(_tft, config.INPUT_Y, prompt_w)
    _writer.printstring(disp)

    pre   = input_buf[start:cursor_pos]
    cur_x = prompt_w + _measure(pre)
    _tft.fill_rect(cur_x, config.INPUT_Y + 2, 1, config.LINE_H - 4, fg)
