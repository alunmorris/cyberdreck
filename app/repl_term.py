# app/repl_term.py
"""Interactive Python REPL on TFT display + USB keyboard."""
import sys, time, config
import fonts.dejavu14_ru as font14

_BUF_LINES = 200
_MAX_CHARS  = 42


class _TFTTerminal:
    def __init__(self, tft, kb):
        self._tft   = tft
        self._kb    = kb
        self._lines = ['']

    def _draw_line(self, view_pos, text):
        y = view_pos * config.LINE_H
        self._tft.fill_rect(0, y, config.SCREEN_W, config.LINE_H, 0x0000)
        if text:
            self._tft.write(font14, text[:_MAX_CHARS], 2, y, 0xFFFF, 0x0000)

    def _full_redraw(self):
        self._tft.fill(0x0000)
        n     = len(self._lines)
        start = max(0, n - config.MAX_VIS)
        for i, line in enumerate(self._lines[start : start + config.MAX_VIS]):
            if line:
                self._tft.write(font14, line[:_MAX_CHARS], 2, i * config.LINE_H, 0xFFFF, 0x0000)

    def write(self, s):
        if isinstance(s, (bytes, bytearray, memoryview)):
            try:
                s = bytes(s).decode('utf-8', 'replace')
            except Exception:
                return 0

        old_n       = len(self._lines)
        old_start   = max(0, old_n - config.MAX_VIS)
        first_dirty = old_n - 1   # current line is always touched

        i = 0
        while i < len(s):
            ch = s[i]
            if ch == '\x1b':
                i += 1
                if i < len(s) and s[i] == '[':
                    i += 1
                    while i < len(s) and not (s[i].isalpha() or s[i] == '~'):
                        i += 1
                i += 1
                continue
            elif ch == '\n':
                self._lines.append('')
                if len(self._lines) > _BUF_LINES:
                    self._lines.pop(0)
            elif ch == '\r':
                if i + 1 < len(s) and s[i + 1] == '\n':
                    pass
                else:
                    self._lines[-1] = ''
            elif ch == '\x08':
                if self._lines[-1]:
                    self._lines[-1] = self._lines[-1][:-1]
            elif ord(ch) >= 0x20:
                self._lines[-1] += ch
            i += 1

        new_n     = len(self._lines)
        new_start = max(0, new_n - config.MAX_VIS)

        if new_start != old_start:
            self._full_redraw()
        else:
            # Redraw from first touched line to end of content
            fv = max(0, first_dirty - new_start)
            lv = min(config.MAX_VIS, new_n - new_start)
            for j in range(fv, lv):
                self._draw_line(j, self._lines[new_start + j])

        return len(s)

    def flush(self): pass


def run(tft, kb):
    """Block here running an interactive REPL. Reset device to exit."""
    tft.fill(0x0000)
    term = _TFTTerminal(tft, kb)

    def out(s):
        term.write(s)

    def show_prompt(cont=False):
        out('... ' if cont else '>>> ')

    out('MicroPython REPL\n')
    out('Reset device to exit\n')
    show_prompt()

    ns   = {}
    cur  = ''
    buf  = []
    cont = False

    while True:
        time.sleep_ms(10)
        ev = kb.poll()
        if ev is None:
            continue
        t, ch = ev

        if t == kb.INPUT_CHAR:
            out(ch)
            cur += ch

        elif t == kb.INPUT_BACKSPACE:
            if cur:
                cur = cur[:-1]
                out('\x08 \x08')

        elif t == kb.INPUT_ENTER:
            out('\n')
            buf.append(cur)
            cur = ''
            src = '\n'.join(buf)

            if src.rstrip().endswith(':'):
                cont = True
                show_prompt(cont=True)
                continue

            if cont and buf[-1].strip() == '':
                cont = False

            if not cont:
                src = src.strip()
                if src:
                    try:
                        try:
                            result = eval(compile(src, '<stdin>', 'eval'), ns)
                            if result is not None:
                                out(repr(result) + '\n')
                        except SyntaxError:
                            exec(compile(src, '<stdin>', 'exec'), ns)
                    except Exception as e:
                        out(type(e).__name__ + ': ' + str(e) + '\n')
                buf  = []
                cont = False
                show_prompt()
