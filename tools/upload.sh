#!/usr/bin/env bash
set -e
PORT=${1:-/dev/ttyUSB0}
APP=/home/alun/esp32/micropython/app

echo "Uploading to $PORT..."
mpremote connect $PORT \
    mkdir :fonts \
    cp $APP/config.py    :config.py \
    cp $APP/secrets.py   :secrets.py \
    cp $APP/hal_kb.py    :hal_kb.py \
    cp $APP/display.py   :display.py \
    cp $APP/writer.py    :writer.py \
    cp $APP/fonts/dejavu14.py :fonts/dejavu14.py \
    cp $APP/history.py   :history.py \
    cp $APP/ui.py        :ui.py \
    cp $APP/wifi_mgr.py  :wifi_mgr.py \
    cp $APP/api.py       :api.py \
    cp $APP/main.py      :main.py \
    reset
echo "Done."
