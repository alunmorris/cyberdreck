#!/usr/bin/env bash
set -e
PORT=${1:-/dev/ttyACM0}
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

PYTHON=${PYTHON:-/home/alun/.platformio/penv/bin/python3}
echo "Building VFS image..."
"$PYTHON" "$SCRIPT_DIR/make_vfs.py"

echo ""
echo "Put device in bootloader: hold BOOT, press RST, release BOOT"
echo "Press Enter when ready..."
read -r

esptool --chip esp32s2 --port "$PORT" write_flash 0x200000 "$SCRIPT_DIR/vfs.img"
echo "Done. Press RST to boot."
