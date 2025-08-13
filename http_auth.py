import requests

def _ptr(doc, pointer):
    cur = doc
    for p in [p for p in pointer.split("/") if p]:
        cur = cur[p]
    return cur

def _fill(payload, secrets):
    # recursively replace "{{key}}" -> secrets[key]
    if isinstance(payload, dict):
        return {k: _fill(v, secrets) for k, v in payload.items()}
    if isinstance(payload, list):
        return [_fill(v, secrets) for v in payload]
    if isinstance(payload, str) and payload.startswith("{{") and payload.endswith("}}"):
        key = payload[2:-2]
        return secrets.get(key, payload)
    return payload

def login_and_get_token(conf):
    login = conf["auth"]["login"]
    payload = _fill(login["payload"], conf["auth"].get("secrets", {}))
    r = requests.request(login.get("method","POST"), login["url"], json=payload, timeout=20)
    if r.status_code >= 400:
        raise requests.HTTPError(f"{r.status_code} {r.reason} body: {r.text[:400]}", response=r)
    body = r.json()
    token = _ptr(body, login.get("token_json_pointer","/accessToken"))
    return {"kind":"bearer","token": token}