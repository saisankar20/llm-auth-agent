# tasks_signup_minimal.py
import json, time, random, asyncio
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from celery_app import app
from db import upsert_credentials

def _load(site_id: str):
    p = Path("site_configs") / f"{site_id}.json"
    if not p.exists():
        raise FileNotFoundError(f"Site config not found: {p}")
    return json.loads(p.read_text())

def _run_async(coro):
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(coro)

def _gen_creds(prefix="llmuser"):
    stamp = int(time.time())
    username = f"{prefix}{stamp}"
    password = f"{random.randint(10,99)}{random.choice('abcdef')}Secure!"
    email = f"llm{stamp}@mailinator.com"
    return username, password, email

@app.task(name="tasks.signup_only")
def signup_only(site_id: str):
    conf = _load(site_id)
    start_url = conf["start_url"]
    sconf = conf["signup"]

    username, password, email = _gen_creds()

    signup_ok = False
    dialog_text = None
    storage_path = conf.get("storage_state_path")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(start_url, wait_until="domcontentloaded")

        # Open signup UI
        if "open" in sconf:
            if sconf["open"].get("click"):
                page.click(sconf["open"]["click"])
            if sconf["open"].get("wait_for"):
                page.wait_for_selector(sconf["open"]["wait_for"], timeout=15000)

        # Fill fields
        f = sconf.get("fields", {})
        if f.get("username"):
            page.fill(f["username"], username)
        if f.get("email"):
            page.fill(f["email"], email)
        if f.get("password"):
            page.fill(f["password"], password)

        # Submit + capture dialog
        submit_sel = sconf["submit"]
        try:
            with page.expect_event("dialog", timeout=15000) as di:
                page.click(submit_sel)
            dlg = di.value
            dialog_text = (dlg.message or "").strip()
            try:
                dlg.accept()
            except Exception:
                pass

            msg = dialog_text.lower()
            if "successful" in msg:
                signup_ok = True
            elif "already exist" in msg:
                # Treat as ok so we can proceed to login
                signup_ok = True
            else:
                signup_ok = False
        except PWTimeout:
            # No dialog popped; optionally add other success checks here
            signup_ok = False

        # Optional: login and persist storage state
        if signup_ok and conf.get("login_after_signup") and "login" in conf:
            lconf = conf["login"]
            if "open" in lconf and lconf["open"].get("click"):
                page.click(lconf["open"]["click"])
            if "open" in lconf and lconf["open"].get("wait_for"):
                page.wait_for_selector(lconf["open"]["wait_for"], timeout=15000)

            lf = lconf.get("fields", {})
            if lf.get("username"):
                page.fill(lf["username"], username)
            if lf.get("email"):
                page.fill(lf["email"], email)
            if lf.get("password"):
                page.fill(lf["password"], password)
            page.click(lconf["submit"])

            # Wait for some logged-in signal
            if lconf.get("success_locator"):
                page.wait_for_selector(lconf["success_locator"], timeout=15000)

            if storage_path:
                Path(storage_path).parent.mkdir(parents=True, exist_ok=True)
                ctx.storage_state(path=storage_path)

        browser.close()

    # Save creds to DB only if we believe signup is ok (or existed)
    if signup_ok:
        _run_async(upsert_credentials(site_id, username, password))

    return {
        "saved": signup_ok,
        "site_id": site_id,
        "signup_ok": signup_ok,
        "username": username,
        "email": email,
        "dialog": dialog_text,
        "storage_path": storage_path if signup_ok and storage_path else None
    }
