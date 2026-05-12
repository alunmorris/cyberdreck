# sysinfo.py — display memory and WiFi info
import gc, network

gc.collect()
free  = gc.mem_free()
alloc = gc.mem_alloc()
total = free + alloc

wlan = network.WLAN(network.STA_IF)
if wlan.isconnected():
    ip   = wlan.ifconfig()[0]
    ssid = wlan.config('ssid')
    rssi = wlan.status('rssi')
    wifi = f"{ssid}  {rssi}dBm"
    ipstr = ip
else:
    wifi  = "not connected"
    ipstr = "-"

print(f"Memory free : {free:,} B")
print(f"Memory used : {alloc:,} B")
print(f"Memory total: {total:,} B")
print()
print(f"WiFi : {wifi}")
print(f"IP   : {ipstr}")
