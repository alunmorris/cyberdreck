#!/bin/bash
# 120526 v1.1 — use relative path
DIR="$(dirname "$0")"
mpremote connect /dev/ttyACM0 cp "$DIR/app/main.py" :/main.py + reset
