#Multi-line status display example
#300426 New by Claude Code. Added monospaced printing
#010526 Count = 20

import time

term = _TFTTerminal(tft, None, font=mono13) #monospaced font
def mprint(*a, **k): term.write(' '.join(str(x) for x in a) + k.get('end','\n'))
  
# Draw a fixed layout (ASCII only — font has no box-drawing characters)
mprint(" ------------------- ")
mprint("| Counter:          |")
mprint("| Status:           |")
mprint(" ------------------- ")

for i in range(20):
    # Update counter on row 2, col 11 (1-indexed)
    mprint(f"\x1b[2;11H{i:5}", end="")
    # Update status on row 3, col 11
    mprint(f"\x1b[3;11H{'running' if i < 99 else 'done   '}", end="")
    time.sleep_ms(100)