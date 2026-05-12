# getprog.py — download user programs from a GitHub repo
# 120526 v1.1 — default repo changed to cyberdreck-examples; custom repo input added
import socket, ssl, json, gc
import wifi_mgr

REPO_HOST    = "raw.githubusercontent.com"
DEFAULT_REPO = "alunmorris/cyberdreck-examples"

def _https_get(host, path):
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


def _type_repo(tft, kb, font14, config):
    """Full-screen text input for a repo name (user/repo). Returns string or None."""
    import time
    text = list(DEFAULT_REPO)

    def _draw():
        tft.fill(0x0000)
        tft.write(font14, "Enter repo (user/name):", 2, 0, 0x03E0, 0x0000)
        tft.write(font14, "Enter=confirm  Menu=cancel", 2, config.LINE_H, 0x4208, 0x0000)
        s = ''.join(text)
        avail = config.SCREEN_W - 4
        # show as much of the text as fits, right-aligned to cursor
        while tft.write_len(font14, s) > avail:
            s = s[1:]
        tft.fill_rect(0, config.LINE_H * 3, config.SCREEN_W, config.LINE_H, 0x0000)
        tft.write(font14, s, 2, config.LINE_H * 3, 0xFFFF, 0x0000)
        cx = 2 + tft.write_len(font14, s)
        tft.fill_rect(cx, config.LINE_H * 3 + 2, 1, config.LINE_H - 4, 0xFFFF)

    _draw()
    while True:
        time.sleep_ms(20)
        ev = kb.poll()
        if ev is None:
            continue
        t, ch = ev
        if t == kb.INPUT_MODEL_MENU:
            return None
        elif t == kb.INPUT_ENTER:
            result = ''.join(text).strip()
            return result if result else None
        elif t == kb.INPUT_BACKSPACE or t == kb.INPUT_DELETE:
            if text:
                text.pop()
                _draw()
        elif t == kb.INPUT_CHAR and ch:
            text.append(ch)
            _draw()


def _browse(tft, kb, font14, config, repo, manifest):
    """Browse and download from a loaded manifest. Returns True to reload, False to exit."""
    import time, uos

    # entries + "Custom repo..." + "Menu"
    IDX_CUSTOM = len(manifest)
    IDX_MENU   = len(manifest) + 1
    n          = len(manifest) + 2
    ENTRY_H    = 2
    sel        = 0

    def _draw(status=""):
        tft.fill(0x0000)
        short_repo = repo.split('/')[-1] if '/' in repo else repo
        tft.write(font14, short_repo[:38], 2, 0, 0x03E0, 0x0000)
        for i, entry in enumerate(manifest):
            y0 = (1 + i * ENTRY_H) * config.LINE_H
            y1 = y0 + config.LINE_H
            if i == sel:
                tft.fill_rect(0, y0, config.SCREEN_W, config.LINE_H, 0xFFFF)
                tft.write(font14, entry['file'][:38], 2, y0, 0x0000, 0xFFFF)
            else:
                tft.write(font14, entry['file'][:38], 2, y0, 0xFFFF, 0x0000)
            tft.write(font14, entry['desc'][:38], 2, y1, 0x4208, 0x0000)

        cancel_y  = (config.MAX_VIS - 1) * config.LINE_H
        custom_y  = cancel_y - config.LINE_H

        # "Custom repo..." row
        fg = 0x0000 if sel == IDX_CUSTOM else 0x07FF
        bg = 0xFFFF if sel == IDX_CUSTOM else 0x0000
        tft.fill_rect(0, custom_y, config.SCREEN_W, config.LINE_H, bg)
        tft.write(font14, "Custom repo...", 2, custom_y, fg, bg)

        # "Menu" row
        fg = 0x0000 if sel == IDX_MENU else 0x07E0
        bg = 0xFFFF if sel == IDX_MENU else 0x0000
        tft.fill_rect(0, cancel_y, config.SCREEN_W, config.LINE_H, bg)
        tft.write(font14, "Menu", 2, cancel_y, fg, bg)

        if status:
            sy = (1 + len(manifest) * ENTRY_H) * config.LINE_H
            if sy < custom_y:
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
            return False
        elif t == kb.INPUT_ENTER:
            if sel == IDX_MENU:
                return False
            elif sel == IDX_CUSTOM:
                return True   # signal caller to prompt for new repo
            else:
                entry = manifest[sel]
                fname = entry['file']
                _draw(f"Downloading {fname}...")
                try:
                    gc.collect()
                    body = _https_get(REPO_HOST, f"/{repo}/main/{fname}")
                    with open("/" + fname, "wb") as f:
                        f.write(body)
                    gc.collect()
                    _draw(f"Saved /{fname}")
                    time.sleep(2)
                except Exception as e:
                    _draw("Error: " + str(e)[:30])
                    time.sleep(3)
                _draw()
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


def run(tft, kb):
    import config, time
    import fonts.dejavu14_ru as font14

    tft.fill(0x0000)
    tft.write(font14, "Connecting...", 2, 0, config.COL_AI, 0x0000)

    if not _ensure_wifi():
        tft.fill(0x0000)
        tft.write(font14, "No WiFi", 2, 0, config.COL_ERROR, 0x0000)
        time.sleep(2)
        return

    repo = DEFAULT_REPO

    while True:
        tft.fill(0x0000)
        tft.write(font14, "Loading manifest...", 2, 0, config.COL_AI, 0x0000)
        try:
            gc.collect()
            data = _https_get(REPO_HOST, f"/{repo}/main/manifest.json")
            manifest = json.loads(data)
            gc.collect()
        except Exception as e:
            tft.fill(0x0000)
            tft.write(font14, "Manifest error:", 2, 0, config.COL_ERROR, 0x0000)
            tft.write(font14, str(e)[:40], 2, config.LINE_H, 0xFFFF, 0x0000)
            time.sleep(3)
            return

        want_custom = _browse(tft, kb, font14, config, repo, manifest)
        if not want_custom:
            return

        new_repo = _type_repo(tft, kb, font14, config)
        if new_repo:
            repo = new_repo
        # if cancelled, loop back with the same repo
