# tests/test_wifi_mgr.py
import sys, os, types
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'app'))

class FakeNVS:
    _store = {}
    def __init__(self, ns): self.ns = ns
    def set_i32(self, k, v): FakeNVS._store[f"{self.ns}/{k}"] = v
    def get_i32(self, k): return FakeNVS._store.get(f"{self.ns}/{k}", 0)
    def set_blob(self, k, v): FakeNVS._store[f"{self.ns}/{k}"] = bytes(v)
    def get_blob(self, k, buf):
        data = FakeNVS._store.get(f"{self.ns}/{k}", b'')
        n = min(len(data), len(buf)); buf[:n] = data[:n]; return n
    def commit(self): pass

esp32_mod = types.ModuleType('esp32')
esp32_mod.NVS = FakeNVS
sys.modules['esp32'] = esp32_mod

net_mod = types.ModuleType('network')
net_mod.WLAN = lambda *a: types.SimpleNamespace(active=lambda *a: None, isconnected=lambda: False, disconnect=lambda: None, connect=lambda *a: None, scan=lambda: [])
net_mod.STA_IF = 1
sys.modules['network'] = net_mod

for m in ['ui', 'hal_kb']:
    sys.modules[m] = types.ModuleType(m)

cfg = types.ModuleType('config')
cfg.WIFI_MAX_ATTEMPTS = 2; cfg.WIFI_RETRY_DELAY = 0
cfg.LINE_H = 18; cfg.SCREEN_H = 240; cfg.COL_INVERT_BG = 0xC618
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

def test_mru_ordering():
    wifi_mgr._creds = []
    wifi_mgr.insert_cred('A', 'pa')
    wifi_mgr.insert_cred('B', 'pb')
    wifi_mgr.insert_cred('A', 'pa2')
    assert wifi_mgr._creds[0]['ssid'] == 'A'
    assert wifi_mgr._creds[0]['pass'] == 'pa2'
    assert wifi_mgr._creds[1]['ssid'] == 'B'
    print("PASS test_mru_ordering")

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
test_mru_ordering()
test_cap_at_9()
test_save_and_load()
print("All wifi_mgr tests passed.")
