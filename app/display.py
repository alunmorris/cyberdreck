# app/display.py
from machine import SPI, Pin
import st7789

SCREEN_W = 320
SCREEN_H = 240

# Colors (RGB565)
BLACK      = st7789.BLACK
WHITE      = st7789.WHITE
RED        = st7789.RED
CYAN       = st7789.CYAN
GREEN      = st7789.GREEN
ORANGE     = 0xFD20
YELLOW     = st7789.YELLOW
DARK_GREY  = 0x4208   # COL_KEY_FACE
MID_GREY   = 0x2945   # COL_BTN_BG
LIGHT_GREY = 0xC618   # COL_INVERT_BG (light theme background)
DARK_BG    = 0x0841   # COL_BG (dark theme background)
AI_YELLOW  = 0xF760   # COL_AI
USER_CYAN  = st7789.CYAN
USER_OLIVE = 0x8400   # COL_USER_LIGHT (light theme user text)

_tft = None

def init():
    global _tft
    spi = SPI(1, baudrate=4_000_000, polarity=0, phase=0,
              sck=Pin(36), mosi=Pin(35), miso=Pin(37))
    _tft = st7789.ST7789(spi, 240, 320,
        reset=Pin(18, Pin.OUT),
        cs=Pin(34, Pin.OUT),
        dc=Pin(17, Pin.OUT),
        rotation=1)
    _tft.init()
    _tft.fill(LIGHT_GREY)
    return _tft

def get():
    return _tft
