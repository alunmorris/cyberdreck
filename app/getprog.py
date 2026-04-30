# getprog.py — download user programs from github.com/alunmorris/crack-programs
#300426 Change exit text to 'Menu'
import socket, ssl, json, gc
import wifi_mgr

REPO_HOST = "raw.githubusercontent.com"
REPO_BASE = "/alunmorris/crack-programs/main"

def _https_get(host, path):
    """Simple HTTPS GET — returns response body as bytes."""
    addr = socket.getaddrinfo(host, 443)[0][-1]
    s = socket.socket()
    s.settimeout(15)
    s.connect(addr)
    s = ssl.wrap_socket(s, server_hostname=host)
    req = (
        f"GET {path} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        "\r\n"
    ).encode()
    s.write(req)
    chunks = []
    try:
        while True:
            chunk = s.read(512)
            if not chunk:
                break
            chunks.append(bytes(chunk))
    finally:
        s.close()
    raw = b''.join(chunks)
    sep = raw.find(b"\r\n\r\n")
    if sep < 0:
        raise ValueError("Bad HTTP response")
    status = raw[:raw.find(b"\r\n")].decode()
    if " 200 " not in status:
        raise ValueError(status[:60])
    return raw[sep + 4:]


def _ensure_wifi():
    if wifi_mgr.is_connected():
        return True
    wifi_mgr.load_creds()
    if not wifi_mgr._creds:
        return False
    c = wifi_mgr._creds[0]
    return wifi_mgr.connect(c['ssid'], c['pass'])


def run(tft, kb):
    import config, time, uos
    import fonts.dejavu14_ru as font14

    tft.fill(0x0000)
    tft.write(font14, "Connecting...", 2, 0, config.COL_AI, 0x0000)

    if not _ensure_wifi():
        tft.fill(0x0000)
        tft.write(font14, "No WiFi", 2, 0, config.COL_ERROR, 0x0000)
        time.sleep(2)
        return

    tft.write(font14, "Loading manifest...", 2, config.LINE_H, config.COL_AI, 0x0000)
    try:
        gc.collect()
        data = _https_get(REPO_HOST, REPO_BASE + "/manifest.json")
        manifest = json.loads(data)
        gc.collect()
    except Exception as e:
        tft.fill(0x0000)
        tft.write(font14, "Manifest error:", 2, 0, config.COL_ERROR, 0x0000)
        tft.write(font14, str(e)[:40], 2, config.LINE_H, 0xFFFF, 0x0000)
        time.sleep(3)
        return

    sel    = 0
    n      = len(manifest) + 1   # entries + Menu
    ENTRY_H = 2                  # rows per entry: filename + description

    def _draw(status=""):
        tft.fill(0x0000)
        tft.write(font14, "Download a program:", 2, 0, 0x03E0, 0x0000)
        for i, entry in enumerate(manifest):
            y0 = (1 + i * ENTRY_H) * config.LINE_H
            y1 = y0 + config.LINE_H
            if i == sel:
                tft.fill_rect(0, y0, config.SCREEN_W, config.LINE_H, 0xFFFF)
                tft.write(font14, entry['file'][:38], 2, y0, 0x0000, 0xFFFF)
            else:
                tft.write(font14, entry['file'][:38], 2, y0, 0xFFFF, 0x0000)
            tft.write(font14, entry['desc'][:38], 2, y1, 0x4208, 0x0000)
        cancel_y = (config.MAX_VIS - 1) * config.LINE_H
        fg = 0x0000 if sel == len(manifest) else 0x07E0
        bg = 0xFFFF if sel == len(manifest) else 0x0000
        tft.fill_rect(0, cancel_y, config.SCREEN_W, config.LINE_H, bg)
        tft.write(font14, "Menu", 2, cancel_y, fg, bg)
        if status:
            sy = (1 + len(manifest) * ENTRY_H) * config.LINE_H
            if sy < cancel_y:
                tft.write(font14, status[:40], 2, sy, config.COL_AI, 0x0000)

    _draw()

    while True:
        time.sleep_ms(20)
        ev = kb.poll()
        if ev is None:
            continue
        t, ch = ev

        if t == kb.INPUT_SCROLL_DOWN:
            if sel > 0:
                sel -= 1
                _draw()
        elif t == kb.INPUT_SCROLL_UP:
            if sel < n - 1:
                sel += 1
                _draw()
        elif t == kb.INPUT_MODEL_MENU:
            return
        elif t == kb.INPUT_ENTER:
            if sel == len(manifest):
                return
            entry = manifest[sel]
            fname = entry['file']
            _draw(f"Downloading {fname}...")
            try:
                gc.collect()
                body = _https_get(REPO_HOST, REPO_BASE + "/" + fname)
                with open("/" + fname, "wb") as f:
                    f.write(body)
                gc.collect()
                _draw(f"Saved /{fname}")
                time.sleep(2)
            except Exception as e:
                _draw("Error: " + str(e)[:30])
                time.sleep(3)
        elif t == kb.INPUT_DELETE:
            if sel < len(manifest):
                fname = manifest[sel]['file']
                try:
                    uos.remove("/" + fname)
                    _draw(f"Deleted /{fname}")
                except OSError:
                    _draw(f"{fname} not on device")
                time.sleep(2)
                _draw()
