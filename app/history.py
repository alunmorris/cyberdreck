# app/history.py
from config import MAX_LINES, MAX_VIS, COL_AI, COL_USER, COL_ERROR, SCREEN_W

# Each message: {'role': 'user'|'ai'|'error', 'text': str, 'display_only': bool}
_messages      = []
_total_bytes   = 0
HEAP_BUDGET    = 64000   # max total text bytes before evicting oldest pair

# Rendered line cache
lines         = []
scroll_offset = 0

def clear():
    global _messages, _total_bytes, lines, scroll_offset
    _messages = []; _total_bytes = 0; lines = []; scroll_offset = 0

def add(role, text, display_only=False):
    """Add a message. role = 'user', 'ai', or 'error'."""
    global _messages, _total_bytes
    text = (text
        .replace('‘', "'").replace('’', "'")
        .replace('“', '"').replace('”', '"')
        .replace('–', '-').replace('—', '-')
        .replace('…', '...').replace(' ', ' ')
    )
    safe = []
    for ch in text:
        o = ord(ch)
        if o == 0x7F:
            continue   # DEL — drop
        if o >= 0x20 or ch == '\n':
            safe.append(ch)
    text = ''.join(safe)
    if not text:
        return
    while len(_messages) >= 2 and _total_bytes + len(text) > HEAP_BUDGET:
        removed = _messages.pop(0)
        _total_bytes -= len(removed['text'])
        if _messages:
            removed2 = _messages.pop(0)
            _total_bytes -= len(removed2['text'])
    _messages.append({'role': role, 'text': text, 'display_only': display_only})
    _total_bytes += len(text)
    global scroll_offset
    scroll_offset = 0
    rebuild_lines()

def get_messages():
    """Return messages for API calls (exclude display_only)."""
    return [m for m in _messages if not m['display_only']]

def rebuild_lines(measure_fn=None):
    """Rebuild rendered line cache. measure_fn(text)->int returns pixel width."""
    global lines
    lines = []
    col_map = {'user': COL_USER, 'ai': COL_AI, 'error': COL_ERROR}
    for msg in _messages:
        col = col_map.get(msg['role'], COL_AI)
        is_user = (msg['role'] == 'user')
        wrap_at = SCREEN_W - 4

        words = msg['text'].replace('\n', ' \n ').split(' ')
        line_buf = ''
        for word in words:
            if word == '\n':
                if line_buf:
                    lines.append({'text': line_buf, 'color': col, 'is_user': is_user})
                    line_buf = ''
                continue
            if not word:
                continue
            test = (line_buf + ' ' + word).strip() if line_buf else word
            w = measure_fn(test) if measure_fn else len(test) * 6
            if w <= wrap_at:
                line_buf = test
            else:
                if line_buf:
                    lines.append({'text': line_buf, 'color': col, 'is_user': is_user})
                line_buf = word
            if len(lines) >= MAX_LINES - 1:
                break
        if line_buf and len(lines) < MAX_LINES:
            lines.append({'text': line_buf, 'color': col, 'is_user': is_user})
        if len(lines) >= MAX_LINES - 1:
            break

def scroll_up(n=1):
    global scroll_offset
    scroll_offset = min(scroll_offset + n, max(0, len(lines) - MAX_VIS))

def scroll_down(n=1):
    global scroll_offset
    scroll_offset = max(scroll_offset - n, 0)
