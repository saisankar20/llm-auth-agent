# signup_login_form.py
import time, secrets, string
from pathlib import Path
from typing import Dict, Tuple
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

STORAGE_DIR = Path("/app/storage")
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

def _gen_username() -> str:
    ts = int(time.time())
    return f"llmuser{ts}"

def _gen_email() -> str:
    # Use mailinator to avoid real inbox; the app doesn't verify email.
    ts = int(time.time())
    return f"llm{ts}@mailinator.com"

def _gen_password() -> str:
    return secrets.token_urlsafe(12)

def generate_creds() -> Tuple[str, str, str]:
    """return (email, username, password)"""
    return _gen_email(), _gen_username(), _gen_password()

def signup_with_form(conf: Dict, email: str, username: str, password: str) -> Dict:
    s = conf["signup"]
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context()
        page = ctx.new_page()

        page.goto(s["url"], wait_until="networkidle", timeout=60_000)

        page.get_by_placeholder(s["fields"]["username_placeholder"]).fill(username)
        page.get_by_placeholder(s["fields"]["email_placeholder"]).fill(email)
        page.get_by_placeholder(s["fields"]["password_placeholder"]).fill(password)
        page.get_by_role("button", name=s.get("submit_text", "Sign up")).click()

        # SPA can take a second to route
        try:
            if s.get("success_url_contains"):
                page.wait_for_url(f"**{s['success_url_contains']}**", timeout=15_000)
        except PWTimeout:
            # Fallback: settle network and continue
            page.wait_for_load_state("networkidle", timeout=10_000)

        # keep a post-signup storage snapshot (debug)
        debug_path = STORAGE_DIR / f"{conf['site_id']}_post_signup.storage.json"
        ctx.storage_state(path=str(debug_path))
        cookies = len(ctx.cookies())
        b.close()
        return {"ok": True, "cookies": cookies, "storage_state_path": str(debug_path)}

def login_with_form(conf: Dict, email: str, password: str, site_id: str) -> Dict:
    import json
    from playwright.sync_api import sync_playwright

    l = conf["login"]
    final_path = STORAGE_DIR / f"{site_id}.storage.json"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()

        # Open login page and fill form
        page.goto(l["url"], wait_until="networkidle", timeout=60_000)
        page.get_by_placeholder(l["fields"]["email_placeholder"]).fill(email)
        page.get_by_placeholder(l["fields"]["password_placeholder"]).fill(password)

        # Click Sign in
        page.get_by_role("button", name=l.get("submit_text", "Sign in")).click()

        # Grab JWT from the /users/login network response
        token = None
        try:
            resp = page.wait_for_response(
                lambda r: "users/login" in r.url and r.request.method == "POST" and r.status == 200,
                timeout=30_000,
            )
            try:
                data = resp.json()
                token = (data.get("user") or {}).get("token")
            except Exception:
                token = None
        except Exception:
            token = None

        # Fallback: ask the page if it already put the jwt in localStorage
        if not token:
            try:
                token = page.evaluate("() => window.localStorage.getItem('jwt')")
            except Exception:
                token = None

        # If we got a token, persist it in localStorage for this origin
        if token:
            page.evaluate("(t) => window.localStorage.setItem('jwt', t)", token)

        # Let SPA settle
        page.wait_for_load_state("networkidle", timeout=30_000)

        # Get storage state
        state = ctx.storage_state()

        # Ensure the jwt is present in origins/localStorage in the saved file
        origin_host = "https://demo.realworld.io"
        if token:
            found_origin = False
            for o in state.get("origins", []):
                if o.get("origin") == origin_host:
                    found_origin = True
                    ls = [item for item in o.get("localStorage", []) if item.get("name") != "jwt"]
                    ls.append({"name": "jwt", "value": token})
                    o["localStorage"] = ls
                    break
            if not found_origin:
                state.setdefault("origins", []).append({
                    "origin": origin_host,
                    "localStorage": [{"name": "jwt", "value": token}],
                })

        # Persist to disk (overwrites existing)
        final_path.write_text(json.dumps(state, ensure_ascii=False))

        cookie_count = len(state.get("cookies", []))
        origin_count = len(state.get("origins", []))

        browser.close()

    return {
        "ok": True,
        "cookies": cookie_count,
        "origins": origin_count,
        "storage_state_path": str(final_path),
        "token_present": bool(token),
    }
