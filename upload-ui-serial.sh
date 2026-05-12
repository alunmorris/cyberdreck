#!/bin/bash
# 120526 v1.1 — use relative path
DIR="$(dirname "$0")"
mpremote connect /dev/ttyUSB0 cp "$DIR/app/ui.py" :/ui.py + reset
