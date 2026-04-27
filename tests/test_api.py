# tests/test_api.py
import sys, os, types
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'app'))

for m in ['socket', 'ssl']:
    sys.modules[m] = types.ModuleType(m)

cfg = types.ModuleType('config')
cfg.API_TIMEOUT_MS = 25000; cfg.HTTPS_PORT = 443
cfg.GEMINI_HOST = "generativelanguage.googleapis.com"
cfg.GROK_HOST = "api.x.ai"; cfg.GROQ_HOST = "api.groq.com"
cfg.SYSTEM_PROMPT = "Be brief."
cfg.GROK_MODEL = "grok-3-fast-beta"; cfg.GROQ_MODEL = "qwen/qwen3-32b"
sys.modules['config'] = cfg

import api

def test_gemini_body():
    msgs = [{'role': 'user', 'text': 'Hello'}]
    body = api._build_gemini_body(msgs, "gemini-2.0-flash")
    assert body['contents'][0]['role'] == 'user'
    assert body['contents'][0]['parts'][0]['text'] == 'Hello'
    assert 'system_instruction' in body
    assert body['generationConfig']['maxOutputTokens'] == 300
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

def test_ai_role_mapping():
    msgs = [{'role': 'ai', 'text': 'Response'}]
    body = api._build_gemini_body(msgs, "m")
    assert body['contents'][0]['role'] == 'model'
    body2 = api._build_openai_body(msgs, "m")
    assert body2['messages'][1]['role'] == 'assistant'
    print("PASS test_ai_role_mapping")

test_gemini_body()
test_openai_body()
test_unchunk()
test_ai_role_mapping()
print("All api tests passed.")
