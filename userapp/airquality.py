# airquality.py — 33-hour AQI forecast for Lecco, Italy (Open-Meteo)
#010526 Change to a chart of next 11 hours. Make long. and lat. constants
#      Add auto scaliong and AQI guide

# airquality.py — 33-hour AQI forecast for Lecco, Italy (Open-Meteo)
#010526 Change to a chart of next 11 hours. Make long. and lat. constants
#       Wait fot 'c' before showing chart, so user can rerad AQI help

import socket, ssl, json, gc, time, sys
import wifi_mgr

# Location & Data settings
LATITUDE = 45.85            # Lecco
LONGITUDE = 9.4             # Lecco
FORECAST_HOURS = 33         # Hourly data

HOST = "air-quality-api.open-meteo.com"
PATH = (f"/v1/air-quality?latitude={LATITUDE}&longitude={LONGITUDE}"
        "&current=european_aqi"
        "&hourly=european_aqi"
        "&forecast_days=3")

def _https_get(host, path):
    addr = socket.getaddrinfo(host, 443)[0][-1]
    s = socket.socket()
    s.settimeout(15)
    s.connect(addr)
    s = ssl.wrap_socket(s, server_hostname=host)
    s.write((
        f"GET {path} HTTP/1.0\r\n"
        f"Host: {host}\r\n"
        "\r\n"
    ).encode())
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
    if b" 200 " not in raw[:raw.find(b"\r\n")]:
        raise ValueError(raw[:60].decode())
    return raw[sep + 4:]

tft.fill(0x0000)
term = _TFTTerminal(tft, None, font=mono13)

def mprint(*args, **kwargs):
    sep = kwargs.get('sep', ' ')
    end = kwargs.get('end', '\n')
    term.write(sep.join(str(a) for a in args) + end)

# Updated shorter help text to prevent line wrapping
mprint("Air Quality Index (AQI) Chart - Lecco, Italy")
mprint("0-50:    Good")
mprint("51-100:  Moderate -OK for vast maj.")
mprint("101-150: Unhealthy for the sensitive")
mprint("151-200: Unhealthy")
mprint("201-300: Very Unhealthy")
mprint("301+:    Hazardous\n")

# Use \r to keep the cursor on the same line so we can overwrite it later
mprint("Connecting...", end='\r')

if not wifi_mgr.is_connected():
    wifi_mgr.load_creds()
    if wifi_mgr._creds:
        c = wifi_mgr._creds[0]
        wifi_mgr.connect(c['ssid'], c['pass'])

if not wifi_mgr.is_connected():
    mprint("\nNo WiFi connection")
else:
    try:
        gc.collect()
        body = _https_get(HOST, PATH)
        data = json.loads(body)
        gc.collect()

        cur_time = data['current']['time']
        h_times = data['hourly']['time']
        h_aqis  = data['hourly']['european_aqi']

        try:
            start_idx = h_times.index(cur_time) + 1
        except ValueError:
            start_idx = 0

        # Collect the 22-hour data
        aqi_list = []
        time_list = []
        for i in range(start_idx, start_idx + FORECAST_HOURS):
            if i < len(h_times):
                time_list.append(h_times[i][-5:]) # "HH:MM"
                aqi_list.append(h_aqis[i])

        # Overwrite the 'Connecting...' line with the new prompt
        mprint("Data ready. Hit 'c' for chart")
        
        while True:
            ev = kb.poll()
            if ev is None:
                time.sleep_ms(20)
                continue
            
            ev_type, ch = ev
            if ev_type == kb.INPUT_CHAR and str(ch).lower() == 'c':
                break
            elif ev_type == kb.INPUT_MODEL_MENU:
                mprint("\nCanceled.")
                sys.exit()

        tft.fill(0x0000)
        term = _TFTTerminal(tft, None, font=mono13)
        mprint(f"Lecco AQI (Next {FORECAST_HOURS}h)")

        # Determine dynamic scale
        valid_aqis = [a for a in aqi_list if a is not None]
        max_aqi = max(valid_aqis) if valid_aqis else 0

        if max_aqi > 200:
            scale_max = 300
            scale_step = 30
        elif max_aqi > 100:
            scale_max = 200
            scale_step = 20
        else:
            scale_max = 100
            scale_step = 10

        # Draw the Y-axis and chart data dynamically (stops before 0 to save a row)
        for lvl in range(scale_max, 0, -scale_step):
            row = f"{lvl:3}|"
            for aqi in aqi_list:
                if aqi is None:
                    row += " "
                else:
                    display_aqi = min(aqi, scale_max)
                    nearest = round(display_aqi / scale_step) * scale_step
                    if nearest == lvl:
                        row += "_"
                    else:
                        row += " "
            mprint(row.rstrip())

        # Merge the 0-level data line and the X-axis separator to save 1 vertical row
        row0 = "  0+"
        for aqi in aqi_list:
            if aqi is None:
                row0 += "-"
            else:
                display_aqi = min(aqi, scale_max)
                nearest = round(display_aqi / scale_step) * scale_step
                if nearest == 0:
                    row0 += "_" # Plot point at 0
                else:
                    row0 += "-" # Axis line
        mprint(row0)
        
        # Draw the X-axis labels on a single line (show every 3rd hour to fit perfectly)
        labels = "    "
        for i in range(0, len(time_list), 3):
            labels += f"{time_list[i][:2]:<3}"
        mprint(labels.rstrip())

    except Exception as e:
        mprint(f"\nError: {e}")