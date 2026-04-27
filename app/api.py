# app/api.py
import socket, ssl, json, config

def _https_post(host, path, headers, body_dict):
    """POST body_dict as JSON to https://host/path. Returns response body string."""
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
    req_lines += ["", ""]
    req = "\r\n".join(req_lines).encode() + body_bytes

    addr = socket.getaddrinfo(host, config.HTTPS_PORT)[0][-1]
    s = socket.socket()
    s.settimeout(config.API_TIMEOUT_MS / 1000)
    s.connect(addr)
    s = ssl.wrap_socket(s, server_hostname=host)
    s.write(req)

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

    sep = raw.find(b"\r\n\r\n")
    if sep < 0:
        raise ValueError("No HTTP header separator")
    status_line = raw[:raw.find(b"\r\n")].decode()
    if " 200 " not in status_line:
        raise ValueError(f"HTTP error: {status_line[:80]}")
    body = raw[sep + 4:]
    header_block = raw[:sep].decode().lower()
    if "transfer-encoding: chunked" in header_block:
        body = _unchunk(body)
    return body.decode('utf-8', 'replace')

def _unchunk(data):
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
    body = _build_openai_body(messages, config.GROK_MODEL)
    resp = _https_post(config.GROK_HOST, "/v1/chat/completions",
                       {"Authorization": f"Bearer {api_key}"}, body)
    data = json.loads(resp)
    return data["choices"][0]["message"]["content"].strip()

def call_groq(messages, api_key):
    body = _build_openai_body(messages, config.GROQ_MODEL)
    resp = _https_post(config.GROQ_HOST, "/openai/v1/chat/completions",
                       {"Authorization": f"Bearer {api_key}"}, body)
    data = json.loads(resp)
    return data["choices"][0]["message"]["content"].strip()
