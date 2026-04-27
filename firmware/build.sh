#!/usr/bin/env bash
set -e
MP_DIR=$HOME/micropython
IDF_DIR=$HOME/esp-idf
PROJ_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BOARD_DIR="$PROJ_DIR/firmware/boards/CRACK_S2"
MODULES_CMAKE="$PROJ_DIR/firmware/usbhid/micropython.cmake"

source "$IDF_DIR/export.sh"
cd "$MP_DIR/ports/esp32"

idf.py \
  -D MICROPY_BOARD=CRACK_S2 \
  -D MICROPY_BOARD_DIR="$BOARD_DIR" \
  -D USER_C_MODULES="$MODULES_CMAKE" \
  build

echo "Firmware: $MP_DIR/ports/esp32/build/micropython.bin"
