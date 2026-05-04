#!/usr/bin/env bash
set -e
PORT=${1:-/dev/ttyACM0}
BUILD=$HOME/micropython/ports/esp32/build

echo "If you need to re-build the firmare, use build.sh"
echo "Put device in bootloader: hold BOOT, press RST, release BOOT"
echo "Press Enter when ready..."
read -r

esptool --chip esp32s2 --port "$PORT" --baud 921600 \
  write_flash \
  0x1000  "$BUILD/bootloader/bootloader.bin" \
  0x8000  "$BUILD/partition_table/partition-table.bin" \
  0x10000 "$BUILD/micropython.bin"

echo "Done. Press RST to boot."
