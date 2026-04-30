# app/repl_term.py
"""Interactive Python REPL on TFT display + USB keyboard."""
import sys, time, config
import fonts.dejavu14_ru as font14

_BUF_LINES = 200
_MAX_CHARS  = 42

_HIDDEN = frozenset({
    'main.py', 'config.py', 'secrets.py', 'hal_kb.py', 'display.py',
    'writer.py', 'history.py', 'ui.py', 'wifi_mgr.py', 'api.py',
    'repl_term.py', 'boot.py', 'fonts',
})


class _TFTTerminal:
    def __init__(self, tft, kb):
        self._tft    = tft
        self._kb     = kb
        self._lines  = [['', config.COL_AI]]
        self._scroll = 0   # lines scrolled back from bottom

    def _view_start(self):
        bottom = max(0, len(self._lines) - config.MAX_VIS)
        return max(0, bottom - self._scroll)

    def _draw_line(self, view_pos, text, color):
        y = view_pos * config.LINE_H
        self._tft.fill_rect(0, y, config.SCREEN_W, config.LINE_H, 0x0000)
        if text:
            self._tft.write(font14, text[:_MAX_CHARS], 2, y, color, 0x0000)

    def _full_redraw(self):
        self._tft.fill(0x0000)
        start = self._view_start()
        for i, (line, col) in enumerate(self._lines[start : start + config.MAX_VIS]):
            if line:
                self._tft.write(font14, line[:_MAX_CHARS], 2, i * config.LINE_H, col, 0x0000)

    def scroll_up(self, n=1):
        max_scroll = max(0, len(self._lines) - config.MAX_VIS)
        self._scroll = min(max_scroll, self._scroll + n)
        self._full_redraw()

    def scroll_down(self, n=1):
        self._scroll = max(0, self._scroll - n)
        self._full_redraw()

    def write(self, s, color=config.COL_AI):
        if isinstance(s, (bytes, bytearray, memoryview)):
            try:
                s = bytes(s).decode('utf-8', 'replace')
            except Exception:
                return 0

        self._lines[-1][1] = color
        old_n       = len(self._lines)
        old_bottom  = max(0, old_n - config.MAX_VIS)
        first_dirty = old_n - 1

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
                self._lines.append(['', color])
                if len(self._lines) > _BUF_LINES:
                    self._lines.pop(0)
            elif ch == '\r':
                if i + 1 < len(s) and s[i + 1] == '\n':
                    pass
                else:
                    self._lines[-1][0] = ''
            elif ch == '\x08':
                if self._lines[-1][0]:
                    self._lines[-1][0] = self._lines[-1][0][:-1]
            elif ord(ch) >= 0x20:
                self._lines[-1][0] += ch
                if len(self._lines[-1][0]) >= _MAX_CHARS:
                    self._lines.append(['', color])
                    if len(self._lines) > _BUF_LINES:
                        self._lines.pop(0)
            i += 1

        if self._scroll > 0:
            return len(s)   # user scrolled back — don't move view

        new_n      = len(self._lines)
        new_bottom = max(0, new_n - config.MAX_VIS)

        if new_bottom != old_bottom:
            self._full_redraw()
        else:
            fv = max(0, first_dirty - new_bottom)
            lv = min(config.MAX_VIS, new_n - new_bottom)
            for j in range(fv, lv):
                line, col = self._lines[new_bottom + j]
                self._draw_line(j, line, col)

        return len(s)

    def flush(self): pass


def run(tft, kb):
    """Block here running an interactive REPL. Reset device to exit."""
    tft.fill(0x0000)
    term = _TFTTerminal(tft, kb)

    def out(s, color=config.COL_AI):
        term.write(s, color)

    out('MicroPython REPL. ctrl-D to exit\n')
    out("run('xxx.py') to run a python file\n", 0x07E0)
    out('ls() to see user files\n', 0x07E0)

    import uos, gc, machine, network

    def _print(*args, **kwargs):
        sep = kwargs.get('sep', ' ')
        end = kwargs.get('end', '\n')
        out(sep.join(str(a) for a in args) + end)

    def _run(path):
        if not path.startswith('/'):
            path = '/' + path
        exec(open(path).read(), ns)

    def _ls(path='/'):
        for name in sorted(uos.listdir(path)):
            if name not in _HIDDEN:
                out(name + '\n')

    class _SafeOS:
        def __getattr__(self, name):
            return getattr(uos, name)
        def listdir(self, path='/'):
            return [f for f in uos.listdir(path) if f not in _HIDDEN]

    _safe_os = _SafeOS()

    ns = dict(globals())
    ns.update({
        'uos': _safe_os, 'os': _safe_os,
        'gc': gc,
        'machine': machine,
        'network': network,
        'print': _print,
        'run': _run,
        'ls': _ls,
    })

    cur     = ''
    cur_pos = 0
    buf     = []
    cont    = False

    def _draw_input():
        p    = '... ' if cont else '>>> '
        text = p + cur
        term._lines[-1] = [text, config.COL_USER]
        n  = len(term._lines)
        vs = term._view_start()
        vp = (n - 1) - vs
        if 0 <= vp < config.MAX_VIS:
            y = vp * config.LINE_H
            tft.fill_rect(0, y, config.SCREEN_W, config.LINE_H, 0x0000)
            if text:
                tft.write(font14, text[:_MAX_CHARS], 2, y, config.COL_USER, 0x0000)
            cx = 2 + tft.write_len(font14, (p + cur[:cur_pos])[:_MAX_CHARS])
            tft.fill_rect(cx, y + 2, 1, config.LINE_H - 4, config.COL_USER)

    _draw_input()

    while True:
        time.sleep_ms(10)
        ev = kb.poll()
        if ev is None:
            continue
        t, ch = ev

        try:
            if t == kb.INPUT_CHAR:
                if ch == '\x04':   # Ctrl-D — exit REPL
                    return
                cur = cur[:cur_pos] + ch + cur[cur_pos:]
                cur_pos += 1
                _draw_input()

            elif t == kb.INPUT_BACKSPACE:
                if cur_pos > 0:
                    cur = cur[:cur_pos - 1] + cur[cur_pos:]
                    cur_pos -= 1
                    _draw_input()

            elif t == kb.INPUT_DELETE:
                if cur_pos < len(cur):
                    cur = cur[:cur_pos] + cur[cur_pos + 1:]
                    _draw_input()

            elif t == kb.INPUT_CURSOR_LEFT:
                if cur_pos > 0:
                    cur_pos -= 1
                    _draw_input()

            elif t == kb.INPUT_CURSOR_RIGHT:
                if cur_pos < len(cur):
                    cur_pos += 1
                    _draw_input()

            elif t == kb.INPUT_MODEL_MENU:
                return

            elif t == kb.INPUT_SCROLL_UP:
                term.scroll_down(1)
                _draw_input()

            elif t == kb.INPUT_SCROLL_DOWN:
                term.scroll_up(1)

            elif t == kb.INPUT_ENTER:
                term._scroll = 0
                out('\n')
                buf.append(cur)
                cur     = ''
                cur_pos = 0
                last    = buf[-1]

                if last.rstrip().endswith(':'):
                    cont = True
                    _draw_input()
                    continue

                if cont:
                    if last.strip() == '':
                        cont = False   # blank line ends block, fall through to exec
                    else:
                        _draw_input()
                        continue       # still collecting block lines

                src  = '\n'.join(buf).strip()
                buf  = []
                cont = False
                if src:
                    try:
                        result = eval(src, ns)
                        if result is not None:
                            out(repr(result) + '\n')
                    except SyntaxError:
                        try:
                            exec(src, ns)
                        except Exception as e:
                            out(type(e).__name__ + ': ' + str(e) + '\n', config.COL_ERROR)
                    except Exception as e:
                        out(type(e).__name__ + ': ' + str(e) + '\n', config.COL_ERROR)
                _draw_input()

        except Exception as e:
            out('\nerr: ' + str(e) + '\n', config.COL_ERROR)
            cur = ''; cur_pos = 0; buf = []; cont = False
            _draw_input()
