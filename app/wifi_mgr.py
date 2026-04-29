# app/wifi_mgr.py
import network, time, esp32, config

PREFS_MAX = 9
_wlan     = network.WLAN(network.STA_IF)
_wlan.active(True)

_creds = []   # list of {'ssid': str, 'pass': str}

def load_creds():
    global _creds
    _creds = []
    try:
        nvs = esp32.NVS("wifi")
        n = nvs.get_i32("n")
        for i in range(min(n, PREFS_MAX)):
            buf = bytearray(33)
            nb  = nvs.get_blob(f"s{i}", buf)
            ssid = buf[:nb].decode()
            buf2 = bytearray(64)
            nb2 = nvs.get_blob(f"p{i}", buf2)
            pwd  = buf2[:nb2].decode()
            _creds.append({'ssid': ssid, 'pass': pwd})
    except Exception:
        pass

def save_creds():
    nvs = esp32.NVS("wifi")
    nvs.set_i32("n", len(_creds))
    for i, c in enumerate(_creds):
        nvs.set_blob(f"s{i}", c['ssid'].encode())
        nvs.set_blob(f"p{i}", c['pass'].encode())
    nvs.commit()

def insert_cred(ssid, password):
    global _creds
    _creds = [c for c in _creds if c['ssid'] != ssid]
    _creds.insert(0, {'ssid': ssid, 'pass': password})
    if len(_creds) > PREFS_MAX:
        _creds = _creds[:PREFS_MAX]
    save_creds()

def find_pass(ssid):
    for c in _creds:
        if c['ssid'] == ssid:
            return c['pass'] if c['pass'] else None
    return None

def connect(ssid, password, show_status=True):
    _wlan.disconnect()
    _wlan.connect(ssid, password)
    for _ in range(config.WIFI_MAX_ATTEMPTS):
        if _wlan.isconnected():
            return True
        time.sleep(config.WIFI_RETRY_DELAY)
    return False

def disconnect():
    _wlan.disconnect()

def is_connected():
    return _wlan.isconnected()

def rssi():
    if not _wlan.isconnected():
        return -100
    return _wlan.status('rssi')

def scan_aps():
    results = _wlan.scan()
    seen = {}
    for r in results:
        ssid = r[0].decode() if isinstance(r[0], bytes) else r[0]
        rssi_val = r[3]
        if ssid and (ssid not in seen or rssi_val > seen[ssid]):
            seen[ssid] = rssi_val
    return sorted(seen.items(), key=lambda x: -x[1])[:9]

def _draw_ap_list(aps, tft):
    import fonts.dejavu14_ru as font14
    bg = config.COL_INVERT_BG
    tft.fill(bg)
    tft.write(font14, "Select WiFi:", 2, 0, 0x03E0, bg)
    for i, (ssid, db) in enumerate(aps):
        y = (i + 1) * config.LINE_H
        if y + config.LINE_H > config.SCREEN_H:
            break
        tft.write(font14, f"{i+1} {ssid[:22]} {db}dB", 2, y, 0x0000, bg)

def ap_picker(tft):
    """Scan and show AP list. Returns (ssid, rssi) or None."""
    from hal_kb import poll, INPUT_CHAR, INPUT_ENTER
    aps = scan_aps()
    if not aps:
        return None
    _draw_ap_list(aps, tft)
    while True:
        ev = poll()
        if ev is None:
            time.sleep_ms(20)
            continue
        ev_type, ch = ev
        if ev_type == INPUT_CHAR and ch.isdigit():
            idx = int(ch) - 1
            if 0 <= idx < len(aps):
                return aps[idx]
        if ev_type == INPUT_ENTER:
            return None

def enter_password(ssid, tft):
    """Show password entry. Returns typed password."""
    from hal_kb import poll, INPUT_CHAR, INPUT_BACKSPACE, INPUT_ENTER, INPUT_CURSOR_LEFT, INPUT_CURSOR_RIGHT
    import ui, fonts.dejavu14_ru as font14
    bg = config.COL_INVERT_BG
    tft.fill(bg)
    tft.write(font14, "Password for:", 2, 0, 0xFFE0, bg)
    tft.write(font14, ssid[:36], 2, config.LINE_H, 0x0000, bg)
    buf = []; cursor = 0
    while True:
        ui.draw_input_bar(''.join(buf), cursor)
        ev = poll()
        if ev is None:
            time.sleep_ms(20)
            continue
        ev_type, ch = ev
        if ev_type == INPUT_ENTER:
            return ''.join(buf)
        elif ev_type == INPUT_CHAR and len(buf) < 63:
            buf.insert(cursor, ch); cursor += 1
        elif ev_type == INPUT_BACKSPACE and cursor > 0:
            buf.pop(cursor - 1); cursor -= 1
        elif ev_type == INPUT_CURSOR_LEFT and cursor > 0:
            cursor -= 1
        elif ev_type == INPUT_CURSOR_RIGHT and cursor < len(buf):
            cursor += 1

def select_ap(tft):
    """Full flow: scan -> pick -> password -> connect. Returns True if connected."""
    choice = ap_picker(tft)
    if choice is None:
        return False
    ssid, _ = choice
    stored = find_pass(ssid)
    password = stored if stored is not None else enter_password(ssid, tft)
    ok = connect(ssid, password, show_status=True)
    if ok:
        insert_cred(ssid, password)
    else:
        insert_cred(ssid, '')
    return ok
