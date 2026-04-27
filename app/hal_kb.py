# app/hal_kb.py
import usbhid
from machine import Pin
import time

INPUT_NONE         = usbhid.INPUT_NONE
INPUT_CHAR         = usbhid.INPUT_CHAR
INPUT_BACKSPACE    = usbhid.INPUT_BACKSPACE
INPUT_ENTER        = usbhid.INPUT_ENTER
INPUT_SCROLL_UP    = usbhid.INPUT_SCROLL_UP
INPUT_SCROLL_DOWN  = usbhid.INPUT_SCROLL_DOWN
INPUT_NEW_CONV     = usbhid.INPUT_NEW_CONV
INPUT_MORE         = usbhid.INPUT_MORE
INPUT_CURSOR_LEFT  = usbhid.INPUT_CURSOR_LEFT
INPUT_CURSOR_RIGHT = usbhid.INPUT_CURSOR_RIGHT
INPUT_MODEL_MENU   = usbhid.INPUT_MODEL_MENU
INPUT_DELETE       = usbhid.INPUT_DELETE

_led = None

def init(timeout_ms=5000):
    """Start USB host. Wait up to timeout_ms for keyboard. Returns True if found."""
    global _led
    _led = Pin(15, Pin.OUT)
    _led.on()
    usbhid.init()
    deadline = time.ticks_add(time.ticks_ms(), timeout_ms)
    while not usbhid.connected():
        if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
            break
        time.sleep_ms(100)
    _led.off()
    return usbhid.connected()

def poll():
    """Non-blocking. Returns (type, ch_str) or None."""
    raw = usbhid.poll()
    if raw is None:
        return None
    ev_type, ch_ord = raw
    ch = chr(ch_ord) if (ev_type == INPUT_CHAR and ch_ord) else ''
    return (ev_type, ch)

def connected():
    return usbhid.connected()

def set_led(on: bool):
    if _led:
        _led.value(1 if on else 0)
