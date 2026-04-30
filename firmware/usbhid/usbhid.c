// firmware/usbhid/usbhid.c
// MicroPython C module: USB HID host keyboard for ESP32-S2.
// Ported from SLUG/src/hal_s2.cpp. Exposes:
//   usbhid.init()       -> None   (starts USB host tasks)
//   usbhid.poll()       -> None | (int, int)  (event_type, char_ord)
//   usbhid.connected()  -> bool

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
        else if (ctrl && code == 0x07) { type = EV_CHAR; ch = '\x04'; }  // Ctrl-D
        // ↑/PgUp = scroll to newer (down in history) — matches SLUG hal_s2.cpp convention
        else if (code == 0x52)         type = EV_SCROLL_DOWN;
        else if (code == 0x51)         type = EV_SCROLL_UP;
        else if (code == 0x4B)         type = EV_SCROLL_DOWN;  // PgUp
        else if (code == 0x4E)         type = EV_SCROLL_UP;    // PgDn
        else if (code == 0x4A)         type = EV_MODEL_MENU;
        else if (code == 0x4C)         type = EV_DELETE;
        else if (code == 0x39)         { s_caps_lock = !s_caps_lock; s_leds_dirty = true; continue; }
        else if (code == 0x50)         type = EV_CURSOR_LEFT;
        else if (code == 0x4F)         type = EV_CURSOR_RIGHT;
        else if (code == 0x28)         type = EV_ENTER;
        else if (code == 0x2A)         type = EV_BACKSPACE;
        else if (!ctrl) { char c = hid_to_ascii(code, shifted, s_caps_lock); if (c) { type = EV_CHAR; ch = c; } }
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

static SemaphoreHandle_t s_ctrl_done = NULL;
static SemaphoreHandle_t s_led_done  = NULL;

static void ctrl_cb(usb_transfer_t* t) {
    xSemaphoreGive((SemaphoreHandle_t)t->context);
}

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
    ctrl->callback = ctrl_cb;
    ctrl->context = (void*)s_ctrl_done;
    esp_err_t err = usb_host_transfer_submit_control(s_client, ctrl);
    if (err != ESP_OK) {
        usb_host_transfer_free(ctrl);
        return err;
    }
    BaseType_t got = xSemaphoreTake(s_ctrl_done, pdMS_TO_TICKS(1000));
    if (got != pdTRUE) {
        // Timeout: transfer still in-flight, cannot safely free — accept leak
        return ESP_ERR_TIMEOUT;
    }
    esp_err_t st = (ctrl->status == USB_TRANSFER_STATUS_COMPLETED) ? ESP_OK : ESP_FAIL;
    usb_host_transfer_free(ctrl);
    return st;
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
    ctrl_xfer(0x21, 0x0B, 0x0000, s_iface, 0, NULL);  // SET_PROTOCOL(Boot)
    ctrl_xfer(0x21, 0x0A, 0x0000, s_iface, 0, NULL);  // SET_IDLE(0)

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
    usb_transfer_t* ctrl = NULL;
    if (usb_host_transfer_alloc(9, 0, &ctrl) != ESP_OK) return;
    uint8_t leds = s_caps_lock ? 0x02 : 0x00;
    ctrl->data_buffer[0] = 0x21; ctrl->data_buffer[1] = 0x09;
    ctrl->data_buffer[2] = 0x00; ctrl->data_buffer[3] = 0x02;
    ctrl->data_buffer[4] = s_iface; ctrl->data_buffer[5] = 0x00;
    ctrl->data_buffer[6] = 0x01; ctrl->data_buffer[7] = 0x00;
    ctrl->data_buffer[8] = leds;
    ctrl->num_bytes = 9; ctrl->device_handle = s_dev;
    ctrl->bEndpointAddress = 0x00; ctrl->timeout_ms = 500;
    ctrl->callback = ctrl_cb;
    ctrl->context = (void*)s_led_done;
    if (usb_host_transfer_submit_control(s_client, ctrl) == ESP_OK)
        xSemaphoreTake(s_led_done, pdMS_TO_TICKS(500));
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
    if (rb_mutex) return mp_const_none;
    rb_mutex     = xSemaphoreCreateMutex();
    s_ctrl_done  = xSemaphoreCreateBinary();
    s_led_done   = xSemaphoreCreateBinary();
    xTaskCreate(usb_host_daemon_task, "usb_host",   4096, NULL, 5, NULL);
    xTaskCreate(usb_client_task,      "usb_client", 4096, NULL, 4, NULL);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(usbhid_init_obj, usbhid_init);

static mp_obj_t usbhid_poll(void) {
    if (!rb_mutex) return mp_const_none;
    xSemaphoreTake(rb_mutex, portMAX_DELAY);
    bool has = (rb_tail != rb_head);
    KbEvent ev = {0, 0};
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
    { MP_ROM_QSTR(MP_QSTR___name__),          MP_ROM_QSTR(MP_QSTR_usbhid) },
    { MP_ROM_QSTR(MP_QSTR_init),              MP_ROM_PTR(&usbhid_init_obj) },
    { MP_ROM_QSTR(MP_QSTR_poll),              MP_ROM_PTR(&usbhid_poll_obj) },
    { MP_ROM_QSTR(MP_QSTR_connected),         MP_ROM_PTR(&usbhid_connected_obj) },
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
