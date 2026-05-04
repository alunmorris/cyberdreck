# app/main.py
import esp
esp.osdebug(None)   # suppress ESP-IDF log output on UART so mpremote can enter raw REPL

import time, gc, _thread
from machine import Pin

import display, ui, history, wifi_mgr, api, config, hal_kb, secrets
import fonts.dejavu14_ru as font14

# ── State ──────────────────────────────────────────────────────────────────────
_input_buf  = []
_cursor     = 0
_more_mode  = False

_use_grok   = False
_use_groq   = False
_gemini_idx = 0

_tft        = None
_wifi_ok    = False
_rssi       = None
_last_activity   = 0
_last_wifi_check = 0

# ── Helpers ────────────────────────────────────────────────────────────────────
def _c3line(y, text, fg=0xFFFF, bg=0x0000):
    _tft.write(font14, text, 2, y, fg, bg)

def _refresh():
    history.rebuild_lines(measure_fn=ui._measure)
    ui.draw_history()
    ui.draw_input_bar(''.join(_input_buf), _cursor, _rssi)

def _model_label():
    if _use_grok: return config.GROK_MODEL
    if _use_groq: return config.GROQ_MODEL
    return config.GEMINI_MODELS[_gemini_idx]

def _new_conv():
    global _more_mode
    history.clear()
    _input_buf.clear()
    _cursor_set(0)
    _more_mode = False
    history.add('ai', 'Model: ' + _model_label(), display_only=True)
    _refresh()

# ── Model menu ─────────────────────────────────────────────────────────────────
def show_model_menu():
    global _use_grok, _use_groq, _gemini_idx
    bg = 0x0000
    items = []
    for i, m in enumerate(config.GEMINI_MODELS, 1):
        items.append((str(i), m, False, False, i - 1))
    n = len(config.GEMINI_MODELS)
    items.append((str(n + 1), config.GROK_MODEL,  True,  False, 0))
    items.append((str(n + 2), config.GROQ_MODEL,  False, True,  0))

    def _draw_menu():
        _tft.fill(bg)
        _tft.write(font14, "Select model:", 2, 0, 0x03E0, bg)
        for idx, (key, label, _, __, ___) in enumerate(items):
            _tft.write(font14, f"{key} {label[:36]}", 2, (idx + 1) * config.LINE_H, 0xFFFF, bg)
        base = len(items) + 2
        _tft.write(font14, "m MicroPython REPL", 2, base * config.LINE_H, 0xFFFF, bg)
        _tft.write(font14, "f File manager",      2, (base + 1) * config.LINE_H, 0xFFFF, bg)
        _tft.write(font14, "g Get programs",     2, (base + 2) * config.LINE_H, 0xFFFF, bg)
        _tft.write(font14, "w WiFi setup",       2, (base + 3) * config.LINE_H, 0xFFFF, bg)

    _draw_menu()

    while True:
        ev = hal_kb.poll()
        if ev is None:
            time.sleep_ms(20)
            continue
        ev_type, ch = ev
        if ev_type == hal_kb.INPUT_CHAR:
            if ch == 'm':
                import repl_term
                repl_term.run(_tft, hal_kb)
                _draw_menu()
                continue
            if ch == 'f':
                import repl_term
                repl_term.show_file_manager(_tft, hal_kb)
                _draw_menu()
                continue
            if ch == 'g':
                import getprog
                getprog.run(_tft, hal_kb)
                _draw_menu()
                continue
            if ch == 'w':
                wifi_mgr.select_ap(_tft, hal_kb)
                _draw_menu()
                continue
            if ch.isdigit():
                for key, label, grok, groq, gidx in items:
                    if ch == key:
                        _use_grok   = grok
                        _use_groq   = groq
                        _gemini_idx = gidx
                        history.add('ai', f"Model: {label}", display_only=True)
                        return False

# ── WiFi connect flow ──────────────────────────────────────────────────────────
def ensure_wifi():
    global _wifi_ok
    if wifi_mgr.is_connected():
        _wifi_ok = True
        return True
    wifi_mgr.load_creds()
    if wifi_mgr._creds:
        import fonts.dejavu14_ru as font14
        ssid = wifi_mgr._creds[0]['ssid']
        pwd  = wifi_mgr._creds[0]['pass']
        _tft.fill(0x0000)
        _tft.write(font14, "WiFi: scanning...", 2, 0, config.COL_AI, 0x0000)
        aps = wifi_mgr.scan_aps()
        visible = {s for s, _ in aps}
        if ssid in visible:
            _tft.fill(0x0000)
            _tft.write(font14, f"WiFi: {ssid[:28]}", 2, 0, config.COL_AI, 0x0000)
            _tft.write(font14, "connecting...", 2, config.LINE_H, 0xFFFF, 0x0000)
            if wifi_mgr.connect(ssid, pwd):
                _wifi_ok = True
                hal_kb.set_led(True)
                return True
        else:
            ok = wifi_mgr.select_ap(_tft, hal_kb, aps)
            _wifi_ok = ok
            if ok:
                hal_kb.set_led(True)
            return ok
    ok = wifi_mgr.select_ap(_tft, hal_kb)
    _wifi_ok = ok
    if ok:
        hal_kb.set_led(True)
    return ok

# ── API call ───────────────────────────────────────────────────────────────────
def _call_api(prompt):
    global _more_mode
    history.add('user', prompt)
    _refresh()

    if not ensure_wifi():
        history.add('error', "No WiFi", display_only=True)
        _refresh()
        return

    history.add('ai', '.', display_only=True)
    _refresh()

    result = [None]
    done   = [False]

    def _api_thread():
        try:
            msgs = history.get_messages()
            for attempt in range(2):
                try:
                    if _use_grok:
                        result[0] = api.call_grok(msgs, secrets.GROK_KEY)
                    elif _use_groq:
                        result[0] = api.call_groq(msgs, secrets.GROQ_KEY)
                    else:
                        result[0] = api.call_gemini(msgs, config.GEMINI_MODELS[_gemini_idx], secrets.GEMINI_KEY)
                    break
                except OSError as e:
                    if attempt == 0 and 'dns:' in str(e):
                        time.sleep_ms(1000)
                        continue
                    raise
        except Exception as e:
            result[0] = f"Error: {e}"
        done[0] = True

    _thread.start_new_thread(_api_thread, ())

    dots = 1
    last_dot = time.ticks_ms()
    while not done[0]:
        if time.ticks_diff(time.ticks_ms(), last_dot) >= 4000:
            dots += 1
            if history._messages and history._messages[-1].get('display_only'):
                history._messages[-1]['text'] = '.' * dots
                history.rebuild_lines(measure_fn=ui._measure)
                ui.draw_history()
            last_dot = time.ticks_ms()
        time.sleep_ms(100)

    if history._messages and history._messages[-1].get('display_only'):
        dot_len = len(history._messages[-1]['text'])
        history._messages.pop()
        history._total_bytes -= dot_len

    reply = result[0] or "Error: no response"
    history.add('ai', reply, display_only=reply.startswith("Error:"))
    _more_mode = True
    _refresh()
    gc.collect()

# ── Send prompt ────────────────────────────────────────────────────────────────
def send_prompt():
    text = ''.join(_input_buf).strip()

    if text == 'new':
        _input_buf.clear(); _cursor_set(0)
        _new_conv()
        return
    if text == 'more':
        _input_buf.clear(); _cursor_set(0)
        _call_api('Tell me more')
        return
    if text == 'menu':
        _input_buf.clear(); _cursor_set(0)
        show_model_menu(); _new_conv()
        return

    if not text:
        if not history._messages:
            return
        _call_api('Tell me more')
        return

    _input_buf.clear()
    _cursor_set(0)
    _call_api(text)

# ── Input buffer helpers ───────────────────────────────────────────────────────
def _cursor_set(pos):
    global _cursor
    _cursor = max(0, min(pos, len(_input_buf)))

def _insert_char(ch):
    global _more_mode
    _more_mode = False
    _input_buf.insert(_cursor, ch)
    _cursor_set(_cursor + 1)

def _delete_back():
    global _more_mode
    if _cursor > 0:
        _input_buf.pop(_cursor - 1)
        _cursor_set(_cursor - 1)
        if not _input_buf and history._messages:
            _more_mode = True

def _delete_fwd():
    global _more_mode
    if _cursor < len(_input_buf):
        _input_buf.pop(_cursor)
        if not _input_buf and history._messages:
            _more_mode = True

# ── Main event loop ────────────────────────────────────────────────────────────
def loop():
    global _last_activity, _last_wifi_check, _wifi_ok, _rssi, _more_mode
    while True:
        ev = hal_kb.poll()
        if ev is not None:
            _last_activity = time.ticks_ms()
            ev_type, ch = ev
            redraw = True
            if   ev_type == hal_kb.INPUT_CHAR:         _insert_char(ch)
            elif ev_type == hal_kb.INPUT_BACKSPACE:    _delete_back()
            elif ev_type == hal_kb.INPUT_DELETE:       _delete_fwd()
            elif ev_type == hal_kb.INPUT_CURSOR_LEFT:  _cursor_set(_cursor - 1)
            elif ev_type == hal_kb.INPUT_CURSOR_RIGHT: _cursor_set(_cursor + 1)
            elif ev_type == hal_kb.INPUT_ENTER:
                send_prompt(); redraw = False
            elif ev_type == hal_kb.INPUT_MORE:
                if _more_mode: _call_api('Tell me more')
                redraw = False
            elif ev_type == hal_kb.INPUT_SCROLL_UP:
                old = history.scroll_offset
                history.scroll_down(config.MAX_VIS // 2)
                if history.scroll_offset != old:
                    history.rebuild_lines(measure_fn=ui._measure)
                    ui.draw_history()
                redraw = False
            elif ev_type == hal_kb.INPUT_SCROLL_DOWN:
                old = history.scroll_offset
                history.scroll_up(config.MAX_VIS // 2)
                if history.scroll_offset != old:
                    history.rebuild_lines(measure_fn=ui._measure)
                    ui.draw_history()
                redraw = False
            elif ev_type == hal_kb.INPUT_NEW_CONV:
                _new_conv(); redraw = False
            elif ev_type == hal_kb.INPUT_MODEL_MENU:
                if show_model_menu(): return
                _refresh(); redraw = False
            else:
                redraw = False
            if redraw:
                ui.draw_input_bar(''.join(_input_buf), _cursor, _rssi)

        now = time.ticks_ms()
        if time.ticks_diff(now, _last_wifi_check) > 2000:
            _last_wifi_check = now
            if wifi_mgr.is_connected():
                _rssi = wifi_mgr.rssi()
                if time.ticks_diff(now, _last_activity) / 1000 > config.WIFI_IDLE_TIMEOUT:
                    wifi_mgr.disconnect()
                    _wifi_ok = False
                    _rssi = None
                    hal_kb.set_led(False)
            elif _wifi_ok:
                _wifi_ok = False
                _rssi = None
                hal_kb.set_led(False)

        time.sleep_ms(10)

# ── Boot sequence ──────────────────────────────────────────────────────────────
def main():
    global _tft
    _tft = display.init()
    ui.init(_tft)

    _tft.fill(0x0000)
    _c3line(0, f"Cyberdreck {config.VERSION}")

    wifi_mgr.load_creds()
    try:
        if secrets.WIFI_SSID_DEFAULT and not wifi_mgr._creds:
            wifi_mgr.insert_cred(secrets.WIFI_SSID_DEFAULT, secrets.WIFI_PASS_DEFAULT)
    except AttributeError:
        pass

    _c3line(config.LINE_H, "WiFi: connecting...")
    _c3line(config.LINE_H * 2, "USB keyboard init...")

    found = hal_kb.init(timeout_ms=5000)
    if not found:
        _c3line(config.LINE_H * 2, "Keyboard not found!", 0xF800)
        time.sleep(2)

    global _rssi
    ensure_wifi()
    if wifi_mgr.is_connected():
        _rssi = wifi_mgr.rssi()
        ssid  = wifi_mgr._wlan.config('ssid')
        _c3line(config.LINE_H, f"WiFi: {ssid[:20]} {_rssi}dBm")
    else:
        _rssi = None
        _c3line(config.LINE_H, "WiFi: not connected", config.COL_ERROR)
    time.sleep(1)
    if show_model_menu():
        return
    _last_activity = time.ticks_ms()
    _refresh()
    loop()

main()
# After main() returns (REPL selected), MicroPython drops to interactive REPL on UART.
