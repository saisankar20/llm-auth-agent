import time, requests, asyncio
from db import record_telemetry, latest_token

def call_authed(site_id, url, auth_kind="bearer"):
    t = asyncio.run(latest_token(site_id))
    if not t:
        raise RuntimeError(f"No token for {site_id}")

    headers, jar = {}, None
    if auth_kind == "bearer" and t.get("token"):
        headers["Authorization"] = f"Bearer {t['token']}"
    if auth_kind == "cookie":
        jar = requests.cookies.RequestsCookieJar()
        for k, v in (t.get("cookies") or {}).items():
            jar.set(k, v)

    t0 = time.perf_counter()
    r = requests.get(url, headers=headers, cookies=jar, timeout=25)
    ms = (time.perf_counter() - t0) * 1000.0
    r.raise_for_status()
    try:
        asyncio.run(record_telemetry(site_id, url, r.status_code, ms))
    except Exception:
        pass
    return {"status": r.status_code, "latency_ms": round(ms, 2)}
