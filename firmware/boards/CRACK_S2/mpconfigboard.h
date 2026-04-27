// firmware/boards/CRACK_S2/mpconfigboard.h
// CRACK_S2: ESP32-S2 Mini with USB OTG host mode (keyboard).
// USB CDC disabled — REPL via UART0 (GPIO43=TX, GPIO44=RX) at 115200 baud.
#define MICROPY_HW_BOARD_NAME "CRACK ESP32-S2"
#define MICROPY_HW_MCU_NAME   "ESP32-S2"

// 4MB flash, no PSRAM
#define MICROPY_HW_FLASH_SIZE  (4 * 1024 * 1024)

// UART0 for REPL (USB OTG used for keyboard host)
#define MICROPY_HW_UART_REPL        0
#define MICROPY_HW_UART_REPL_BAUD   115200

// Disable USB device stack so OTG peripheral is free for usb_host
#define MICROPY_HW_USB_CDC          0
#define MICROPY_PY_MACHINE_USB_DEVICE 0
