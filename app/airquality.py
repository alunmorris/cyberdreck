# airquality.py — current air quality for Lecco, Italy (Open-Meteo)
import socket, ssl, json, gc
import wifi_mgr

HOST = "air-quality-api.open-meteo.com"
PATH = ("/v1/air-quality?latitude=45.85&longitude=9.4"
        "&current=european_aqi,pm10,pm2_5,carbon_monoxide"
        ",nitrogen_dioxide,ozone")

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

def _aqi_label(v):
    if v is None: return "?"
    if v <= 20:   return "Good"
    if v <= 40:   return "Fair"
    if v <= 60:   return "Moderate"
    if v <= 80:   return "Poor"
    if v <= 100:  return "V.Poor"
    return "Hazardous"

tft.fill(0x0000)
term = _TFTTerminal(tft, None, font=mono13)

def mprint(*args, **kwargs):
    sep = kwargs.get('sep', ' ')
    end = kwargs.get('end', '\n')
    term.write(sep.join(str(a) for a in args) + end)

mprint("Air Quality - Lecco, Italy")
mprint("Connecting...")

if not wifi_mgr.is_connected():
    wifi_mgr.load_creds()
    if wifi_mgr._creds:
        c = wifi_mgr._creds[0]
        wifi_mgr.connect(c['ssid'], c['pass'])

if not wifi_mgr.is_connected():
    mprint("No WiFi connection")
else:
    try:
        gc.collect()
        body = _https_get(HOST, PATH)
        data = json.loads(body)
        gc.collect()

        cur  = data['current']
        t    = cur.get('time', '')[:16]
        aqi  = cur.get('european_aqi')
        pm10 = cur.get('pm10')
        pm25 = cur.get('pm2_5')
        co   = cur.get('carbon_monoxide')
        no2  = cur.get('nitrogen_dioxide')
        o3   = cur.get('ozone')

        tft.fill(0x0000)
        term = _TFTTerminal(tft, None, font=mono13)

        mprint("Air Quality - Lecco, Italy")
        mprint(f"Updated: {t}")
        mprint("----------------------------------------")
        mprint(f"European AQI : {str(aqi):<4} ({_aqi_label(aqi)})")
        mprint(f"PM10         : {str(pm10):<7} ug/m3")
        mprint(f"PM2.5        : {str(pm25):<7} ug/m3")
        mprint(f"CO           : {str(co):<7} ug/m3")
        mprint(f"NO2          : {str(no2):<7} ug/m3")
        mprint(f"O3           : {str(o3):<7} ug/m3")

    except Exception as e:
        mprint(f"Error: {e}")
