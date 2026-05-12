# sim800l-sms.py — receive and list SMS via SIM800L GSM module
# 120526 v1.0
# Wiring: ESP32-S2 GPIO8=TX -> SIM800L RXD, GPIO9=RX <- SIM800L TXD
# SIM800L needs 3.7-4.2V supply (not 3.3V) capable of 2A peaks.
from machine import UART, Pin
import time

BAUD   = 9600
TX_PIN = 8   # ESP32-S2 TX  -> SIM800L RXD
RX_PIN = 9   # ESP32-S2 RX  <- SIM800L TXD

uart = UART(1, baudrate=BAUD, tx=Pin(TX_PIN), rx=Pin(RX_PIN),
            timeout=100, rxbuf=1024)


def _at(cmd, wait_ms=500, expect=None):
    """Send AT command, return response lines (strips OK/ERROR)."""
    uart.write((cmd + '\r\n').encode())
    time.sleep_ms(wait_ms)
    raw = b''
    while uart.any():
        raw += uart.read(uart.any())
        time.sleep_ms(20)
    lines = [l.strip() for l in raw.decode('utf-8', 'replace').splitlines() if l.strip()]
    if expect and not any(expect in l for l in lines):
        raise RuntimeError(f"Expected {expect!r}, got: {lines}")
    return lines


def _init():
    # Auto-baud sync
    for _ in range(5):
        resp = _at('AT', 300)
        if any('OK' in l for l in resp):
            break
        time.sleep_ms(500)
    else:
        raise RuntimeError('SIM800L not responding — check power and wiring')

    _at('ATE0', 300)           # echo off
    _at('AT+CMGF=1', 300, 'OK')  # SMS text mode
    _at('AT+CSCS="GSM"', 300)  # GSM character set


def _parse_sms(lines):
    """Parse CMGL response into list of (index, from, date, text) tuples."""
    messages = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('+CMGL:'):
            # +CMGL: <idx>,"<stat>","<from>",,"<date>"
            try:
                parts = line[7:].split(',')
                idx  = parts[0].strip()
                stat = parts[1].strip().strip('"')
                frm  = parts[2].strip().strip('"')
                dt   = parts[4].strip().strip('"') if len(parts) > 4 else ''
                body = lines[i + 1] if i + 1 < len(lines) else ''
                messages.append((idx, frm, dt, stat, body))
                i += 2
            except (IndexError, ValueError):
                i += 1
        else:
            i += 1
    return messages


# ── Main ──────────────────────────────────────────────────────────────────────

print('SIM800L SMS reader')
print(f'UART1  TX=GPIO{TX_PIN}  RX=GPIO{RX_PIN}  {BAUD} baud')

try:
    _init()
    print('Module OK')
except RuntimeError as e:
    print(f'Init failed: {e}')
    raise SystemExit

# Signal quality
sq = _at('AT+CSQ', 300)
for l in sq:
    if '+CSQ:' in l:
        val = l.split(':')[1].split(',')[0].strip()
        try:
            rssi = int(val)
            dbm = -113 + rssi * 2 if rssi < 99 else 'unknown'
            print(f'Signal: {rssi}/31  ({dbm} dBm)')
        except ValueError:
            print(f'Signal: {l}')

# Network registration
reg = _at('AT+CREG?', 300)
for l in reg:
    if '+CREG:' in l:
        status = l.split(',')[-1].strip() if ',' in l else l.split(':')[-1].strip()
        labels = {'0':'not registered', '1':'home network', '2':'searching',
                  '3':'denied', '5':'roaming'}
        print(f'Network: {labels.get(status, status)}')

# List all SMS
print()
raw = _at('AT+CMGL="ALL"', 1000)
messages = _parse_sms(raw)

if not messages:
    print('No SMS stored on SIM')
else:
    print(f'{len(messages)} message(s):')
    print()
    for idx, frm, dt, stat, body in messages:
        flag = '*' if stat.upper() in ('REC UNREAD', 'UNREAD') else ' '
        print(f'[{idx}]{flag} From: {frm}')
        if dt:
            print(f'     Date: {dt}')
        print(f'     {body}')
        print()

print('Done. Use AT+CMGD=<n> to delete a message.')
