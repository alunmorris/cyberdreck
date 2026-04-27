# app/main.py
import time, gc
from machine import Pin

import display, ui, history, wifi_mgr, api, config, hal_kb, secrets
import fonts.dejavu14 as font14
from writer import Writer

# ── State ──────────────────────────────────────────────────────────────────────
_input_buf  = []       # list of chars
_cursor     = 0        # insertion point
_more_mode  = False    # True after AI reply
_invert     = True     # light theme

# Active model selection
_use_grok  = False
_use_groq  = False
_gemini_idx = 0        # index into config.GEMINI_MODELS

_tft  = None
_wri  = None
_wifi_ok    = False
_last_activity = 0
_last_wifi_check = 0

# ── Helpers ────────────────────────────────────────────────────────────────────
def _active_model_label():
    if _use_grok:  return config.GROK_MODEL
    if _use_groq:  return config.GROQ_MODEL
    return config.GEMINI_MODELS[_gemini_idx]

def _c3line(y, text, fg=0x0000, bg=0xC618):
    Writer.set_textpos(_tft, y, 2)
    _wri.set_textcolor(fg, bg)
    _wri.printstring(text)

def _refresh():
    history.rebuild_lines(measure_fn=ui._measure)
    ui.draw_history()
    ui.draw_input_bar(''.join(_input_buf), _cursor, _wifi_ok)

def _set_led(on):
    hal_kb.set_led(on)

# ── Model menu ─────────────────────────────────────────────────────────────────
def show_model_menu():
    """Display model selection menu; block until a valid key is pressed."""
    global _use_grok, _use_groq, _gemini_idx
    bg = 0xC618
    _tft.fill(bg)
    items = []
    for i, m in enumerate(config.GEMINI_MODELS, 1):
        items.append((str(i), m, False, False, i - 1))
    items.append(('5', config.GROK_MODEL,  True,  False, 0))
    items.append(('6', config.GROQ_MODEL,  False, True,  0))
    _c3line(0, "Select model:", 0x03E0, bg)
    for idx, (key, label, _, __, ___) in enumerate(items):
        _c3line((idx + 1) * config.LINE_H, f"{key} {label[:36]}", 0x0000, bg)

    while True:
        ev = hal_kb.poll()
        if ev is None:
            time.sleep_ms(20)
            continue
        ev_type, ch = ev
        if ev_type == hal_kb.INPUT_CHAR and ch.isdigit():
            for key, label, grok, groq, gidx in items:
                if ch == key:
                    _use_grok  = grok
                    _use_groq  = groq
                    _gemini_idx = gidx
                    history.add('ai', f"Model: {label}", display_only=True)
                    return

# ── WiFi connect flow ──────────────────────────────────────────────────────────
def ensure_wifi():
    """Ensure WiFi is connected, running AP scan flow if needed. Returns True."""
    global _wifi_ok
    if wifi_mgr.is_connected():
        _wifi_ok = True
        return True
    wifi_mgr.load_creds()
    if wifi_mgr._creds:
        ssid = wifi_mgr._creds[0]['ssid']
        pwd  = wifi_mgr._creds[0]['pass']
        if wifi_mgr.connect(ssid, pwd, show_status=True):
            _wifi_ok = True
            _set_led(True)
            return True
    # AP scan flow
    ok = wifi_mgr.select_ap(_tft, _wri)
    _wifi_ok = ok
    if ok:
        _set_led(True)
    return ok

# ── Send prompt ────────────────────────────────────────────────────────────────
def send_prompt():
    global _more_mode, _wifi_ok
    text = ''.join(_input_buf).strip()
    if not text:
        return
    _input_buf.clear()
    _cursor_set(0)
    history.add('user', text)
    _refresh()

    if not ensure_wifi():
        history.add('error', "No WiFi", display_only=True)
        _refresh()
        return

    history.add('ai', "...", display_only=True)
    _refresh()

    try:
        msgs = history.get_messages()
        if _use_grok:
            reply = api.call_grok(msgs, secrets.GROK_KEY)
        elif _use_groq:
            reply = api.call_groq(msgs, secrets.GROQ_KEY)
        else:
            reply = api.call_gemini(msgs, config.GEMINI_MODELS[_gemini_idx], secrets.GEMINI_KEY)
    except Exception as e:
        reply = f"Error: {e}"
    finally:
        # Remove the "..." placeholder
        if history._messages and history._messages[-1].get('display_only'):
            history._messages.pop()
            history._total_bytes -= 3

    history.add('ai', reply)
    _more_mode = True
    _refresh()
    gc.collect()

# ── Input buffer helpers ───────────────────────────────────────────────────────
def _cursor_set(pos):
    global _cursor
    _cursor = max(0, min(pos, len(_input_buf)))

def _insert_char(ch):
    _input_buf.insert(_cursor, ch)
    _cursor_set(_cursor + 1)

def _delete_back():
    if _cursor > 0:
        _input_buf.pop(_cursor - 1)
        _cursor_set(_cursor - 1)

def _delete_fwd():
    if _cursor < len(_input_buf):
        _input_buf.pop(_cursor)

# ── Main event loop ────────────────────────────────────────────────────────────
def loop():
    global _last_activity, _last_wifi_check, _wifi_ok, _more_mode
    while True:
        ev = hal_kb.poll()
        if ev is not None:
            _last_activity = time.ticks_ms()
            ev_type, ch = ev
            redraw = True
            if   ev_type == hal_kb.INPUT_CHAR:
                _insert_char(ch)
            elif ev_type == hal_kb.INPUT_BACKSPACE:
                _delete_back()
            elif ev_type == hal_kb.INPUT_DELETE:
                _delete_fwd()
            elif ev_type == hal_kb.INPUT_CURSOR_LEFT:
                _cursor_set(_cursor - 1)
            elif ev_type == hal_kb.INPUT_CURSOR_RIGHT:
                _cursor_set(_cursor + 1)
            elif ev_type == hal_kb.INPUT_ENTER:
                send_prompt()
                redraw = False
            elif ev_type == hal_kb.INPUT_SCROLL_UP:
                history.scroll_up(); history.rebuild_lines(measure_fn=ui._measure)
                ui.draw_history(); redraw = False
            elif ev_type == hal_kb.INPUT_SCROLL_DOWN:
                history.scroll_down(); history.rebuild_lines(measure_fn=ui._measure)
                ui.draw_history(); redraw = False
            elif ev_type == hal_kb.INPUT_NEW_CONV:
                history.clear(); _input_buf.clear(); _cursor_set(0)
                _more_mode = False; _refresh(); redraw = False
            elif ev_type == hal_kb.INPUT_MODEL_MENU:
                show_model_menu(); _refresh(); redraw = False
            else:
                redraw = False
            if redraw:
                ui.draw_input_bar(''.join(_input_buf), _cursor, _wifi_ok)

        # WiFi idle disconnect (60s without activity)
        now = time.ticks_ms()
        if (time.ticks_diff(now, _last_wifi_check) > 2000 and wifi_mgr.is_connected()):
            _last_wifi_check = now
            idle_s = time.ticks_diff(now, _last_activity) / 1000
            if idle_s > config.WIFI_IDLE_TIMEOUT:
                wifi_mgr.disconnect()
                _wifi_ok = False
                _set_led(False)
        elif not wifi_mgr.is_connected() and _wifi_ok:
            _wifi_ok = False
            _set_led(False)

        time.sleep_ms(10)

# ── Boot sequence ──────────────────────────────────────────────────────────────
def main():
    global _tft, _wri
    _tft = display.init()
    _wri = Writer(_tft, font14)
    ui.init(_tft)

    bg = 0xC618
    _c3line(0, "CRACK — USB keyboard init...", 0x0000, bg)

    found = hal_kb.init(timeout_ms=5000)
    if not found:
        _c3line(config.LINE_H, "Keyboard not found!", 0xF800, bg)
        time.sleep(2)

    wifi_mgr.load_creds()

    # Check for pre-seeded default credentials from secrets.py
    try:
        if secrets.WIFI_SSID_DEFAULT and not wifi_mgr._creds:
            wifi_mgr.insert_cred(secrets.WIFI_SSID_DEFAULT, secrets.WIFI_PASS_DEFAULT)
    except AttributeError:
        pass

    ensure_wifi()
    show_model_menu()
    _last_activity = time.ticks_ms()
    _refresh()
    loop()

main()
