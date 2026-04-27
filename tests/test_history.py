# tests/test_history.py — run with desktop micropython or cpython
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import types

cfg = types.ModuleType('config')
cfg.MAX_LINES = 150
cfg.COL_AI    = 0xF760
cfg.COL_USER  = 0x07FF
cfg.COL_ERROR = 0xF800
cfg.SCREEN_W  = 320
sys.modules['config'] = cfg

import history

def test_add_and_wrap():
    history.clear()
    history.add('user', 'Hello world')
    history.add('ai', 'Hi there, this is a longer AI response that should wrap onto multiple lines if needed.')
    history.rebuild_lines(measure_fn=lambda t: len(t) * 6)
    assert len(history.lines) >= 2, f"Expected >=2 lines, got {len(history.lines)}"
    assert history.lines[0]['text'] == 'Hello world'
    assert history.lines[0]['is_user'] == True
    assert history.lines[1]['is_user'] == False
    print("PASS test_add_and_wrap")

def test_eviction():
    history.clear()
    history.HEAP_BUDGET = 50
    history.add('user', 'A' * 30)
    history.add('ai',   'B' * 30)
    history.add('user', 'C' * 30)   # triggers eviction of first pair
    msgs = history.get_messages()
    assert len(msgs) == 1, f"Expected 1 message, got {len(msgs)}"
    assert msgs[0]['text'].startswith('C')
    print("PASS test_eviction")

def test_scroll():
    history.clear()
    history.HEAP_BUDGET = 8000
    for i in range(20):
        history.add('user', f'Message {i}')
    history.rebuild_lines(measure_fn=lambda t: len(t) * 6)
    initial = history.scroll_offset
    history.scroll_up()
    assert history.scroll_offset == initial + 1
    history.scroll_down()
    assert history.scroll_offset == initial
    print("PASS test_scroll")

def test_display_only_excluded():
    history.clear()
    history.HEAP_BUDGET = 8000
    history.add('user', 'real question')
    history.add('ai', 'placeholder', display_only=True)
    msgs = history.get_messages()
    assert len(msgs) == 1
    assert msgs[0]['text'] == 'real question'
    print("PASS test_display_only_excluded")

def test_sanitise_non_ascii():
    history.clear()
    history.HEAP_BUDGET = 8000
    history.add('ai', 'Hello \x00 world \x01 end')
    assert history._messages[0]['text'] == 'Hello  world  end'
    print("PASS test_sanitise_non_ascii")

test_add_and_wrap()
test_eviction()
test_scroll()
test_display_only_excluded()
test_sanitise_non_ascii()
print("All history tests passed.")
