# app/repl_term.py
"""Interactive Python REPL on TFT display + USB keyboard."""
import sys, time, config
import fonts.dejavu14_ru as font14
import fonts.mono13 as mono13

_BUF_LINES = 200

_HIDDEN = frozenset({
    'main.py', 'config.py', 'secrets.py', 'hal_kb.py', 'display.py',
    'writer.py', 'history.py', 'ui.py', 'wifi_mgr.py', 'api.py',
    'repl_term.py', 'boot.py', 'fonts', 'getprog.py',
})


class _TFTTerminal:
    def __init__(self, tft, kb, font=None):
        self._tft      = tft
        self._kb       = kb
        self._font     = font or font14
        cw = tft.write_len(self._font, 'W')
        self._max_chars = (config.SCREEN_W - 4) // cw if cw else 42
        self._lines    = [['', config.COL_AI]]
        self._scroll   = 0
        self._col      = 0   # write column in current line
        self._cur_line = 0   # index into _lines of active write position

    def _view_start(self):
        bottom = max(0, len(self._lines) - config.MAX_VIS)
        return max(0, bottom - self._scroll)

    def _draw_line(self, view_pos, text, color):
        y = view_pos * config.LINE_H
        self._tft.fill_rect(0, y, config.SCREEN_W, config.LINE_H, 0x0000)
        if text:
            self._tft.write(self._font, text[:self._max_chars], 2, y, color, 0x0000)

    def _full_redraw(self):
        self._tft.fill(0x0000)
        start = self._view_start()
        for i, (line, col) in enumerate(self._lines[start : start + config.MAX_VIS]):
            if line:
                self._tft.write(self._font, line[:self._max_chars], 2, i * config.LINE_H, col, 0x0000)

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

        self._lines[self._cur_line][1] = color
        old_n       = len(self._lines)
        old_bottom  = max(0, old_n - config.MAX_VIS)
        first_dirty = self._cur_line

        i = 0
        while i < len(s):
            ch = s[i]
            if ch == '\x1b':
                i += 1
                if i < len(s) and s[i] == '[':
                    i += 1
                    # parse semicolon-separated params
                    params = []
                    num = 0
                    while i < len(s) and (s[i].isdigit() or s[i] == ';'):
                        if s[i] == ';':
                            params.append(num); num = 0
                        else:
                            num = num * 10 + int(s[i])
                        i += 1
                    params.append(num)
                    if i < len(s):
                        cmd = s[i]
                        p0  = params[0]
                        n   = max(1, p0)
                        if cmd == 'A':   # cursor up
                            self._cur_line = max(0, self._cur_line - n)
                            first_dirty = min(first_dirty, self._cur_line)
                        elif cmd == 'B': # cursor down
                            self._cur_line = min(len(self._lines) - 1, self._cur_line + n)
                        elif cmd == 'K': # erase line (any variant — erase whole line)
                            self._lines[self._cur_line][0] = ''
                            self._col = 0
                            first_dirty = min(first_dirty, self._cur_line)
                        elif cmd == 'H': # move cursor: \x1b[H home, \x1b[r;cH 1-indexed
                            r      = max(1, p0) - 1
                            c      = max(1, params[1] if len(params) > 1 else 1) - 1
                            bottom = max(0, len(self._lines) - config.MAX_VIS)
                            self._cur_line = max(0, min(len(self._lines) - 1, bottom + r))
                            self._col      = max(0, min(self._max_chars - 1, c))
                            first_dirty = min(first_dirty, self._cur_line)
                        i += 1
                continue
            if ch == '\n':
                if self._cur_line == len(self._lines) - 1:
                    self._lines.append(['', color])
                    if len(self._lines) > _BUF_LINES:
                        self._lines.pop(0)
                        self._cur_line = max(0, self._cur_line - 1)
                    self._cur_line = len(self._lines) - 1
                else:
                    self._cur_line += 1
                self._col = 0
            elif ch == '\r':
                if not (i + 1 < len(s) and s[i + 1] == '\n'):
                    self._col = 0
            elif ch == '\x08':
                if self._col > 0:
                    self._col -= 1
            elif ord(ch) >= 0x20:
                text = self._lines[self._cur_line][0]
                if self._col < len(text):
                    self._lines[self._cur_line][0] = text[:self._col] + ch + text[self._col + 1:]
                else:
                    self._lines[self._cur_line][0] = text + ch
                self._col += 1
                if self._col >= self._max_chars:
                    if self._cur_line == len(self._lines) - 1:
                        self._lines.append(['', color])
                        if len(self._lines) > _BUF_LINES:
                            self._lines.pop(0)
                            self._cur_line = max(0, self._cur_line - 1)
                    self._cur_line = min(len(self._lines) - 1, self._cur_line + 1)
                    self._col = 0
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
        term._cur_line = len(term._lines) - 1
        term._lines[-1] = [text, config.COL_USER]
        term._col = len(text)
        n  = len(term._lines)
        vs = term._view_start()
        vp = (n - 1) - vs
        if 0 <= vp < config.MAX_VIS:
            y = vp * config.LINE_H
            tft.fill_rect(0, y, config.SCREEN_W, config.LINE_H, 0x0000)
            if text:
                tft.write(font14, text[:term._max_chars], 2, y, config.COL_USER, 0x0000)
            cx = 2 + tft.write_len(font14, (p + cur[:cur_pos])[:term._max_chars])
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


def _run_file(tft, kb, path):
    import gc, machine, network, _thread
    import time as _time
    tft.fill(0x0000)
    term = _TFTTerminal(tft, kb)
    def _print(*args, **kwargs):
        sep = kwargs.get('sep', ' ')
        end = kwargs.get('end', '\n')
        term.write(sep.join(str(a) for a in args) + end)
    # The main thread is the sole caller of kb.poll() to avoid race conditions.
    # Scroll events are handled immediately; everything else goes into this queue
    # for the user program to read via the _KbProxy below.
    _ev_queue = []

    class _KbProxy:
        def poll(self_):
            return _ev_queue.pop(0) if _ev_queue else None
        def __getattr__(self_, name):
            return getattr(kb, name)

    ns = dict(globals())
    ns.update({'__name__': '__main__', 'gc': gc, 'machine': machine,
               'network': network, 'print': _print, 'tft': tft, 'kb': _KbProxy(),
               'font14': font14, 'mono13': mono13, '_TFTTerminal': _TFTTerminal})
    result = [None]
    def _run():
        try:
            exec(open(path).read(), ns)
        except Exception as e:
            result[0] = e
        if result[0] is None:
            result[0] = True
    _thread.start_new_thread(_run, ())
    while result[0] is None:
        _time.sleep_ms(20)
        ev = kb.poll()
        if ev is not None:
            t = ev[0]
            if t == kb.INPUT_SCROLL_UP:    term.scroll_down(1)
            elif t == kb.INPUT_SCROLL_DOWN: term.scroll_up(1)
            else:                           _ev_queue.append(ev)
    hint_y = (config.MAX_VIS - 1) * config.LINE_H
    if isinstance(result[0], Exception):
        e = result[0]
        tft.fill(0x0000)
        tft.write(font14, type(e).__name__ + ':', 2, 0, 0xF800, 0x0000)
        msg = str(e)
        for row in range(min(4, config.MAX_VIS - 2)):
            chunk = msg[row * 38 : (row + 1) * 38]
            if not chunk: break
            tft.write(font14, chunk, 2, (row + 1) * config.LINE_H, 0xFFFF, 0x0000)
    tft.fill_rect(0, hint_y, config.SCREEN_W, config.LINE_H, 0x0000)
    tft.write(font14, 'Enter to exit', 2, hint_y, 0x07E0, 0x0000)
    while True:
        _time.sleep_ms(20)
        ev = kb.poll()
        if ev is None: continue
        t = ev[0]
        if t == kb.INPUT_SCROLL_UP:
            term.scroll_down(1)
            tft.fill_rect(0, hint_y, config.SCREEN_W, config.LINE_H, 0x0000)
            tft.write(font14, 'Enter to exit', 2, hint_y, 0x07E0, 0x0000)
        elif t == kb.INPUT_SCROLL_DOWN:
            term.scroll_up(1)
            tft.fill_rect(0, hint_y, config.SCREEN_W, config.LINE_H, 0x0000)
            tft.write(font14, 'Enter to exit', 2, hint_y, 0x07E0, 0x0000)
        elif t in (kb.INPUT_ENTER, kb.INPUT_MODEL_MENU):
            break


def show_file_manager(tft, kb):
    import uos, time as _time

    _FILE_ROWS = config.MAX_VIS - 3
    _COL_W = config.SCREEN_W // 2   # 160px per column

    def _get_entries(path):
        entries = []
        try:
            for item in uos.ilistdir(path):
                name, ftype = item[0], item[1]
                is_dir = bool(ftype & 0x4000)
                if path == '/' and name in _HIDDEN:
                    continue
                entries.append((name, is_dir))
        except Exception:
            pass
        entries.sort(key=lambda e: (0 if e[1] else 1, e[0].lower()))
        if path != '/':
            entries.insert(0, ('..', True))
        return entries

    def _join(path, name):
        return ('/' + name) if path == '/' else (path + '/' + name)

    def _cell_label(name, is_dir):
        if is_dir:
            return (name[:17] + '/') if len(name) > 17 else (name + '/')
        return name[:18]

    def _draw(entries, sel, offset, path, hint=''):
        tft.fill(0x0000)
        hdr = path if len(path) <= 30 else '...' + path[-27:]
        tft.write(font14, 'Files: ' + hdr, 2, 0, 0x03E0, 0x0000)
        offset_row = offset // 2
        for row in range(_FILE_ROWS):
            row_y = (row + 1) * config.LINE_H
            for col in range(2):
                fi = (offset_row + row) * 2 + col
                cx = 2 + col * _COL_W
                if fi < len(entries):
                    name, is_dir = entries[fi]
                    label = _cell_label(name, is_dir)
                    if fi == sel:
                        tft.fill_rect(cx - 2, row_y, _COL_W, config.LINE_H, 0xFFFF)
                        tft.write(font14, label, cx, row_y, 0x0000, 0xFFFF)
                    else:
                        fg = 0x07E0 if is_dir else (0x07FF if name.endswith('.py') else 0xFFFF)
                        tft.write(font14, label, cx, row_y, fg, 0x0000)
        hint1_y = (config.MAX_VIS - 2) * config.LINE_H
        menu_y  = (config.MAX_VIS - 1) * config.LINE_H
        tft.fill_rect(0, hint1_y, config.SCREEN_W, config.LINE_H * 2, 0x0000)
        if hint:
            tft.write(font14, hint[:38], 2, hint1_y, config.COL_AI, 0x0000)
        elif sel == len(entries):
            tft.fill_rect(0, menu_y, config.SCREEN_W, config.LINE_H, 0xFFFF)
            tft.write(font14, 'Menu', 2, menu_y, 0x0000, 0xFFFF)
        else:
            tft.write(font14, 'e=execute f=new folder r=rename', 2, hint1_y, 0xC618, 0x0000)
            tft.write(font14, 'DEL=delete  m=menu', 2, menu_y, 0xC618, 0x0000)

    def _text_prompt(title, initial=''):
        import ui
        tft.fill(0x0000)
        tft.write(font14, title, 2, 0, config.COL_AI, 0x0000)
        if initial:
            tft.write(font14, initial[:36], 2, config.LINE_H, 0xFFFF, 0x0000)
        buf = list(initial); cursor = len(buf)
        ui.draw_input_bar(''.join(buf), cursor, show_wifi=False)
        while True:
            _time.sleep_ms(20)
            ev = kb.poll()
            if ev is None: continue
            t, ch = ev
            if t == kb.INPUT_ENTER:
                return ''.join(buf).strip() or None
            elif t == kb.INPUT_MODEL_MENU:
                return None
            elif t == kb.INPUT_CHAR and len(buf) < 40:
                buf.insert(cursor, ch); cursor += 1
            elif t == kb.INPUT_BACKSPACE and cursor > 0:
                buf.pop(cursor - 1); cursor -= 1
            elif t == kb.INPUT_DELETE and cursor < len(buf):
                buf.pop(cursor)
            elif t == kb.INPUT_CURSOR_LEFT and cursor > 0:
                cursor -= 1
            elif t == kb.INPUT_CURSOR_RIGHT and cursor < len(buf):
                cursor += 1
            else:
                continue
            ui.draw_input_bar(''.join(buf), cursor, show_wifi=False)

    path = '/'; sel = 0; offset = 0

    while True:
        entries = _get_entries(path)
        n = len(entries) + 1   # +1 for Menu
        sel = min(sel, n - 1)
        max_offset_row = max(0, (len(entries) + 1) // 2 - _FILE_ROWS)
        offset = max(0, min(offset, max_offset_row * 2))
        _draw(entries, sel, offset, path)

        while True:
            _time.sleep_ms(20)
            ev = kb.poll()
            if ev is None: continue
            t, ch = ev

            sel_row = sel // 2
            sel_col = sel % 2
            offset_row = offset // 2

            if t == kb.INPUT_SCROLL_DOWN:
                if sel_row > 0:
                    sel = (sel_row - 1) * 2 + sel_col
                    if sel // 2 < offset_row:
                        offset = (sel // 2) * 2
                    _draw(entries, sel, offset, path)
            elif t == kb.INPUT_SCROLL_UP:
                new_sel = (sel_row + 1) * 2 + sel_col
                if new_sel >= len(entries):      # col unavailable, fall to col 0
                    new_sel = (sel_row + 1) * 2
                new_sel = min(new_sel, n - 1)
                if new_sel != sel:
                    sel = new_sel
                    if sel // 2 >= offset_row + _FILE_ROWS:
                        offset = (sel // 2 - _FILE_ROWS + 1) * 2
                    _draw(entries, sel, offset, path)
            elif t == kb.INPUT_CURSOR_LEFT:
                if sel_col == 1:
                    sel -= 1
                    _draw(entries, sel, offset, path)
            elif t == kb.INPUT_CURSOR_RIGHT:
                if sel_col == 0 and sel + 1 < n:
                    sel += 1
                    _draw(entries, sel, offset, path)
            elif t == kb.INPUT_MODEL_MENU:
                return
            elif t == kb.INPUT_CHAR and ch == 'm':
                return

            elif t == kb.INPUT_ENTER:
                if sel == len(entries):   # Menu selected
                    return
                if not entries: break
                name, is_dir = entries[sel]
                if is_dir:
                    if name == '..':
                        p = path.rstrip('/')
                        idx = p.rfind('/')
                        path = p[:idx] if idx > 0 else '/'
                    else:
                        path = _join(path, name)
                    sel = 0; offset = 0
                else:
                    _draw(entries, sel, offset, path, hint='use e to execute')
                    _time.sleep_ms(1500)
                break

            elif t == kb.INPUT_CHAR and ch == 'e':
                if sel == len(entries) or not entries: continue
                name, is_dir = entries[sel]
                if is_dir or name == '..': continue
                if name.endswith('.py'):
                    _run_file(tft, kb, _join(path, name))
                else:
                    _draw(entries, sel, offset, path, hint=name + ': not a .py file')
                    _time.sleep_ms(1500)
                break

            elif t == kb.INPUT_DELETE:
                if not entries: continue
                name, is_dir = entries[sel]
                if name == '..': continue
                _draw(entries, sel, offset, path,
                      hint='Delete? Enter=Yes  Menu=No')
                confirmed = False
                while True:
                    _time.sleep_ms(20)
                    ev2 = kb.poll()
                    if ev2 is None: continue
                    t2, _ = ev2
                    if t2 == kb.INPUT_ENTER:   confirmed = True; break
                    elif t2 == kb.INPUT_MODEL_MENU: break
                if confirmed:
                    try:
                        fp = _join(path, name)
                        uos.rmdir(fp) if is_dir else uos.remove(fp)
                        sel = max(0, sel - 1)
                    except Exception as e:
                        _draw(entries, sel, offset, path, hint='Error: ' + str(e)[:28])
                        _time.sleep_ms(1500)
                break

            elif t == kb.INPUT_CHAR and ch == 'f':
                new_dir = _text_prompt('New folder:')
                if new_dir:
                    try:
                        uos.mkdir(_join(path, new_dir))
                    except Exception as e:
                        _draw(entries, sel, offset, path, hint='Error: ' + str(e)[:28])
                        _time.sleep_ms(1500)
                break

            elif t == kb.INPUT_CHAR and ch == 'r':
                if not entries: continue
                name, is_dir = entries[sel]
                if name == '..': continue
                new_name = _text_prompt('Rename to:', name)
                if new_name and new_name != name:
                    try:
                        uos.rename(_join(path, name), _join(path, new_name))
                    except Exception as e:
                        entries = _get_entries(path)
                        _draw(entries, sel, offset, path, hint='Error: ' + str(e)[:28])
                        _time.sleep_ms(1500)
                break
