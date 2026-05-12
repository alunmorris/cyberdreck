#!/usr/bin/env bash
set -e
PORT=${1:-/dev/ttyACM0}
APP="$(dirname "$0")/../app"

echo "Uploading to $PORT..."
mpremote connect $PORT mkdir :fonts 2>/dev/null || true
mpremote connect $PORT cp $APP/config.py           :config.py
mpremote connect $PORT cp $APP/secrets.py          :secrets.py
mpremote connect $PORT cp $APP/hal_kb.py           :hal_kb.py
mpremote connect $PORT cp $APP/display.py          :display.py
mpremote connect $PORT cp $APP/writer.py           :writer.py
mpremote connect $PORT cp $APP/fonts/dejavu14.py   :fonts/dejavu14.py
mpremote connect $PORT cp $APP/fonts/dejavu14_ru.py :fonts/dejavu14_ru.py
mpremote connect $PORT cp $APP/fonts/dejavu24bold_ru.py :fonts/dejavu24bold_ru.py
mpremote connect $PORT cp $APP/fonts/mono13.py     :fonts/mono13.py
mpremote connect $PORT cp $APP/history.py          :history.py
mpremote connect $PORT cp $APP/ui.py               :ui.py
mpremote connect $PORT cp $APP/wifi_mgr.py         :wifi_mgr.py
mpremote connect $PORT cp $APP/api.py              :api.py
mpremote connect $PORT cp $APP/repl_term.py        :repl_term.py
mpremote connect $PORT cp $APP/getprog.py          :getprog.py
mpremote connect $PORT cp $APP/main.py             :main.py
mpremote connect $PORT reset
echo "Done."
