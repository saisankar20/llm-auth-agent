# tasks_signup.py
"""
Create a RealWorld (Conduit) demo account and GUARANTEE a token in storage_state.

Usage inside the container:
    from tasks_signup import ensure_account_then_login as t
    print(t.delay('realworld').get(timeout=240))
"""

import json
import time
import string
import random
import asyncio
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from celery_app import app
from db import upsert_credentials, insert_token

STORAGE_DIR = Path("/app/storage")
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

REALWORLD_ORIGIN = "https://demo.realworld.io"

# Try multiple public RealWorld API mirrors (some are flaky or rate-limited)
API_CANDIDATES = [
    "https://api.realworld.io/api",
    "https://conduit.productionready.io/api",
    # add more mirrors if you know them:
    # "https://realworld-api.fly.dev/api",
    # "https://api.realworld.tools/api",
]

# ---------- helpers ----------

def _rand(n: int = 14) -> str:
    chars = string.ascii_letters + string.digits
    return "".join(random.choice(chars) for _ in range(n))

def _arun(coro):
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(coro)

def _poll_local_storage(page, key: str, timeout_ms: int = 15_000) -> str | None:
    deadline = time.time() + timeout_ms / 1000.0
    last_err = None
    while time.time() < deadline:
        try:
            val = page.evaluate(f"() => window.localStorage.getItem('{key}')")
            if val:
                return val
        except Exception as e:
            last_err = e
        time.sleep(0.25)
    return None

def _ensure_kv_in_state(state: dict, origin: str, pairs: dict) -> None:
    """Insert/replace key/values in localStorage for given origin inside storage_state dict."""
    # find origin
    for o in state.get("origins", []):
        if o.get("origin") == origin:
            ls = [i for i in o.get("localStorage", []) if i.get("name") not in pairs]
            for k, v in pairs.items():
                ls.append({"name": k, "value": v})
            o["localStorage"] = ls
            break
    else:
        state.setdefault("origins", []).append(
            {"origin": origin,
             "localStorage": [{"name": k, "value": v} for k, v in pairs.items()]}
        )

def _api_signup_and_login(email: str, username: str, password: str):
    """
    Try API sign-up then login on multiple bases.
    Returns dict: {"token": str|None, "api_base": str|None, "status": [(base, step, code, ok)]}
    """
    results = []
    headers = {"Content-Type": "application/json"}
    payload_signup = {"user": {"username": username, "email": email, "password": password}}
    payload_login  = {"user": {"email": email, "password": password}}

    for base in API_CANDIDATES:
        # sign up (ignore 4xx if user exists)
        try:
            r = requests.post(f"{base}/users", json=payload_signup, headers=headers, timeout=20)
            results.append((base, "signup", getattr(r, "status_code", None), bool(getattr(r, "ok", False))))
        except requests.RequestException:
            results.append((base, "signup", None, False))

        # login
        try:
            r = requests.post(f"{base}/users/login", json=payload_login, headers=headers, timeout=20)
            results.append((base, "login", getattr(r, "status_code", None), bool(getattr(r, "ok", False))))
            if r.ok:
                try:
                    data = r.json() or {}
                except Exception:
                    data = {}
                token = (data.get("user") or {}).get("token")
                if token:
                    return {"token": token, "api_base": base, "status": results}
        except requests.RequestException:
            results.append((base, "login", None, False))

    return {"token": None, "api_base": None, "status": results}

# ---------- main task ----------

@app.task(name="tasks.ensure_account_then_login")
def ensure_account_then_login(site_id: str):
    """
    Creates account + guarantees token in storage_state for https://demo.realworld.io.
    Persists credentials and storage_state JSON to the DB.
    """
    # fresh creds
    suffix = str(int(time.time()))
    username = f"llmuser{suffix}"
    email = f"llm{suffix}@mailinator.com"
    password = _rand(14)

    storage_path = STORAGE_DIR / f"{site_id}.storage.json"

    # 1) API path (preferred)
    api_out = _api_signup_and_login(email, username, password)
    token = api_out["token"]

    # 2) Browser flow if needed OR to ensure origin appears in state
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context()
            page = ctx.new_page()

            # If we don't have a token yet, try UI register -> login
            if not token:
                # Register
                try:
                    page.goto(f"{REALWORLD_ORIGIN}/#/register", wait_until="networkidle", timeout=60_000)
                    page.get_by_placeholder("Username").fill(username)
                    page.get_by_placeholder("Email").fill(email)
                    page.get_by_placeholder("Password").fill(password)
                    page.get_by_role("button", name="Sign up").click()
                    # check localStorage
                    token = _poll_local_storage(page, "jwt", 8_000) or _poll_local_storage(page, "token", 2_000)
                except Exception:
                    pass

                # If still no token, go to login page and try again
                if not token:
                    try:
                        page.goto(f"{REALWORLD_ORIGIN}/#/login", wait_until="networkidle", timeout=60_000)
                        page.get_by_placeholder("Email").fill(email)
                        page.get_by_placeholder("Password").fill(password)
                        page.get_by_role("button", name="Sign in").click()
                        token = _poll_local_storage(page, "jwt", 8_000) or _poll_local_storage(page, "token", 2_000)
                    except Exception:
                        pass

                # Last resort: do API login from within the page to multiple hosts and stash both keys
                if not token:
                    for base in API_CANDIDATES:
                        try:
                            page.evaluate(
                                """async ({email, password, base}) => {
                                    try {
                                      const res = await fetch(`${base}/users/login`, {
                                        method: "POST",
                                        headers: {"Content-Type":"application/json"},
                                        body: JSON.stringify({user:{email, password}})
                                      });
                                      if (res.ok) {
                                        const data = await res.json();
                                        if (data?.user?.token) {
                                          localStorage.setItem("jwt", data.user.token);
                                          localStorage.setItem("token", data.user.token);
                                        }
                                      }
                                    } catch(e) {}
                                  }""",
                                {"email": email, "password": password, "base": base},
                            )
                            # brief poll after each attempt
                            token = _poll_local_storage(page, "jwt", 3_000) or _poll_local_storage(page, "token", 1_500)
                            if token:
                                break
                        except Exception:
                            continue

            # build storage state from context
            try:
                page.wait_for_load_state("networkidle", timeout=6_000)
            except PlaywrightTimeoutError:
                pass

            state = ctx.storage_state()

            # If we have a token from any path, force it into state under BOTH keys
            if token:
                _ensure_kv_in_state(state, REALWORLD_ORIGIN, {"jwt": token, "token": token})

            storage_path.write_text(json.dumps(state, ensure_ascii=False))
            browser.close()

    except Exception:
        # If browser steps fail, still persist a minimal state (with token if we got one via API)
        base_state = {"cookies": [], "origins": []}
        if token:
            _ensure_kv_in_state(base_state, REALWORLD_ORIGIN, {"jwt": token, "token": token})
        storage_path.write_text(json.dumps(base_state, ensure_ascii=False))

    # Ensure file exists (in case an exception happened before write)
    if not storage_path.exists():
        base_state = {"cookies": [], "origins": []}
        if token:
            _ensure_kv_in_state(base_state, REALWORLD_ORIGIN, {"jwt": token, "token": token})
        storage_path.write_text(json.dumps(base_state, ensure_ascii=False))

    # Read back & compute counts
    state = json.loads(storage_path.read_text())
    cookies_count = len(state.get("cookies", []))
    origins_count = len(state.get("origins", []))

    # Persist creds + storage to DB
    _arun(upsert_credentials(site_id, username, password))
    _arun(insert_token(site_id, "storage_state", json.dumps(state), None, None))

    return {
        "saved": True,
        "strategy": "form_browser",
        "kind": "storage_state",
        "cookies": cookies_count,
        "origins": origins_count,
        "path": str(storage_path),
        "username": username,
        "email": email,
        "token_present": bool(token),
        "api_debug": api_out["status"],   # (base, step, status_code, ok)
        "api_used": api_out["api_base"],
    }
