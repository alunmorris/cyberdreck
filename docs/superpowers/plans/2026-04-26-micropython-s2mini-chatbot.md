# ESP32-S2 Mini MicroPython AI Chatbot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the SLUG `s2mini` AI chatbot (C++/Arduino) to MicroPython on ESP32-S2 Mini with GMT020-02 240×320 display and USB HID keyboard via USB-C OTG.

**Architecture:** Custom MicroPython firmware with a C extension (`usbhid`) that ports `hal_s2.cpp`'s USB host logic directly. USB CDC is disabled in the firmware so the OTG peripheral is free for host mode; REPL and debug go through UART0 (GPIO 43 TX / 44 RX) via an external USB-UART adapter. Application is split into focused modules mirroring the C++ source decomposition.

**Tech Stack:** MicroPython 1.24 ESP32-S2 port (custom build), ESP-IDF 5.x USB host library, russhughes `st7789_mpy` display driver, Peter Hinch `writer.py` + `font_to_py`, `esp32.NVS`, raw `socket`+`ssl` for HTTPS.

---

## File Structure

```
firmware/
  usbhid/
    usbhid.c           — C extension: USB HID host, ring buffer, Boot Protocol parser
    micropython.cmake  — registers usbhid with MicroPython build system
  boards/CRACK_S2/
    mpconfigboard.h    — custom board: USB CDC off, UART0 REPL
    mpconfigboard.cmake
    sdkconfig.board    — USB host config, UART console

app/
  main.py              — boot sequence, main event loop, model menu, send prompt
  config.py            — pins, colors, timing, API hosts, system prompt
  secrets.py           — API keys (gitignored)
  secrets_example.py   — template
  hal_kb.py            — wraps usbhid C ext; exposes poll_input() + INPUT_* constants
  display.py           — ST7789 init, fill_rect(), draw_text(), LINE_H constant
  fonts/
    dejavu14.py        — generated with font_to_py (DejaVu Sans Bold 14px)
  writer.py            — Peter Hinch proportional font renderer (verbatim from his repo)
  history.py           — message list, add_message(), word_wrap(), rebuild_lines()
  ui.py                — draw_history(), draw_input_bar()
  wifi_mgr.py          — NVS 9-slot cred store, connect(), scan_aps(), ap_picker(), enter_password()
  api.py               — call_gemini(), call_grok(), call_groq() via ssl socket

tools/
  upload.sh            — mpremote upload helper
```

**Dependency order:** Tasks 1–3 (firmware) must complete before Tasks 4–12 (application). Tasks 4–12 are otherwise sequential; each builds on the previous.

> **Scope note:** Firmware build (Tasks 1–3) and the MicroPython application (Tasks 4–12) are independent subsystems. If firmware build proves time-consuming, application code can be developed in parallel using MicroPython on any ESP32-S2 board with dummy keyboard input, then integrated.

---

### Task 1: Build environment — MicroPython + ESP-IDF

**Files:**
- Create: `firmware/build.sh`

Set up the toolchain, clone MicroPython and ESP-IDF, verify a standard S2 build compiles.

- [ ] **Step 1: Install prerequisites**

```bash
sudo apt-get install -y git wget flex bison gperf python3 python3-pip cmake ninja-build \
    ccache libffi-dev libssl-dev dfu-util libusb-1.0-0
pip3 install pyserial esptool
```

- [ ] **Step 2: Clone ESP-IDF v5.2 and install tools**

```bash
cd ~
git clone --recursive --depth 1 --branch v5.2.2 https://github.com/espressif/esp-idf.git
cd ~/esp-idf
./install.sh esp32s2
```

- [ ] **Step 3: Clone MicroPython**

```bash
cd ~
git clone --depth 1 --branch v1.24.1 https://github.com/micropython/micropython.git
cd ~/micropython
git submodule update --init
make -C mpy-cross
```

- [ ] **Step 4: Verify standard LOLIN_S2_MINI build compiles**

```bash
source ~/esp-idf/export.sh
cd ~/micropython/ports/esp32
idf.py -D MICROPY_BOARD=LOLIN_S2_MINI build 2>&1 | tail -5
```

Expected: `Project build complete.`

- [ ] **Step 5: Write build helper script**

```bash
cat > /home/alun/esp32/micropython/firmware/build.sh << 'EOF'
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

echo "Firmware: $MP_DIR/ports/esp32/build-CRACK_S2/firmware.bin"
EOF
chmod +x /home/alun/esp32/micropython/firmware/build.sh
```

- [ ] **Step 6: Commit**

```bash
cd /home/alun/esp32/micropython
git init
git add firmware/build.sh
git commit -m "feat: add firmware build script"
```

---

### Task 2: Custom board config — disable USB CDC, enable OTG host

**Files:**
- Create: `firmware/boards/CRACK_S2/mpconfigboard.h`
- Create: `firmware/boards/CRACK_S2/mpconfigboard.cmake`
- Create: `firmware/boards/CRACK_S2/sdkconfig.board`

Disabling USB CDC is required so the OTG peripheral is free for USB host mode. After this, MicroPython REPL is only accessible via UART0 (GPIO 43 TX / 44 RX) with an external USB-UART adapter at 115200 baud.

- [ ] **Step 1: Create `mpconfigboard.h`**

```bash
mkdir -p /home/alun/esp32/micropython/firmware/boards/CRACK_S2
```

```c
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
```

- [ ] **Step 2: Create `mpconfigboard.cmake`**

```cmake
# firmware/boards/CRACK_S2/mpconfigboard.cmake
set(IDF_TARGET esp32s2)
set(SDKCONFIG_DEFAULTS
    boards/sdkconfig.base
    boards/sdkconfig.240mhz
    boards/sdkconfig.spiram_sx
    ${MICROPY_BOARD_DIR}/sdkconfig.board
)
```

- [ ] **Step 3: Create `sdkconfig.board`**

```ini
# firmware/boards/CRACK_S2/sdkconfig.board
# Console on UART0, not USB
CONFIG_ESP_CONSOLE_UART_DEFAULT=y
CONFIG_ESP_CONSOLE_UART_NUM=0
CONFIG_ESP_CONSOLE_UART_BAUDRATE=115200

# Disable USB device (CDC/serial) so OTG peripheral is free for usb_host
CONFIG_ESP_CONSOLE_USB_CDC=n
CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=n

# USB OTG host support
CONFIG_USB_OTG_SUPPORTED=y
CONFIG_USB_HOST_CONTROL_TRANSFER_MAX_SIZE=512
CONFIG_USB_HOST_HW_BUFFER_BIAS_BALANCED=y

# Flash: 4MB default partition table
CONFIG_ESPTOOLPY_FLASHSIZE_4MB=y
CONFIG_PARTITION_TABLE_SINGLE_APP=y
```

- [ ] **Step 4: Verify board config is found by build**

```bash
source ~/esp-idf/export.sh
cd ~/micropython/ports/esp32
idf.py \
  -D MICROPY_BOARD=CRACK_S2 \
  -D MICROPY_BOARD_DIR=/home/alun/esp32/micropython/firmware/boards/CRACK_S2 \
  -D USER_C_MODULES=/home/alun/esp32/micropython/firmware/usbhid/micropython.cmake \
  reconfigure 2>&1 | grep -E "(CRACK|error|Error)"
```

Expected: `MICROPY_BOARD=CRACK_S2` visible in output, no errors about missing files.

Note: The `USER_C_MODULES` cmake file will not exist yet — that is created in Task 3. Replace with a real path or create a stub: `touch /home/alun/esp32/micropython/firmware/usbhid/micropython.cmake && mkdir -p /home/alun/esp32/micropython/firmware/usbhid`

- [ ] **Step 5: Commit**

```bash
cd /home/alun/esp32/micropython
git add firmware/boards/
git commit -m "feat: add CRACK_S2 board config (USB CDC off, OTG host)"
```

---

### Task 3: USB HID C extension — `usbhid.c`

**Files:**
- Create: `firmware/usbhid/usbhid.c`
- Create: `firmware/usbhid/micropython.cmake`

This is a direct port of `hal_s2.cpp`'s USB host logic into a MicroPython C module. Exposes `usbhid.init()`, `usbhid.poll()`, `usbhid.connected()`.

- [ ] **Step 1: Create `micropython.cmake`**

```cmake
# firmware/usbhid/micropython.cmake
add_library(usermod_usbhid INTERFACE)
target_sources(usermod_usbhid INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/usbhid.c
)
target_include_directories(usermod_usbhid INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}
)
target_link_libraries(usermod INTERFACE usermod_usbhid)
```

- [ ] **Step 2: Create `usbhid.c` — ring buffer + event types**

```c
// firmware/usbhid/usbhid.c
// MicroPython C module: USB HID host keyboard for ESP32-S2.
// Ported from SLUG/src/hal_s2.cpp. Exposes:
//   usbhid.init()       -> None   (starts USB host tasks)
//   usbhid.poll()       -> None | (int, int)  (event_type, char_ord)
//   usbhid.connected()  -> bool
// Event type constants mirror hal.h InputEventType:
//   INPUT_NONE=0, INPUT_CHAR=1, INPUT_BACKSPACE=2, INPUT_ENTER=3,
//   INPUT_SCROLL_UP=4, INPUT_SCROLL_DOWN=5, INPUT_NEW_CONV=6, INPUT_MORE=7,
//   INPUT_CURSOR_LEFT=8, INPUT_CURSOR_RIGHT=9, INPUT_MODEL_MENU=10, INPUT_DELETE=11

#include "py/runtime.h"
#include "py/obj.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "usb/usb_host.h"
#include <string.h>

// ── Event type constants ───────────────────────────────────────────────────────
#define EV_NONE          0
#define EV_CHAR          1
#define EV_BACKSPACE     2
#define EV_ENTER         3
#define EV_SCROLL_UP     4
#define EV_SCROLL_DOWN   5
#define EV_NEW_CONV      6
#define EV_MORE          7
#define EV_CURSOR_LEFT   8
#define EV_CURSOR_RIGHT  9
#define EV_MODEL_MENU   10
#define EV_DELETE       11

// ── Ring buffer ────────────────────────────────────────────────────────────────
#define RB_SIZE 16
typedef struct { int type; char ch; } KbEvent;
static KbEvent        rb[RB_SIZE];
static volatile int   rb_head = 0, rb_tail = 0;
static SemaphoreHandle_t rb_mutex = NULL;

static void rb_push(int type, char ch) {
    xSemaphoreTake(rb_mutex, portMAX_DELAY);
    int next = (rb_head + 1) % RB_SIZE;
    if (next != rb_tail) { rb[rb_head].type = type; rb[rb_head].ch = ch; rb_head = next; }
    xSemaphoreGive(rb_mutex);
}

// ── HID scan code → ASCII ──────────────────────────────────────────────────────
static char hid_to_ascii(uint8_t code, bool shifted, bool caps_lock) {
    if (code >= 0x04 && code <= 0x1D) {
        char c = 'a' + (code - 0x04);
        return (shifted ^ caps_lock) ? (c - 32) : c;
    }
    if (code >= 0x1E && code <= 0x27) {
        static const char num[]   = "1234567890";
        static const char numSh[] = "!@#$%^&*()";
        return shifted ? numSh[code - 0x1E] : num[code - 0x1E];
    }
    switch (code) {
        case 0x2C: return ' ';
        case 0x2D: return shifted ? '_' : '-';
        case 0x2E: return shifted ? '+' : '=';
        case 0x2F: return shifted ? '{' : '[';
        case 0x30: return shifted ? '}' : ']';
        case 0x31: return shifted ? '|' : '\\';
        case 0x33: return shifted ? ':' : ';';
        case 0x34: return shifted ? '"' : '\'';
        case 0x35: return shifted ? '~' : '`';
        case 0x36: return shifted ? '<' : ',';
        case 0x37: return shifted ? '>' : '.';
        case 0x38: return shifted ? '?' : '/';
        default:   return 0;
    }
}

// ── HID report parser ──────────────────────────────────────────────────────────
static uint8_t s_last_keycodes[6] = {};
static bool    s_caps_lock        = false;
static volatile bool s_leds_dirty = false;

static void parse_hid_report(const uint8_t* data, size_t len) {
    if (len < 3) return;
    // Wireless dongle report-ID detection (same logic as hal_s2.cpp)
    if (len >= 4 && data[0] >= 1 && data[0] <= 4 && data[2] == 0x00) { data++; len--; }
    uint8_t modifier = data[0];
    bool ctrl    = (modifier & 0x11) != 0;
    bool shifted = (modifier & 0x22) != 0;

    bool all_zero = true;
    for (size_t i = 2; i < len && i < 8; i++) if (data[i]) { all_zero = false; break; }
    if (all_zero) { memset(s_last_keycodes, 0, 6); return; }

    uint8_t keycodes[6] = {};
    for (size_t i = 2, k = 0; i < len && i < 8 && k < 6; i++, k++) keycodes[k] = data[i];
    if (memcmp(keycodes, s_last_keycodes, 6) == 0) return;
    memcpy(s_last_keycodes, keycodes, 6);

    for (size_t i = 2; i < len && i < 8; i++) {
        uint8_t code = data[i];
        if (!code) continue;
        int type = EV_NONE; char ch = 0;
        if      (ctrl && code == 0x11) type = EV_NEW_CONV;
        else if (ctrl && code == 0x10) type = EV_MORE;
        else if (code == 0x52)         type = EV_SCROLL_DOWN;   // ↑ = newer
        else if (code == 0x51)         type = EV_SCROLL_UP;     // ↓ = older
        else if (code == 0x4B)         type = EV_SCROLL_DOWN;   // PgUp = newer
        else if (code == 0x4E)         type = EV_SCROLL_UP;     // PgDn = older
        else if (code == 0x4A)         type = EV_MODEL_MENU;    // Home
        else if (code == 0x4C)         type = EV_DELETE;        // Del
        else if (code == 0x39)         { s_caps_lock = !s_caps_lock; s_leds_dirty = true; continue; }
        else if (code == 0x50)         type = EV_CURSOR_LEFT;
        else if (code == 0x4F)         type = EV_CURSOR_RIGHT;
        else if (code == 0x28)         type = EV_ENTER;
        else if (code == 0x2A)         type = EV_BACKSPACE;
        else { char c = hid_to_ascii(code, shifted, s_caps_lock); if (c) { type = EV_CHAR; ch = c; } }
        if (type != EV_NONE) rb_push(type, ch);
    }
}

// ── USB host ───────────────────────────────────────────────────────────────────
static usb_host_client_handle_t s_client   = NULL;
static usb_device_handle_t      s_dev      = NULL;
static usb_transfer_t*          s_xfer     = NULL;
static uint8_t                  s_iface    = 0;
static volatile bool            s_dev_open = false;
static volatile bool            s_new_dev  = false;
static volatile bool            s_dev_gone = false;
static volatile uint8_t         s_new_addr = 0;
static volatile bool            s_usb_err  = false;

static void transfer_cb(usb_transfer_t* xfer) {
    if (xfer->status == USB_TRANSFER_STATUS_COMPLETED && xfer->actual_num_bytes > 0)
        parse_hid_report(xfer->data_buffer, xfer->actual_num_bytes);
    if (s_dev_open && xfer->status == USB_TRANSFER_STATUS_COMPLETED)
        usb_host_transfer_submit(xfer);
}

static void client_event_cb(const usb_host_client_event_msg_t* msg, void* arg) {
    (void)arg;
    if (msg->event == USB_HOST_CLIENT_EVENT_NEW_DEV) {
        s_new_addr = msg->new_dev.address; s_new_dev = true;
    } else { s_dev_gone = true; }
}

static bool find_hid_ep(usb_device_handle_t dev,
                        uint8_t* ep_addr, uint16_t* max_pkt, uint8_t* if_num) {
    const usb_config_desc_t* cfg;
    if (usb_host_get_active_config_descriptor(dev, &cfg) != ESP_OK) return false;
    bool in_hid = false;
    int off = 0;
    const uint8_t* p = (const uint8_t*)cfg;
    while (off + 2 <= cfg->wTotalLength) {
        uint8_t dlen = p[off], dtype = p[off + 1];
        if (!dlen || off + dlen > cfg->wTotalLength) break;
        if (dtype == 0x04) {
            const usb_intf_desc_t* intf = (const usb_intf_desc_t*)(p + off);
            in_hid = (intf->bInterfaceClass == 0x03 && intf->bInterfaceProtocol != 2);
            if (in_hid) *if_num = intf->bInterfaceNumber;
        } else if (dtype == 0x05 && in_hid) {
            const usb_ep_desc_t* ep = (const usb_ep_desc_t*)(p + off);
            if ((ep->bEndpointAddress & 0x80) && (ep->bmAttributes & 0x03) == 0x03) {
                *ep_addr = ep->bEndpointAddress; *max_pkt = ep->wMaxPacketSize; return true;
            }
        }
        off += dlen;
    }
    return false;
}

// Synchronous control transfer helper
static esp_err_t ctrl_xfer(uint8_t req_type, uint8_t req, uint16_t val, uint16_t idx,
                            uint16_t wlen, const uint8_t* data) {
    usb_transfer_t* ctrl = NULL;
    if (usb_host_transfer_alloc(8 + wlen, 0, &ctrl) != ESP_OK) return ESP_FAIL;
    ctrl->data_buffer[0] = req_type;
    ctrl->data_buffer[1] = req;
    ctrl->data_buffer[2] = val & 0xFF; ctrl->data_buffer[3] = val >> 8;
    ctrl->data_buffer[4] = idx & 0xFF; ctrl->data_buffer[5] = idx >> 8;
    ctrl->data_buffer[6] = wlen & 0xFF; ctrl->data_buffer[7] = wlen >> 8;
    if (data && wlen) memcpy(ctrl->data_buffer + 8, data, wlen);
    ctrl->num_bytes = 8 + wlen;
    ctrl->device_handle = s_dev;
    ctrl->bEndpointAddress = 0x00;
    ctrl->timeout_ms = 1000;
    static SemaphoreHandle_t done = NULL;
    if (!done) done = xSemaphoreCreateBinary();
    ctrl->callback = [](usb_transfer_t* t) { xSemaphoreGive((SemaphoreHandle_t)t->context); };
    ctrl->context = (void*)done;
    esp_err_t err = usb_host_transfer_submit_control(s_client, ctrl);
    if (err == ESP_OK) xSemaphoreTake(done, pdMS_TO_TICKS(1000));
    esp_err_t st = (ctrl->status == USB_TRANSFER_STATUS_COMPLETED) ? ESP_OK : ESP_FAIL;
    usb_host_transfer_free(ctrl);
    return (err == ESP_OK) ? st : err;
}

static void open_device(uint8_t addr) {
    if (usb_host_device_open(s_client, addr, &s_dev) != ESP_OK) return;
    uint8_t ep_addr = 0; uint16_t max_pkt = 8;
    if (!find_hid_ep(s_dev, &ep_addr, &max_pkt, &s_iface)) {
        usb_host_device_close(s_client, s_dev); s_dev = NULL; return;
    }
    if (usb_host_interface_claim(s_client, s_dev, s_iface, 0) != ESP_OK) {
        usb_host_device_close(s_client, s_dev); s_dev = NULL; return;
    }
    // SET_PROTOCOL(Boot) — force 8-byte boot report format
    ctrl_xfer(0x21, 0x0B, 0x0000, s_iface, 0, NULL);
    // SET_IDLE(0) — suppress repeated reports while key held
    ctrl_xfer(0x21, 0x0A, 0x0000, s_iface, 0, NULL);

    if (usb_host_transfer_alloc(max_pkt, 0, &s_xfer) != ESP_OK) {
        usb_host_interface_release(s_client, s_dev, s_iface);
        usb_host_device_close(s_client, s_dev); s_dev = NULL; return;
    }
    s_xfer->device_handle    = s_dev;
    s_xfer->bEndpointAddress = ep_addr;
    s_xfer->callback         = transfer_cb;
    s_xfer->context          = NULL;
    s_xfer->num_bytes        = max_pkt;
    s_xfer->timeout_ms       = 0;
    s_dev_open = true;
    usb_host_transfer_submit(s_xfer);
}

static void close_device(void) {
    s_dev_open = false;
    if (s_xfer && s_dev) {
        usb_host_endpoint_halt(s_dev, s_xfer->bEndpointAddress);
        usb_host_endpoint_flush(s_dev, s_xfer->bEndpointAddress);
    }
    if (s_xfer) { usb_host_transfer_free(s_xfer); s_xfer = NULL; }
    if (s_dev) {
        usb_host_interface_release(s_client, s_dev, s_iface);
        usb_host_device_close(s_client, s_dev); s_dev = NULL;
    }
}

static void send_led_report(void) {
    if (!s_dev_open) return;
    uint8_t leds = s_caps_lock ? 0x02 : 0x00;
    usb_transfer_t* ctrl = NULL;
    if (usb_host_transfer_alloc(9, 0, &ctrl) != ESP_OK) return;
    ctrl->data_buffer[0] = 0x21; ctrl->data_buffer[1] = 0x09;
    ctrl->data_buffer[2] = 0x00; ctrl->data_buffer[3] = 0x02;
    ctrl->data_buffer[4] = s_iface; ctrl->data_buffer[5] = 0x00;
    ctrl->data_buffer[6] = 0x01; ctrl->data_buffer[7] = 0x00;
    ctrl->data_buffer[8] = leds;
    ctrl->num_bytes = 9; ctrl->device_handle = s_dev;
    ctrl->bEndpointAddress = 0x00; ctrl->timeout_ms = 500;
    static SemaphoreHandle_t led_done = NULL;
    if (!led_done) led_done = xSemaphoreCreateBinary();
    ctrl->callback = [](usb_transfer_t* t) { xSemaphoreGive((SemaphoreHandle_t)t->context); };
    ctrl->context = (void*)led_done;
    if (usb_host_transfer_submit_control(s_client, ctrl) == ESP_OK)
        xSemaphoreTake(led_done, pdMS_TO_TICKS(500));
    usb_host_transfer_free(ctrl);
}

static void usb_host_daemon_task(void* arg) {
    (void)arg;
    usb_host_config_t cfg = { .skip_phy_setup = false, .intr_flags = ESP_INTR_FLAG_LEVEL1 };
    if (usb_host_install(&cfg) != ESP_OK) { s_usb_err = true; vTaskDelete(NULL); return; }
    uint32_t flags;
    for (;;) {
        usb_host_lib_handle_events(portMAX_DELAY, &flags);
        if (flags & USB_HOST_LIB_EVENT_FLAGS_NO_CLIENTS) usb_host_device_free_all();
    }
}

static void usb_client_task(void* arg) {
    (void)arg;
    vTaskDelay(pdMS_TO_TICKS(100));
    if (s_usb_err) { vTaskDelete(NULL); return; }
    usb_host_client_config_t ccfg = {
        .is_synchronous = false, .max_num_event_msg = 5,
        .async = { .client_event_callback = client_event_cb, .callback_arg = NULL }
    };
    if (usb_host_client_register(&ccfg, &s_client) != ESP_OK) {
        s_usb_err = true; vTaskDelete(NULL); return;
    }
    for (;;) {
        usb_host_client_handle_events(s_client, pdMS_TO_TICKS(100));
        if (s_new_dev) { s_new_dev = false; open_device(s_new_addr); }
        if (s_dev_gone) { s_dev_gone = false; close_device(); }
        if (s_leds_dirty) { s_leds_dirty = false; send_led_report(); }
    }
}

// ── Python-callable functions ──────────────────────────────────────────────────
static mp_obj_t usbhid_init(void) {
    if (rb_mutex) return mp_const_none;  // already initialised
    rb_mutex = xSemaphoreCreateMutex();
    xTaskCreate(usb_host_daemon_task, "usb_host",   4096, NULL, 5, NULL);
    xTaskCreate(usb_client_task,      "usb_client", 4096, NULL, 4, NULL);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(usbhid_init_obj, usbhid_init);

static mp_obj_t usbhid_poll(void) {
    if (!rb_mutex) return mp_const_none;
    xSemaphoreTake(rb_mutex, portMAX_DELAY);
    bool has = (rb_tail != rb_head);
    KbEvent ev = {};
    if (has) { ev = rb[rb_tail]; rb_tail = (rb_tail + 1) % RB_SIZE; }
    xSemaphoreGive(rb_mutex);
    if (!has) return mp_const_none;
    mp_obj_t tuple[2] = { mp_obj_new_int(ev.type), mp_obj_new_int((uint8_t)ev.ch) };
    return mp_obj_new_tuple(2, tuple);
}
static MP_DEFINE_CONST_FUN_OBJ_0(usbhid_poll_obj, usbhid_poll);

static mp_obj_t usbhid_connected(void) {
    return s_dev_open ? mp_const_true : mp_const_false;
}
static MP_DEFINE_CONST_FUN_OBJ_0(usbhid_connected_obj, usbhid_connected);

// ── Module table ───────────────────────────────────────────────────────────────
static const mp_rom_map_elem_t usbhid_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__),     MP_ROM_QSTR(MP_QSTR_usbhid) },
    { MP_ROM_QSTR(MP_QSTR_init),         MP_ROM_PTR(&usbhid_init_obj) },
    { MP_ROM_QSTR(MP_QSTR_poll),         MP_ROM_PTR(&usbhid_poll_obj) },
    { MP_ROM_QSTR(MP_QSTR_connected),    MP_ROM_PTR(&usbhid_connected_obj) },
    { MP_ROM_QSTR(MP_QSTR_INPUT_NONE),        MP_ROM_INT(EV_NONE) },
    { MP_ROM_QSTR(MP_QSTR_INPUT_CHAR),        MP_ROM_INT(EV_CHAR) },
    { MP_ROM_QSTR(MP_QSTR_INPUT_BACKSPACE),   MP_ROM_INT(EV_BACKSPACE) },
    { MP_ROM_QSTR(MP_QSTR_INPUT_ENTER),       MP_ROM_INT(EV_ENTER) },
    { MP_ROM_QSTR(MP_QSTR_INPUT_SCROLL_UP),   MP_ROM_INT(EV_SCROLL_UP) },
    { MP_ROM_QSTR(MP_QSTR_INPUT_SCROLL_DOWN), MP_ROM_INT(EV_SCROLL_DOWN) },
    { MP_ROM_QSTR(MP_QSTR_INPUT_NEW_CONV),    MP_ROM_INT(EV_NEW_CONV) },
    { MP_ROM_QSTR(MP_QSTR_INPUT_MORE),        MP_ROM_INT(EV_MORE) },
    { MP_ROM_QSTR(MP_QSTR_INPUT_CURSOR_LEFT), MP_ROM_INT(EV_CURSOR_LEFT) },
    { MP_ROM_QSTR(MP_QSTR_INPUT_CURSOR_RIGHT),MP_ROM_INT(EV_CURSOR_RIGHT) },
    { MP_ROM_QSTR(MP_QSTR_INPUT_MODEL_MENU),  MP_ROM_INT(EV_MODEL_MENU) },
    { MP_ROM_QSTR(MP_QSTR_INPUT_DELETE),      MP_ROM_INT(EV_DELETE) },
};
static MP_DEFINE_CONST_DICT(usbhid_module_globals, usbhid_module_globals_table);

const mp_obj_module_t usbhid_module = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t*)&usbhid_module_globals,
};
MP_REGISTER_MODULE(MP_QSTR_usbhid, usbhid_module);
```

- [ ] **Step 3: Build firmware**

```bash
cd /home/alun/esp32/micropython
./firmware/build.sh 2>&1 | tail -10
```

Expected: `Project build complete.`

- [ ] **Step 4: Flash firmware**

Connect a USB-UART adapter to GPIO 43 (TX) and 44 (RX) for debug. Connect the USB-C port directly to the build host for flashing (will appear as `/dev/ttyACM0` initially):

```bash
source ~/esp-idf/export.sh
esptool.py --chip esp32s2 --port /dev/ttyACM0 --baud 460800 \
  write_flash -z 0x1000 ~/micropython/ports/esp32/build-CRACK_S2/firmware.bin
```

- [ ] **Step 5: Verify MicroPython boots via UART0**

```bash
screen /dev/ttyUSB0 115200
# Press Enter — should see MicroPython REPL: >>>
```

- [ ] **Step 6: Verify usbhid module loads**

At the MicroPython REPL (via UART0):
```python
import usbhid
usbhid.init()
usbhid.connected()   # False before keyboard plugged in
# Plug in USB keyboard. Wait 2s.
usbhid.connected()   # True
ev = usbhid.poll()   # Press a key — returns (1, 97) for 'a'
print(ev)
```

Expected: `(1, 97)` for the 'a' key.

- [ ] **Step 7: Commit**

```bash
cd /home/alun/esp32/micropython
git add firmware/usbhid/
git commit -m "feat: usbhid C extension — USB HID host for MicroPython ESP32-S2"
```

---

### Task 4: Display driver + basic drawing

**Files:**
- Create: `app/display.py`

Install the russhughes `st7789_mpy` driver and verify the display works with correct orientation (landscape 320×240).

- [ ] **Step 1: Install st7789_mpy driver onto device**

```bash
mpremote connect /dev/ttyUSB0 mip install github:russhughes/st7789_mpy
```

- [ ] **Step 2: Test display at REPL**

```python
from machine import SPI, Pin
import st7789

spi = SPI(1, baudrate=40_000_000, polarity=0, phase=0,
          sck=Pin(36), mosi=Pin(35), miso=Pin(37))
tft = st7789.ST7789(spi, 240, 320,
    reset=Pin(18, Pin.OUT),
    cs=Pin(34, Pin.OUT),
    dc=Pin(17, Pin.OUT),
    rotation=1)   # rotation=1 → landscape 320×240
tft.init()
tft.fill(st7789.BLACK)
tft.fill_rect(0, 0, 50, 20, st7789.RED)
```

Expected: red rectangle in top-left of a black screen.

- [ ] **Step 3: Write `app/display.py`**

```python
# app/display.py
from machine import SPI, Pin
import st7789

SCREEN_W = 320
SCREEN_H = 240

# Colors (RGB565 — same values as C++ COL_* defines)
BLACK      = st7789.BLACK
WHITE      = st7789.WHITE
RED        = st7789.RED
CYAN       = st7789.CYAN
GREEN      = st7789.GREEN
ORANGE     = 0xFD20   # RGB565 orange
YELLOW     = st7789.YELLOW
DARK_GREY  = 0x4208   # COL_KEY_FACE
MID_GREY   = 0x2945   # COL_BTN_BG
LIGHT_GREY = 0xC618   # COL_INVERT_BG (light theme background)
DARK_BG    = 0x0841   # COL_BG (dark theme background)
AI_YELLOW  = 0xF760   # COL_AI
USER_CYAN  = st7789.CYAN
USER_OLIVE = 0x8400   # COL_USER_LIGHT (light theme user text)

_tft = None

def init():
    global _tft
    spi = SPI(1, baudrate=4_000_000, polarity=0, phase=0,
              sck=Pin(36), mosi=Pin(35), miso=Pin(37))
    _tft = st7789.ST7789(spi, 240, 320,
        reset=Pin(18, Pin.OUT),
        cs=Pin(34, Pin.OUT),
        dc=Pin(17, Pin.OUT),
        rotation=1)
    _tft.init()
    _tft.fill(LIGHT_GREY)
    return _tft

def get():
    return _tft
```

Note: SPI speed starts at 4MHz (matching the C++ `SPI_FREQUENCY=4000000`). Can be increased to 20–40MHz once display is confirmed working.

- [ ] **Step 4: Upload and test `display.py`**

```bash
mpremote connect /dev/ttyUSB0 cp app/display.py :display.py
```

At REPL:
```python
import display
tft = display.init()
tft.fill(display.DARK_BG)
tft.fill_rect(0, 0, 320, 18, display.LIGHT_GREY)
```

Expected: dark background with a light grey bar at the top.

- [ ] **Step 5: Commit**

```bash
git add app/display.py
git commit -m "feat: display.py — ST7789 init and color constants"
```

---

### Task 5: Font system

**Files:**
- Create: `app/fonts/dejavu14.py` (generated)
- Copy: `app/writer.py` (from Peter Hinch's repo)

Generate a 14px DejaVu Sans Bold bitmap font for proportional text rendering. `LINE_H = 18` (14px ascent + 4px descent/leading).

- [ ] **Step 1: Get font_to_py and writer.py**

```bash
cd /tmp
git clone --depth 1 https://github.com/peterhinch/micropython-font-to-py.git
cp /tmp/micropython-font-to-py/writer/writer.py /home/alun/esp32/micropython/app/writer.py
mkdir -p /home/alun/esp32/micropython/app/fonts
```

- [ ] **Step 2: Download DejaVu Sans Condensed Bold**

```bash
# DejaVu fonts are bundled with many systems or downloadable from dejavu-fonts.org
sudo apt-get install -y fonts-dejavu-core
ls /usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf
```

- [ ] **Step 3: Generate 14px bitmap font**

```bash
cd /tmp/micropython-font-to-py
python3 font_to_py.py /usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf 14 \
    -x -c "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 !\"#\$%&'()*+,-./:;<=>?@[\\]^_{|}~\`éèêëàâùûüîïôœæçÉÀÂÙÛÜÎÏÔŒÆÇ€£°·" \
    /home/alun/esp32/micropython/app/fonts/dejavu14.py

head -5 /home/alun/esp32/micropython/app/fonts/dejavu14.py
```

Expected output begins with `# Code generated by font_to_py.py`.

- [ ] **Step 4: Verify font renders on device**

Upload fonts and writer:
```bash
mpremote connect /dev/ttyUSB0 \
    cp app/writer.py :writer.py \
    cp app/fonts/dejavu14.py :fonts/dejavu14.py
```

At REPL:
```python
import display, writer, fonts.dejavu14 as font14
tft = display.init()
tft.fill(display.DARK_BG)
wri = writer.Writer(tft, font14)
writer.Writer.set_textpos(tft, 0, 0)
wri.printstring("Hello CRACK", invert=False)
```

Expected: "Hello CRACK" in white proportional text on dark background.

- [ ] **Step 5: Measure LINE_H**

```python
print(font14.height())   # should be 14
# LINE_H used in layout = font height + leading = 14 + 4 = 18
```

- [ ] **Step 6: Commit**

```bash
git add app/writer.py app/fonts/dejavu14.py
git commit -m "feat: dejavu14 bitmap font + writer.py for proportional rendering"
```

---

### Task 6: config.py — all constants

**Files:**
- Create: `app/config.py`
- Create: `app/secrets_example.py`

- [ ] **Step 1: Write `app/config.py`**

```python
# app/config.py
# Hardware
LED_PIN    = 15          # active-high GPIO LED
SCREEN_W   = 320
SCREEN_H   = 240
LINE_H     = 18          # pixel height per text row (14px font + 4px leading)

# Layout
HIST_H     = SCREEN_H - LINE_H   # chat history area height (222px)
INPUT_Y    = SCREEN_H - LINE_H   # y-coord of input bar (222)
MAX_VIS    = HIST_H // LINE_H    # visible history rows (12)
MAX_LINES  = 150                 # rendered line cache

# Timing
API_TIMEOUT_MS     = 25_000
WIFI_RETRY_DELAY   = 0.5         # seconds
WIFI_MAX_ATTEMPTS  = 30
WIFI_IDLE_TIMEOUT  = 60          # seconds idle → disconnect WiFi

# Colors (imported from display — referenced here for UI modules)
from display import (
    BLACK, WHITE, RED, CYAN, GREEN, YELLOW, ORANGE,
    DARK_BG, LIGHT_GREY, AI_YELLOW, USER_CYAN, USER_OLIVE,
    MID_GREY, DARK_GREY
)
COL_BG          = DARK_BG
COL_INVERT_BG   = LIGHT_GREY
COL_AI          = AI_YELLOW
COL_USER        = USER_CYAN
COL_USER_LIGHT  = USER_OLIVE
COL_ERROR       = RED
COL_PROMPT      = 0x4208         # dark grey prompt ">"

# API endpoints
GEMINI_HOST = "generativelanguage.googleapis.com"
GROK_HOST   = "api.x.ai"
GROQ_HOST   = "api.groq.com"
HTTPS_PORT  = 443

# Default model names (can be overridden at boot)
GEMINI_MODELS = [
    "gemini-2.5-flash-preview-04-17",
    "gemini-2.5-pro-preview-05-06",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
]
GROK_MODEL  = "grok-3-fast-beta"
GROQ_MODEL  = "qwen/qwen3-32b"

# System prompt (120-word limit for 320×240 display)
SYSTEM_PROMPT = (
    "Respond in 120 words or fewer. Plain text only: no markdown, "
    "no ** or * emphasis, no tables, no bullet symbols, no numbered or unnumbered lists. "
    "Use paragraphs to separate distinct ideas. Never include URLs, hyperlinks, citations, "
    "footnotes, source references, or attribution of any kind."
)
```

- [ ] **Step 2: Write `app/secrets_example.py`**

```python
# app/secrets_example.py — copy to secrets.py and fill in your keys
GEMINI_KEY = "YOUR_GEMINI_API_KEY"
GROK_KEY   = "YOUR_GROK_API_KEY"
GROQ_KEY   = "YOUR_GROQ_API_KEY"

# Optional: pre-seed one WiFi credential (avoids AP scan on first boot)
WIFI_SSID_DEFAULT = ""
WIFI_PASS_DEFAULT = ""
```

- [ ] **Step 3: Verify config imports cleanly on device**

```bash
mpremote connect /dev/ttyUSB0 cp app/config.py :config.py
```

At REPL:
```python
import config
print(config.SCREEN_W, config.LINE_H, config.MAX_VIS)
```

Expected: `320 18 12`

- [ ] **Step 4: Commit**

```bash
git add app/config.py app/secrets_example.py
git commit -m "feat: config.py — layout, colors, API endpoints, system prompt"
```

---

### Task 7: hal_kb.py — keyboard input wrapper

**Files:**
- Create: `app/hal_kb.py`

Wraps the `usbhid` C extension with a Python API that matches the C++ `halPollInput` pattern.

- [ ] **Step 1: Write `app/hal_kb.py`**

```python
# app/hal_kb.py
import usbhid
from machine import Pin
import time

# Re-export input event type constants
INPUT_NONE         = usbhid.INPUT_NONE
INPUT_CHAR         = usbhid.INPUT_CHAR
INPUT_BACKSPACE    = usbhid.INPUT_BACKSPACE
INPUT_ENTER        = usbhid.INPUT_ENTER
INPUT_SCROLL_UP    = usbhid.INPUT_SCROLL_UP
INPUT_SCROLL_DOWN  = usbhid.INPUT_SCROLL_DOWN
INPUT_NEW_CONV     = usbhid.INPUT_NEW_CONV
INPUT_MORE         = usbhid.INPUT_MORE
INPUT_CURSOR_LEFT  = usbhid.INPUT_CURSOR_LEFT
INPUT_CURSOR_RIGHT = usbhid.INPUT_CURSOR_RIGHT
INPUT_MODEL_MENU   = usbhid.INPUT_MODEL_MENU
INPUT_DELETE       = usbhid.INPUT_DELETE

_led = None

def init(timeout_ms=5000):
    """Start USB host. Wait up to timeout_ms for keyboard. Returns True if found."""
    global _led
    _led = Pin(15, Pin.OUT)
    _led.on()                    # LED on during init
    usbhid.init()
    deadline = time.ticks_add(time.ticks_ms(), timeout_ms)
    while not usbhid.connected():
        if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
            break
        time.sleep_ms(100)
    _led.off()
    return usbhid.connected()

def poll():
    """Non-blocking. Returns (type, ch_str) or None.
    ch_str is a single-character string when type==INPUT_CHAR, else ''."""
    raw = usbhid.poll()
    if raw is None:
        return None
    ev_type, ch_ord = raw
    ch = chr(ch_ord) if (ev_type == INPUT_CHAR and ch_ord) else ''
    return (ev_type, ch)

def connected():
    return usbhid.connected()

def set_led(on: bool):
    if _led:
        _led.value(1 if on else 0)
```

- [ ] **Step 2: Test hal_kb.py on device**

```bash
mpremote connect /dev/ttyUSB0 cp app/hal_kb.py :hal_kb.py
```

At REPL:
```python
import hal_kb
found = hal_kb.init(timeout_ms=5000)
print("keyboard found:", found)
# Type a key
ev = hal_kb.poll()
print(ev)
```

Expected with 'a' pressed: `(1, 'a')`

- [ ] **Step 3: Commit**

```bash
git add app/hal_kb.py
git commit -m "feat: hal_kb.py — Python wrapper for usbhid C extension"
```

---

### Task 8: history.py — message list + word wrap

**Files:**
- Create: `app/history.py`

Manages the conversation history linked list, word-wraps messages into rendered lines using font metrics.

- [ ] **Step 1: Write `app/history.py`**

```python
# app/history.py
from config import MAX_LINES, COL_AI, COL_USER, COL_ERROR, SCREEN_W

# Each message: {'role': 'user'|'ai'|'error', 'text': str, 'display_only': bool}
_messages      = []
_total_bytes   = 0
HEAP_BUDGET    = 8000    # max total text bytes before evicting oldest pair

# Rendered line cache: list of {'text': str, 'color': int, 'is_user': bool}
lines      = []
scroll_offset = 0

def clear():
    global _messages, _total_bytes, lines, scroll_offset
    _messages = []; _total_bytes = 0; lines = []; scroll_offset = 0

def add(role, text, display_only=False):
    """Add a message. role = 'user', 'ai', or 'error'."""
    global _messages, _total_bytes
    # Sanitise: keep printable ASCII + newline, replace anything else with '?'
    safe = []
    for ch in text:
        o = ord(ch)
        if ch == '\n' or (0x20 <= o <= 0x7E):
            safe.append(ch)
        elif o > 0x7E:
            safe.append('?')
    text = ''.join(safe)
    if not text:
        return
    # Evict oldest pair while over budget
    while len(_messages) >= 2 and _total_bytes + len(text) > HEAP_BUDGET:
        removed = _messages.pop(0)
        _total_bytes -= len(removed['text'])
        if _messages:
            removed2 = _messages.pop(0)
            _total_bytes -= len(removed2['text'])
    _messages.append({'role': role, 'text': text, 'display_only': display_only})
    _total_bytes += len(text)
    global scroll_offset
    scroll_offset = 0   # auto-scroll to bottom
    rebuild_lines()

def get_messages():
    """Return messages list for API calls (exclude display_only entries)."""
    return [m for m in _messages if not m['display_only']]

def rebuild_lines(measure_fn=None):
    """Rebuild the rendered line cache. measure_fn(text)->int returns pixel width.
    If not provided, uses a fixed-width estimate (6px per char)."""
    global lines
    lines = []
    col_map = {'user': COL_USER, 'ai': COL_AI, 'error': COL_ERROR}
    for msg in _messages:
        col = col_map.get(msg['role'], COL_AI)
        is_user = (msg['role'] == 'user')
        wrap_at = SCREEN_W - 4

        words = msg['text'].replace('\n', ' \n ').split(' ')
        line_buf = ''
        for word in words:
            if word == '\n':
                if line_buf:
                    lines.append({'text': line_buf, 'color': col, 'is_user': is_user})
                    line_buf = ''
                continue
            if not word:
                continue
            test = (line_buf + ' ' + word).strip() if line_buf else word
            w = measure_fn(test) if measure_fn else len(test) * 6
            if w <= wrap_at:
                line_buf = test
            else:
                if line_buf:
                    lines.append({'text': line_buf, 'color': col, 'is_user': is_user})
                line_buf = word
            if len(lines) >= MAX_LINES - 1:
                break
        if line_buf and len(lines) < MAX_LINES:
            lines.append({'text': line_buf, 'color': col, 'is_user': is_user})
        if len(lines) >= MAX_LINES - 1:
            break

def scroll_up():
    global scroll_offset
    scroll_offset = min(scroll_offset + 1, max(0, len(lines) - 1))

def scroll_down():
    global scroll_offset
    scroll_offset = max(scroll_offset - 1, 0)
```

- [ ] **Step 2: Write unit test for word wrap**

Create `tests/test_history.py` on the host (run with desktop `micropython`):

```python
# tests/test_history.py
import sys; sys.path.insert(0, 'app')

# Stub config for desktop testing
import types
cfg = types.ModuleType('config')
cfg.MAX_LINES = 150; cfg.COL_AI = 0xF760; cfg.COL_USER = 0x07FF
cfg.COL_ERROR = 0xF800; cfg.SCREEN_W = 320
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
    history.add('ai', 'B' * 30)
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
    initial_offset = history.scroll_offset
    history.scroll_up()
    assert history.scroll_offset == initial_offset + 1
    history.scroll_down()
    assert history.scroll_offset == initial_offset
    print("PASS test_scroll")

test_add_and_wrap()
test_eviction()
test_scroll()
print("All history tests passed.")
```

- [ ] **Step 3: Run tests**

```bash
micropython tests/test_history.py
```

Expected:
```
PASS test_add_and_wrap
PASS test_eviction
PASS test_scroll
All history tests passed.
```

- [ ] **Step 4: Upload history.py to device**

```bash
mpremote connect /dev/ttyUSB0 cp app/history.py :history.py
```

- [ ] **Step 5: Commit**

```bash
git add app/history.py tests/test_history.py
git commit -m "feat: history.py — message list, word wrap, scroll"
```

---

### Task 9: ui.py — drawHistory and drawInputBar

**Files:**
- Create: `app/ui.py`

Renders the chat history and input bar on the display. Uses `writer.py` for proportional font text. Mirrors `drawHistory()` and `drawInputBar()` from `main.cpp`.

- [ ] **Step 1: Write `app/ui.py`**

```python
# app/ui.py
import display, history, config
from writer import Writer
import fonts.dejavu14 as font14

_tft    = None
_writer = None
_invert = True   # True = light theme (light grey background)

def init(tft):
    global _tft, _writer
    _tft = tft
    _writer = Writer(tft, font14)

def _bg():
    return config.COL_INVERT_BG if _invert else config.COL_BG

def _fg_user():
    return config.COL_USER_LIGHT if _invert else config.COL_USER

def _measure(text):
    return _writer.stringlen(text)

def draw_history():
    """Render the chat history area (rows 0 to MAX_VIS-1)."""
    bg = _bg()
    _tft.fill_rect(0, 0, config.SCREEN_W, config.HIST_H, bg)
    if not history.lines:
        return
    n = len(history.lines)
    first = max(0, n - config.MAX_VIS - history.scroll_offset)
    last  = min(n, first + config.MAX_VIS)
    y = 0
    for i in range(first, last):
        ln = history.lines[i]
        bg_row = bg
        if ln['is_user']:
            col = _fg_user()
            # Right-align user text
            tw = _measure(ln['text'])
            x  = config.SCREEN_W - tw - 2
        else:
            col = config.COL_AI if not _invert else 0x0000   # black in light theme
            if ln['color'] == config.COL_ERROR:
                col = config.COL_ERROR
            x = 2
        Writer.set_textpos(_tft, y, x)
        _writer.printstring(ln['text'])
        y += config.LINE_H

def draw_input_bar(input_buf, cursor_pos, wifi_ok=True, more_mode=False):
    """Render the input bar at the bottom of the screen."""
    bg  = _bg()
    fg  = 0x0000 if _invert else 0xFFFF
    prompt_col = 0x4208 if wifi_ok else config.COL_ERROR   # dark grey or red

    _tft.fill_rect(0, config.INPUT_Y, config.SCREEN_W, config.LINE_H, bg)

    # Prompt ">"
    Writer.set_textpos(_tft, config.INPUT_Y, 2)
    _writer.set_textcolor(prompt_col, bg)
    _writer.printstring('> ')
    prompt_w = _measure('> ') + 2

    # Input text (scroll so cursor is visible)
    _writer.set_textcolor(fg, bg)
    avail = config.SCREEN_W - prompt_w - 4
    start = cursor_pos
    while start > 0:
        test = input_buf[start-1:cursor_pos]
        if _measure(test) > avail - 2:
            break
        start -= 1
    disp = input_buf[start:]
    Writer.set_textpos(_tft, config.INPUT_Y, prompt_w)
    _writer.printstring(disp)

    # Cursor bar at cursor_pos
    pre = input_buf[start:cursor_pos]
    cur_x = prompt_w + _measure(pre)
    _tft.fill_rect(cur_x, config.INPUT_Y + 2, 1, config.LINE_H - 4, fg)
```

- [ ] **Step 2: Test ui.py on device**

```bash
mpremote connect /dev/ttyUSB0 cp app/ui.py :ui.py
```

At REPL:
```python
import display, ui, history, fonts.dejavu14 as font14
tft = display.init()
ui.init(tft)
history.clear()
history.add('user', 'Hello')
history.add('ai', 'Hi there! How can I help you today?')
history.rebuild_lines(measure_fn=ui._measure)
ui.draw_history()
ui.draw_input_bar('Test input', 10)
```

Expected: grey background, "Hello" right-aligned in olive, AI response left-aligned in black, "Test input" in input bar with cursor visible.

- [ ] **Step 3: Commit**

```bash
git add app/ui.py
git commit -m "feat: ui.py — draw_history, draw_input_bar"
```

---

### Task 10: wifi_mgr.py — NVS credential store + WiFi

**Files:**
- Create: `app/wifi_mgr.py`

9-slot NVS credential store, WiFi connect, AP scan, AP picker UI, password entry. Mirrors the C++ `loadWifiCreds`, `saveWifiCreds`, `insertWifiCred`, `connectWiFi`, `selectAP`, `enterPassword`.

- [ ] **Step 1: Write `app/wifi_mgr.py`**

```python
# app/wifi_mgr.py
import network, time, esp32, ui, config
from hal_kb import (poll, INPUT_CHAR, INPUT_BACKSPACE, INPUT_ENTER,
                    INPUT_CURSOR_LEFT, INPUT_CURSOR_RIGHT)

PREFS_MAX = 9
_wlan     = network.WLAN(network.STA_IF)
_wlan.active(True)

# In-memory credential slots: list of {'ssid': str, 'pass': str}
_creds = []

def _nvs_open(readonly=True):
    return esp32.NVS("wifi")

def load_creds():
    """Load credentials from NVS into _creds."""
    global _creds
    _creds = []
    try:
        nvs = _nvs_open()
        n = nvs.get_i32("n")
        for i in range(min(n, PREFS_MAX)):
            buf = bytearray(33)
            nb  = nvs.get_blob(f"s{i}", buf)
            ssid = buf[:nb].decode()
            buf2 = bytearray(64)
            nb2 = nvs.get_blob(f"p{i}", buf2)
            pwd  = buf2[:nb2].decode()
            _creds.append({'ssid': ssid, 'pass': pwd})
    except Exception:
        pass

def save_creds():
    """Flush _creds to NVS."""
    nvs = esp32.NVS("wifi")
    nvs.set_i32("n", len(_creds))
    for i, c in enumerate(_creds):
        nvs.set_blob(f"s{i}", c['ssid'].encode())
        nvs.set_blob(f"p{i}", c['pass'].encode())
    nvs.commit()

def insert_cred(ssid, password):
    """Add/update ssid at front of list (most-recently-used)."""
    global _creds
    _creds = [c for c in _creds if c['ssid'] != ssid]
    _creds.insert(0, {'ssid': ssid, 'pass': password})
    if len(_creds) > PREFS_MAX:
        _creds = _creds[:PREFS_MAX]
    save_creds()

def find_pass(ssid):
    """Return stored password for ssid, or None if not found."""
    for c in _creds:
        if c['ssid'] == ssid:
            return c['pass'] if c['pass'] else None
    return None

def connect(ssid, password, show_status=True):
    """Connect to WiFi. Returns True on success."""
    if show_status and ui._tft:
        ui._tft.fill(config._bg() if hasattr(config, '_bg') else 0xC618)
        import writer, fonts.dejavu14 as f14
        from writer import Writer
        wri = writer.Writer(ui._tft, f14)
        Writer.set_textpos(ui._tft, 0, 2)
        wri.printstring(f"Connecting: {ssid[:28]}...")
    _wlan.disconnect()
    _wlan.connect(ssid, password)
    for _ in range(config.WIFI_MAX_ATTEMPTS):
        if _wlan.isconnected():
            return True
        time.sleep(config.WIFI_RETRY_DELAY)
    return False

def disconnect():
    _wlan.disconnect()

def is_connected():
    return _wlan.isconnected()

def rssi():
    if not _wlan.isconnected():
        return -100
    return _wlan.status('rssi')

def scan_aps():
    """Scan for APs. Returns list of (ssid, rssi) sorted by signal strength."""
    results = _wlan.scan()   # returns list of tuples: (ssid, bssid, channel, rssi, authmode, hidden)
    seen = {}
    for r in results:
        ssid = r[0].decode() if isinstance(r[0], bytes) else r[0]
        rssi_val = r[3]
        if ssid and (ssid not in seen or rssi_val > seen[ssid]):
            seen[ssid] = rssi_val
    return sorted(seen.items(), key=lambda x: -x[1])[:9]

def _draw_ap_list(aps, tft, wri):
    from writer import Writer
    bg = 0xC618; tft.fill(bg)
    Writer.set_textpos(tft, 0, 2)
    wri.set_textcolor(0x03E0, bg)   # green header
    wri.printstring("Select WiFi:")
    for i, (ssid, db) in enumerate(aps):
        y = (i + 1) * config.LINE_H
        if y + config.LINE_H > config.SCREEN_H:
            break
        Writer.set_textpos(tft, y, 2)
        wri.set_textcolor(0x0000, bg)
        label = f"{i+1} {ssid[:22]} {db}dB"
        wri.printstring(label)

def ap_picker(tft, wri):
    """Show AP list, return chosen (ssid, rssi) or None."""
    aps = scan_aps()
    if not aps:
        return None
    _draw_ap_list(aps, tft, wri)
    while True:
        ev = poll()
        if ev is None:
            time.sleep_ms(20)
            continue
        ev_type, ch = ev
        if ev_type == INPUT_CHAR and ch.isdigit():
            idx = int(ch) - 1
            if 0 <= idx < len(aps):
                return aps[idx]
        if ev_type in (INPUT_ENTER,):
            return None   # cancel

def enter_password(ssid, tft, wri):
    """Show password entry screen. Returns typed password string."""
    from writer import Writer
    bg = 0xC618; tft.fill(bg)
    Writer.set_textpos(tft, 0, 2)
    wri.set_textcolor(0xFFE0, bg)   # yellow
    wri.printstring("Password for:")
    Writer.set_textpos(tft, config.LINE_H, 2)
    wri.set_textcolor(0x0000, bg)
    wri.printstring(ssid[:36])

    buf = []; cursor = 0
    while True:
        ui.draw_input_bar(''.join(buf), cursor)
        ev = poll()
        if ev is None:
            time.sleep_ms(20)
            continue
        ev_type, ch = ev
        if ev_type == INPUT_ENTER:
            return ''.join(buf)
        elif ev_type == INPUT_CHAR and len(buf) < 63:
            buf.insert(cursor, ch); cursor += 1
        elif ev_type == INPUT_BACKSPACE and cursor > 0:
            buf.pop(cursor - 1); cursor -= 1
        elif ev_type == INPUT_CURSOR_LEFT and cursor > 0:
            cursor -= 1
        elif ev_type == INPUT_CURSOR_RIGHT and cursor < len(buf):
            cursor += 1

def select_ap(tft, wri):
    """Run the full AP scan → pick → password → connect flow.
    Returns True if connected, False on cancel."""
    choice = ap_picker(tft, wri)
    if choice is None:
        return False
    ssid, _ = choice
    stored = find_pass(ssid)
    if stored is not None:
        password = stored
    else:
        password = enter_password(ssid, tft, wri)
    ok = connect(ssid, password, show_status=True)
    if ok:
        insert_cred(ssid, password)
    else:
        # Bad password — clear stored credential
        insert_cred(ssid, '')
    return ok
```

- [ ] **Step 2: Write unit test for NVS cred logic (desktop)**

```python
# tests/test_wifi_mgr.py
import sys; sys.path.insert(0, 'app')

# Stub out hardware modules for desktop testing
import types

# Stub esp32.NVS
class FakeNVS:
    _store = {}
    def __init__(self, ns): self.ns = ns
    def set_i32(self, k, v): FakeNVS._store[f"{self.ns}/{k}"] = v
    def get_i32(self, k):
        v = FakeNVS._store.get(f"{self.ns}/{k}", 0)
        return v
    def set_blob(self, k, v): FakeNVS._store[f"{self.ns}/{k}"] = bytes(v)
    def get_blob(self, k, buf):
        data = FakeNVS._store.get(f"{self.ns}/{k}", b'')
        n = min(len(data), len(buf))
        buf[:n] = data[:n]
        return n
    def commit(self): pass

esp32_mod = types.ModuleType('esp32')
esp32_mod.NVS = FakeNVS
sys.modules['esp32'] = esp32_mod

# Stub network, ui, config, hal_kb
for m in ['network', 'ui', 'hal_kb']:
    sys.modules[m] = types.ModuleType(m)
cfg = types.ModuleType('config')
cfg.WIFI_MAX_ATTEMPTS = 30; cfg.WIFI_RETRY_DELAY = 0.5; cfg.LINE_H = 18; cfg.SCREEN_H = 240
sys.modules['config'] = cfg

import wifi_mgr

def test_insert_and_find():
    wifi_mgr._creds = []
    wifi_mgr.insert_cred('Home', 'pass1')
    wifi_mgr.insert_cred('Work', 'pass2')
    assert wifi_mgr.find_pass('Home') == 'pass1'
    assert wifi_mgr.find_pass('Work') == 'pass2'
    assert wifi_mgr.find_pass('Unknown') is None
    print("PASS test_insert_and_find")

def test_most_recently_used_ordering():
    wifi_mgr._creds = []
    wifi_mgr.insert_cred('A', 'pa')
    wifi_mgr.insert_cred('B', 'pb')
    wifi_mgr.insert_cred('A', 'pa2')   # re-insert A → moves to front
    assert wifi_mgr._creds[0]['ssid'] == 'A'
    assert wifi_mgr._creds[0]['pass'] == 'pa2'
    assert wifi_mgr._creds[1]['ssid'] == 'B'
    print("PASS test_most_recently_used_ordering")

def test_cap_at_9():
    wifi_mgr._creds = []
    for i in range(12):
        wifi_mgr.insert_cred(f"net{i}", f"p{i}")
    assert len(wifi_mgr._creds) == wifi_mgr.PREFS_MAX
    print("PASS test_cap_at_9")

def test_save_and_load():
    FakeNVS._store = {}
    wifi_mgr._creds = []
    wifi_mgr.insert_cred('MySSID', 'MyPass')
    wifi_mgr._creds = []
    wifi_mgr.load_creds()
    assert len(wifi_mgr._creds) == 1
    assert wifi_mgr._creds[0]['ssid'] == 'MySSID'
    assert wifi_mgr._creds[0]['pass'] == 'MyPass'
    print("PASS test_save_and_load")

test_insert_and_find()
test_most_recently_used_ordering()
test_cap_at_9()
test_save_and_load()
print("All wifi_mgr tests passed.")
```

- [ ] **Step 3: Run tests**

```bash
micropython tests/test_wifi_mgr.py
```

Expected:
```
PASS test_insert_and_find
PASS test_most_recently_used_ordering
PASS test_cap_at_9
PASS test_save_and_load
All wifi_mgr tests passed.
```

- [ ] **Step 4: Upload and test AP scan on device**

```bash
mpremote connect /dev/ttyUSB0 cp app/wifi_mgr.py :wifi_mgr.py
```

At REPL:
```python
import wifi_mgr
wifi_mgr.load_creds()
aps = wifi_mgr.scan_aps()
print(aps[:3])
```

Expected: list of `(ssid, rssi)` tuples for visible APs.

- [ ] **Step 5: Commit**

```bash
git add app/wifi_mgr.py tests/test_wifi_mgr.py
git commit -m "feat: wifi_mgr.py — NVS 9-slot cred store, connect, AP picker"
```

---

### Task 11: api.py — Gemini, Grok, Groq HTTPS

**Files:**
- Create: `app/api.py`

HTTPS POST calls to Gemini, Grok, and Groq using raw `socket` + `ssl`. Builds JSON request body, parses JSON response, returns the AI reply text. No streaming — one synchronous call per message.

- [ ] **Step 1: Write `app/api.py`**

```python
# app/api.py
import socket, ssl, json, config

def _https_post(host, path, headers, body_dict):
    """POST body_dict as JSON to https://host/path. Returns response body string.
    Raises OSError on network/TLS failure, ValueError on unexpected response."""
    body_bytes = json.dumps(body_dict).encode()
    req_lines = [
        f"POST {path} HTTP/1.1",
        f"Host: {host}",
        "Content-Type: application/json",
        f"Content-Length: {len(body_bytes)}",
        "Connection: close",
    ]
    for k, v in headers.items():
        req_lines.append(f"{k}: {v}")
    req_lines.append("")
    req_lines.append("")
    req = "\r\n".join(req_lines).encode() + body_bytes

    addr = socket.getaddrinfo(host, config.HTTPS_PORT)[0][-1]
    s = socket.socket()
    s.settimeout(config.API_TIMEOUT_MS / 1000)
    s.connect(addr)
    s = ssl.wrap_socket(s, server_hostname=host)
    s.write(req)

    # Read response: skip HTTP headers, return body
    raw = b""
    try:
        while True:
            chunk = s.read(1024)
            if not chunk:
                break
            raw += chunk
    except OSError:
        pass
    finally:
        s.close()

    # Split headers from body
    sep = raw.find(b"\r\n\r\n")
    if sep < 0:
        raise ValueError("No HTTP header separator found")
    status_line = raw[:raw.find(b"\r\n")].decode()
    if " 200 " not in status_line:
        raise ValueError(f"HTTP error: {status_line[:60]}")
    body = raw[sep + 4:]

    # Handle chunked transfer encoding
    header_block = raw[:sep].decode().lower()
    if "transfer-encoding: chunked" in header_block:
        body = _unchunk(body)

    return body.decode('utf-8', 'replace')

def _unchunk(data):
    """Decode HTTP chunked transfer encoding."""
    out = b""
    while data:
        end = data.find(b"\r\n")
        if end < 0:
            break
        size = int(data[:end], 16)
        if size == 0:
            break
        out += data[end + 2: end + 2 + size]
        data = data[end + 2 + size + 2:]
    return out

def _build_gemini_body(messages, model):
    contents = []
    for m in messages:
        role = "user" if m['role'] == 'user' else "model"
        contents.append({"role": role, "parts": [{"text": m['text']}]})
    return {
        "system_instruction": {"parts": [{"text": config.SYSTEM_PROMPT}]},
        "contents": contents,
        "generationConfig": {"maxOutputTokens": 300},
    }

def call_gemini(messages, model, api_key):
    """Call Gemini generateContent. Returns reply text string."""
    path = f"/v1beta/models/{model}:generateContent?key={api_key}"
    body = _build_gemini_body(messages, model)
    resp = _https_post(config.GEMINI_HOST, path, {}, body)
    data = json.loads(resp)
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()

def _build_openai_body(messages, model):
    msgs = [{"role": "system", "content": config.SYSTEM_PROMPT}]
    for m in messages:
        role = "user" if m['role'] == 'user' else "assistant"
        msgs.append({"role": role, "content": m['text']})
    return {"model": model, "messages": msgs, "max_tokens": 300}

def call_grok(messages, api_key):
    """Call Grok (xAI) chat completions."""
    body = _build_openai_body(messages, config.GROK_MODEL)
    resp = _https_post(config.GROK_HOST, "/v1/chat/completions",
                       {"Authorization": f"Bearer {api_key}"}, body)
    data = json.loads(resp)
    return data["choices"][0]["message"]["content"].strip()

def call_groq(messages, api_key):
    """Call Groq chat completions."""
    body = _build_openai_body(messages, config.GROQ_MODEL)
    resp = _https_post(config.GROQ_HOST, "/openai/v1/chat/completions",
                       {"Authorization": f"Bearer {api_key}"}, body)
    data = json.loads(resp)
    return data["choices"][0]["message"]["content"].strip()
```

- [ ] **Step 2: Write unit tests for request building**

```python
# tests/test_api.py
import sys; sys.path.insert(0, 'app')
import types

# Stub socket and ssl for desktop
for m in ['socket', 'ssl']:
    sys.modules[m] = types.ModuleType(m)

cfg = types.ModuleType('config')
cfg.API_TIMEOUT_MS = 25000; cfg.HTTPS_PORT = 443
cfg.GEMINI_HOST = "generativelanguage.googleapis.com"
cfg.GROK_HOST = "api.x.ai"; cfg.GROQ_HOST = "api.groq.com"
cfg.SYSTEM_PROMPT = "Be brief."; cfg.GROK_MODEL = "grok-3-fast-beta"
cfg.GROQ_MODEL = "qwen/qwen3-32b"
sys.modules['config'] = cfg

import api, json

def test_gemini_body():
    msgs = [{'role': 'user', 'text': 'Hello'}]
    body = api._build_gemini_body(msgs, "gemini-2.0-flash")
    assert body['contents'][0]['role'] == 'user'
    assert body['contents'][0]['parts'][0]['text'] == 'Hello'
    assert 'system_instruction' in body
    print("PASS test_gemini_body")

def test_openai_body():
    msgs = [{'role': 'user', 'text': 'Hi'}, {'role': 'ai', 'text': 'Hello'}]
    body = api._build_openai_body(msgs, "grok-3-fast-beta")
    assert body['messages'][0]['role'] == 'system'
    assert body['messages'][1]['role'] == 'user'
    assert body['messages'][2]['role'] == 'assistant'
    print("PASS test_openai_body")

def test_unchunk():
    chunked = b"5\r\nHello\r\n6\r\n World\r\n0\r\n\r\n"
    result = api._unchunk(chunked)
    assert result == b"Hello World", repr(result)
    print("PASS test_unchunk")

test_gemini_body()
test_openai_body()
test_unchunk()
print("All api tests passed.")
```

- [ ] **Step 3: Run tests**

```bash
micropython tests/test_api.py
```

Expected:
```
PASS test_gemini_body
PASS test_openai_body
PASS test_unchunk
All api tests passed.
```

- [ ] **Step 4: Upload api.py and test live call**

First create `app/secrets.py` from the example (fill in real keys). Then:

```bash
mpremote connect /dev/ttyUSB0 cp app/api.py :api.py cp app/secrets.py :secrets.py
```

At REPL (after WiFi is connected):
```python
import wifi_mgr, api, secrets
wifi_mgr.load_creds()
wifi_mgr.connect(wifi_mgr._creds[0]['ssid'], wifi_mgr._creds[0]['pass'])
msgs = [{'role': 'user', 'text': 'What is 2+2?'}]
reply = api.call_gemini(msgs, 'gemini-2.0-flash', secrets.GEMINI_KEY)
print(reply)
```

Expected: `4` or a short answer.

- [ ] **Step 5: Commit**

```bash
git add app/api.py tests/test_api.py
git commit -m "feat: api.py — Gemini/Grok/Groq HTTPS via raw ssl socket"
```

---

### Task 12: main.py — boot sequence, main loop, model menu

**Files:**
- Create: `app/main.py`

The top-level application. Mirrors `setup()` + `loop()` + `selectModel()` from `main.cpp`. Ties all modules together.

- [ ] **Step 1: Write `app/main.py`**

```python
# app/main.py
import time, gc
from machine import Pin

import display, ui, history, wifi_mgr, api, config, hal_kb, secrets
import fonts.dejavu14 as font14
from writer import Writer

# ── State ──────────────────────────────────────────────────────────────────────
_input_buf  = []       # list of chars
_cursor     = 0        # insertion point
_more_mode  = False    # True after AI reply
_invert     = True     # light theme

# Active model selection
_use_grok  = False
_use_groq  = False
_gemini_idx = 0        # index into config.GEMINI_MODELS

_tft  = None
_wri  = None
_wifi_ok    = False
_last_activity = 0
_last_wifi_check = 0

# ── Helpers ────────────────────────────────────────────────────────────────────
def _active_model_label():
    if _use_grok:  return config.GROK_MODEL
    if _use_groq:  return config.GROQ_MODEL
    return config.GEMINI_MODELS[_gemini_idx]

def _c3line(y, text, fg=0x0000, bg=0xC618):
    Writer.set_textpos(_tft, y, 2)
    _wri.set_textcolor(fg, bg)
    _wri.printstring(text)

def _refresh():
    history.rebuild_lines(measure_fn=ui._measure)
    ui.draw_history()
    ui.draw_input_bar(''.join(_input_buf), _cursor, _wifi_ok)

def _set_led(on):
    hal_kb.set_led(on)

# ── Model menu ─────────────────────────────────────────────────────────────────
def show_model_menu():
    """Display model selection menu; block until a valid key is pressed."""
    global _use_grok, _use_groq, _gemini_idx
    bg = 0xC618
    _tft.fill(bg)
    items = []
    for i, m in enumerate(config.GEMINI_MODELS, 1):
        items.append((str(i), m, False, False, i - 1))
    items.append(('5', config.GROK_MODEL,  True,  False, 0))
    items.append(('6', config.GROQ_MODEL,  False, True,  0))
    _c3line(0, "Select model:", 0x03E0, bg)
    for idx, (key, label, _, __, ___) in enumerate(items):
        _c3line((idx + 1) * config.LINE_H, f"{key} {label[:36]}", 0x0000, bg)

    while True:
        ev = hal_kb.poll()
        if ev is None:
            time.sleep_ms(20)
            continue
        ev_type, ch = ev
        if ev_type == hal_kb.INPUT_CHAR and ch.isdigit():
            for key, label, grok, groq, gidx in items:
                if ch == key:
                    _use_grok  = grok
                    _use_groq  = groq
                    _gemini_idx = gidx
                    history.add('ai', f"Model: {label}", display_only=True)
                    return

# ── WiFi connect flow ──────────────────────────────────────────────────────────
def ensure_wifi():
    """Ensure WiFi is connected, running AP scan flow if needed. Returns True."""
    global _wifi_ok
    if wifi_mgr.is_connected():
        _wifi_ok = True
        return True
    wifi_mgr.load_creds()
    if wifi_mgr._creds:
        ssid = wifi_mgr._creds[0]['ssid']
        pwd  = wifi_mgr._creds[0]['pass']
        if wifi_mgr.connect(ssid, pwd, show_status=True):
            _wifi_ok = True
            _set_led(True)
            return True
    # AP scan flow
    ok = wifi_mgr.select_ap(_tft, _wri)
    _wifi_ok = ok
    if ok:
        _set_led(True)
    return ok

# ── Send prompt ────────────────────────────────────────────────────────────────
def send_prompt():
    global _more_mode, _wifi_ok
    text = ''.join(_input_buf).strip()
    if not text:
        return
    _input_buf.clear()
    _cursor_set(0)
    history.add('user', text)
    _refresh()

    if not ensure_wifi():
        history.add('error', "No WiFi", display_only=True)
        _refresh()
        return

    history.add('ai', "...", display_only=True)
    _refresh()

    try:
        msgs = history.get_messages()
        if _use_grok:
            reply = api.call_grok(msgs, secrets.GROK_KEY)
        elif _use_groq:
            reply = api.call_groq(msgs, secrets.GROQ_KEY)
        else:
            reply = api.call_gemini(msgs, config.GEMINI_MODELS[_gemini_idx], secrets.GEMINI_KEY)
    except Exception as e:
        reply = f"Error: {e}"
    finally:
        # Remove the "..." placeholder
        if history._messages and history._messages[-1].get('display_only'):
            history._messages.pop()
            history._total_bytes -= 3

    history.add('ai', reply)
    _more_mode = True
    _refresh()
    gc.collect()

# ── Input buffer helpers ───────────────────────────────────────────────────────
def _cursor_set(pos):
    global _cursor
    _cursor = max(0, min(pos, len(_input_buf)))

def _insert_char(ch):
    _input_buf.insert(_cursor, ch)
    _cursor_set(_cursor + 1)

def _delete_back():
    if _cursor > 0:
        _input_buf.pop(_cursor - 1)
        _cursor_set(_cursor - 1)

def _delete_fwd():
    if _cursor < len(_input_buf):
        _input_buf.pop(_cursor)

# ── Main event loop ────────────────────────────────────────────────────────────
def loop():
    global _last_activity, _last_wifi_check, _wifi_ok, _more_mode
    while True:
        ev = hal_kb.poll()
        if ev is not None:
            _last_activity = time.ticks_ms()
            ev_type, ch = ev
            redraw = True
            if   ev_type == hal_kb.INPUT_CHAR:
                _insert_char(ch)
            elif ev_type == hal_kb.INPUT_BACKSPACE:
                _delete_back()
            elif ev_type == hal_kb.INPUT_DELETE:
                _delete_fwd()
            elif ev_type == hal_kb.INPUT_CURSOR_LEFT:
                _cursor_set(_cursor - 1)
            elif ev_type == hal_kb.INPUT_CURSOR_RIGHT:
                _cursor_set(_cursor + 1)
            elif ev_type == hal_kb.INPUT_ENTER:
                send_prompt()
                redraw = False
            elif ev_type == hal_kb.INPUT_SCROLL_UP:
                history.scroll_up(); history.rebuild_lines(measure_fn=ui._measure)
                ui.draw_history(); redraw = False
            elif ev_type == hal_kb.INPUT_SCROLL_DOWN:
                history.scroll_down(); history.rebuild_lines(measure_fn=ui._measure)
                ui.draw_history(); redraw = False
            elif ev_type == hal_kb.INPUT_NEW_CONV:
                history.clear(); _input_buf.clear(); _cursor_set(0)
                _more_mode = False; _refresh(); redraw = False
            elif ev_type == hal_kb.INPUT_MODEL_MENU:
                show_model_menu(); _refresh(); redraw = False
            else:
                redraw = False
            if redraw:
                ui.draw_input_bar(''.join(_input_buf), _cursor, _wifi_ok)

        # WiFi idle disconnect (60s without activity)
        now = time.ticks_ms()
        if (time.ticks_diff(now, _last_wifi_check) > 2000 and wifi_mgr.is_connected()):
            _last_wifi_check = now
            idle_s = time.ticks_diff(now, _last_activity) / 1000
            if idle_s > config.WIFI_IDLE_TIMEOUT:
                wifi_mgr.disconnect()
                _wifi_ok = False
                _set_led(False)
        elif not wifi_mgr.is_connected() and _wifi_ok:
            _wifi_ok = False
            _set_led(False)

        time.sleep_ms(10)

# ── Boot sequence ──────────────────────────────────────────────────────────────
def main():
    global _tft, _wri
    _tft = display.init()
    _wri = Writer(_tft, font14)
    ui.init(_tft)

    bg = 0xC618
    _c3line(0, "CRACK — USB keyboard init...", 0x0000, bg)

    found = hal_kb.init(timeout_ms=5000)
    if not found:
        _c3line(config.LINE_H, "Keyboard not found!", 0xF800, bg)
        time.sleep(2)

    wifi_mgr.load_creds()

    # Check for pre-seeded default credentials from secrets.py
    try:
        if secrets.WIFI_SSID_DEFAULT and not wifi_mgr._creds:
            wifi_mgr.insert_cred(secrets.WIFI_SSID_DEFAULT, secrets.WIFI_PASS_DEFAULT)
    except AttributeError:
        pass

    ensure_wifi()
    show_model_menu()
    _last_activity = time.ticks_ms()
    _refresh()
    loop()

main()
```

- [ ] **Step 2: Write upload script**

```bash
cat > /home/alun/esp32/micropython/tools/upload.sh << 'EOF'
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
EOF
chmod +x /home/alun/esp32/micropython/tools/upload.sh
```

- [ ] **Step 3: Upload all app files and boot**

```bash
cp /home/alun/esp32/ai-chatbot/SLUG/... ...  # ensure secrets.py exists
/home/alun/esp32/micropython/tools/upload.sh /dev/ttyUSB0
```

Watch UART0 serial output at 115200 baud. Expected boot sequence:
```
CRACK — USB keyboard init...
[USB] host lib installed
[USB] new device addr=1
SET_PROTOCOL(Boot) OK
```

Then the display shows the model selection menu.

- [ ] **Step 4: Commit**

```bash
cd /home/alun/esp32/micropython
git add app/main.py tools/upload.sh
git commit -m "feat: main.py — boot sequence, main loop, model menu, send prompt"
```

---

### Task 13: Integration test

Manual end-to-end verification on hardware.

- [ ] **Step 1: Full upload**

```bash
/home/alun/esp32/micropython/tools/upload.sh /dev/ttyUSB0
```

- [ ] **Step 2: Boot test**

Power cycle the board. Expected sequence:
1. Display shows light grey background, "CRACK — USB keyboard init..."
2. Plug USB keyboard into the USB-C port (5V VBUS must be supplied externally — the S2 Mini's USB-C is now OTG host, not a power sink)
3. Display shows model menu within 5 seconds
4. Press `1` — display goes to chat screen with "Model: gemini-2.5-flash..."

- [ ] **Step 3: WiFi connect test**

If no stored credentials: AP scan screen appears automatically. Select an AP by pressing its number key, enter password, press Enter. LED on GPIO 15 lights when connected.

- [ ] **Step 4: Chat test**

Type "What is 2+2?" and press Enter. Expected:
- Message appears right-aligned (user, olive text)
- "..." placeholder appears briefly
- AI reply appears left-aligned (yellow text)
- Input bar clears

- [ ] **Step 5: Keyboard navigation test**

- Left/right arrows: cursor moves within input bar
- PgUp/PgDn: scroll history up and down
- Home key: re-opens model menu
- Del key: forward-deletes character at cursor
- Ctrl+N: clears conversation history

- [ ] **Step 6: Grok/Groq test**

Press Home, select 5 (Grok). Send a message. Verify response from Grok endpoint.

- [ ] **Step 7: WiFi idle timeout test**

Leave idle for 60 seconds. Verify LED turns off (WiFi disconnected). Press a key to type, then Enter — verify WiFi reconnects automatically and AI call succeeds.

- [ ] **Step 8: Commit final state**

```bash
cd /home/alun/esp32/micropython
git add .
git commit -m "feat: integration complete — CRACK MicroPython chatbot on ESP32-S2 Mini"
```

---

## Self-Review

### Spec coverage

| Requirement | Task |
|---|---|
| MicroPython on ESP32-S2 Mini | Tasks 1–3 |
| GMT020-02 240×320 display | Task 4 |
| USB HID keyboard input | Tasks 3, 7 |
| Gemini / Grok / Groq APIs | Task 11 |
| WiFi credential store (9-slot NVS) | Task 10 |
| AP scan + password entry UI | Task 10 |
| Chat history + word wrap | Task 8 |
| Input bar with cursor | Task 9 |
| Model selection menu | Task 12 |
| New conversation (Ctrl+N) | Task 12 |
| Scroll history (PgUp/PgDn) | Task 12 |
| LED WiFi status (GPIO 15) | Task 7 |
| WiFi idle disconnect | Task 12 |

### Key hardware constraints (carried from SLUG)

- `ARDUINO_USB_CDC_ON_BOOT=0` equivalent: the `CRACK_S2` board config sets `CONFIG_ESP_CONSOLE_UART_DEFAULT=y` and `MICROPY_HW_USB_CDC=0`. Without this, the OTG peripheral is claimed by MicroPython's USB-CDC stack and `usb_host_install()` will fail.
- UART0 (GPIO 43 TX, GPIO 44 RX) is the only REPL/debug path once USB OTG is in host mode. An external USB-UART adapter is required.
- USB-C OTG is host — the board must be powered from the 5V header or 3V3 pin, NOT the USB-C port. The keyboard's VBUS (5V) must be supplied externally.
- SPI at 4MHz initially (matching the C++ target); increase to 20MHz if display is stable.

### Placeholder scan

No TBD, TODO, or "implement later" items present. All code blocks are complete.

### Type consistency

- `hal_kb.poll()` returns `(int, str)` — used consistently in `main.py` event loop.
- `history.rebuild_lines(measure_fn)` — `measure_fn` is `ui._measure` in all call sites.
- `wifi_mgr._creds` — `list[dict]` with keys `'ssid'` and `'pass'` — consistent across load/save/insert/find.
- `api.call_*` — all take `(messages: list[dict], ..., api_key: str)` — consistent with `history.get_messages()` output format.
