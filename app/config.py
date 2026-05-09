# app/config.py
VERSION = "9 May 2026"

# Hardware
LED_PIN    = 15          # active-high GPIO LED
SCREEN_W   = 320
SCREEN_H   = 240
LINE_H     = 16          # pixel height per text row (13px font + 3px leading)

# Layout
HIST_H     = SCREEN_H - LINE_H   # chat history area height (222px)
INPUT_Y    = SCREEN_H - LINE_H   # y-coord of input bar (222)
MAX_VIS    = HIST_H // LINE_H    # visible history rows (12)
MAX_LINES  = 150                 # rendered line cache

# Timing
API_TIMEOUT_MS     = 25_000
WIFI_RETRY_DELAY   = 0.5         # seconds
WIFI_MAX_ATTEMPTS  = 30
WIFI_IDLE_TIMEOUT  = 60          # seconds idle -> disconnect WiFi

# Colors (RGB565)
COL_BG          = 0x0841   # dark theme background
COL_INVERT_BG   = 0xC618   # light theme background (grey)
COL_AI          = 0xF760   # yellow
COL_USER        = 0x07FF   # cyan
COL_USER_LIGHT  = 0x8400   # olive (user text in light theme)
COL_ERROR       = 0xF800   # red
COL_PROMPT      = 0x4208   # dark grey prompt ">"

# API endpoints
GEMINI_HOST = "generativelanguage.googleapis.com"
GROK_HOST   = "api.x.ai"
GROQ_HOST   = "api.groq.com"
HTTPS_PORT  = 443

# Models
GEMINI_MODELS = [
    "gemini-3.1-flash-lite-preview",
    "gemini-3-flash-preview",
    "gemini-3.1-pro-preview",
]
GROK_MODEL  = "grok-3-fast"
GROQ_MODEL  = "openai/gpt-oss-120b"

# System prompt (120-word limit)
SYSTEM_PROMPT = (
    "You are displayed on a 240x320 pixel screen. Respond in 80 words or fewer. "
    "Plain text only: no markdown, no ** or * emphasis, no tables, no bullet symbols, "
    "no numbered or unnumbered lists. Use paragraphs to separate distinct ideas. "
    "Never include URLs, hyperlinks, citations, footnotes, source references, or attribution of any kind."
)
