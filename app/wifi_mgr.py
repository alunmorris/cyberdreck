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

def connect(ssid, password):
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

def _rssi_bars(db):
    if db >= -55: return "####"
    if db >= -65: return "###."
    if db >= -75: return "##.."
    if db >= -85: return "#..."
    return "...."

def _draw_ap_list(tft, aps, sel):
    import fonts.dejavu14_ru as font14
    tft.fill(0x0000)
    tft.write(font14, "Select WiFi:", 2, 0, 0x03E0, 0x0000)
    for i, (ssid, db) in enumerate(aps):
        y = (i + 1) * config.LINE_H
        label = f"{ssid[:24]} {_rssi_bars(db)}"
        if i == sel:
            tft.fill_rect(0, y, config.SCREEN_W, config.LINE_H, 0xFFFF)
            tft.write(font14, label, 2, y, 0x0000, 0xFFFF)
        else:
            tft.write(font14, label, 2, y, 0xFFFF, 0x0000)

def ap_picker(tft, kb):
    """Scan and show AP list. Returns (ssid, rssi) or None if cancelled."""
    import fonts.dejavu14_ru as font14
    while True:
        tft.fill(0x0000)
        tft.write(font14, "Scanning WiFi...", 2, 0, config.COL_AI, 0x0000)
        aps = scan_aps()
        if aps:
            break
        tft.fill(0x0000)
        tft.write(font14, "No networks found", 2, 0, config.COL_ERROR, 0x0000)
        tft.write(font14, "Enter: retry  Menu: skip", 2, config.LINE_H * 2, 0xFFFF, 0x0000)
        while True:
            time.sleep_ms(20)
            ev = kb.poll()
            if ev is None:
                continue
            t, _ = ev
            if t == kb.INPUT_ENTER:
                break          # re-scan
            if t == kb.INPUT_MODEL_MENU:
                return None    # give up
    sel = 0
    _draw_ap_list(tft, aps, sel)
    while True:
        time.sleep_ms(20)
        ev = kb.poll()
        if ev is None:
            continue
        t, _ = ev
        if t == kb.INPUT_SCROLL_DOWN and sel > 0:
            sel -= 1
            _draw_ap_list(tft, aps, sel)
        elif t == kb.INPUT_SCROLL_UP and sel < len(aps) - 1:
            sel += 1
            _draw_ap_list(tft, aps, sel)
        elif t == kb.INPUT_ENTER:
            return aps[sel]
        elif t == kb.INPUT_MODEL_MENU:
            return None

def enter_password(tft, kb, ssid):
    """Show password entry. Returns typed string, or None if cancelled."""
    import fonts.dejavu14_ru as font14
    import ui
    tft.fill(0x0000)
    tft.write(font14, "Password for:", 2, 0, config.COL_AI, 0x0000)
    tft.write(font14, ssid[:36], 2, config.LINE_H, 0xFFFF, 0x0000)
    buf = []; cursor = 0
    while True:
        ui.draw_input_bar(''.join(buf), cursor)
        time.sleep_ms(20)
        ev = kb.poll()
        if ev is None:
            continue
        t, ch = ev
        if t == kb.INPUT_ENTER:
            return ''.join(buf)
        elif t == kb.INPUT_MODEL_MENU:
            return None
        elif t == kb.INPUT_CHAR and len(buf) < 63:
            buf.insert(cursor, ch); cursor += 1
        elif t == kb.INPUT_BACKSPACE and cursor > 0:
            buf.pop(cursor - 1); cursor -= 1
        elif t == kb.INPUT_CURSOR_LEFT and cursor > 0:
            cursor -= 1
        elif t == kb.INPUT_CURSOR_RIGHT and cursor < len(buf):
            cursor += 1

def select_ap(tft, kb):
    """Full flow: scan → pick → password → connect. Returns True if connected."""
    import fonts.dejavu14_ru as font14
    while True:                          # outer: re-scan loop
        choice = ap_picker(tft, kb)
        if choice is None:
            return False
        ssid, _ = choice

        while True:                      # inner: connect loop for this AP
            stored = find_pass(ssid)
            password = stored if stored is not None else enter_password(tft, kb, ssid)
            if password is None:
                return False

            tft.fill(0x0000)
            tft.write(font14, "Connecting...", 2, 0, config.COL_AI, 0x0000)
            tft.write(font14, ssid[:36], 2, config.LINE_H, 0xFFFF, 0x0000)

            if connect(ssid, password):
                insert_cred(ssid, password)
                return True

            insert_cred(ssid, '')        # blank stored pass → re-prompt next iteration

            tft.fill(0x0000)
            tft.write(font14, f"Failed: {ssid[:26]}", 2, 0, config.COL_ERROR, 0x0000)
            tft.write(font14, "Enter: retry password", 2, config.LINE_H * 2, 0xFFFF, 0x0000)
            tft.write(font14, "Del:   new scan",       2, config.LINE_H * 3, 0xFFFF, 0x0000)
            tft.write(font14, "Menu:  cancel",         2, config.LINE_H * 4, 0xFFFF, 0x0000)

            action = None
            while action is None:
                time.sleep_ms(20)
                ev = kb.poll()
                if ev is None:
                    continue
                t, _ = ev
                if   t == kb.INPUT_ENTER:       action = 'retry'
                elif t == kb.INPUT_DELETE:      action = 'scan'
                elif t == kb.INPUT_MODEL_MENU:  action = 'cancel'

            if action == 'cancel':
                return False
            if action == 'scan':
                break                    # break inner → outer re-scan
            # action == 'retry': inner loop continues, find_pass returns None → re-prompt
