# tasks.py
import asyncio
import json
import os
from pathlib import Path

from celery_app import app
from db import upsert_credentials, insert_token
from probe import call_authed
from browser_auth_browser_use import login_with_browser_use

# ---------- helpers ----------

def _load(site_id: str) -> dict:
    """Load site config from site_configs/<site_id>.json"""
    p = Path("site_configs") / f"{site_id}.json"
    if not p.exists():
        raise FileNotFoundError(f"Site config not found: {p}")
    return json.loads(p.read_text())

def arun(coro):
    """Run an async coroutine from sync context (works inside Celery worker)."""
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(coro)

# ---------- tasks ----------

@app.task(name="tasks.ensure_access")
def ensure_access(site_id: str):
    """
    Ensure we can access a site by logging in with browser-use.
    Strategy:
      - If config has 'strategy' of 'browser_use' or 'llm_browser', we use browser-use.
      - If config has a 'start_url' (and no explicit strategy), default to browser-use.
    """
    conf = _load(site_id)
    strat = conf.get("strategy")
    if not strat:
        strat = "browser_use" if conf.get("start_url") else None

    if strat not in ("browser_use", "llm_browser"):
        raise ValueError(
            f"Site '{site_id}' must use browser_use/llm_browser (got: {strat!r}). "
            "Remove http_api paths – this worker only supports browser-use."
        )

    if "start_url" not in conf:
        raise ValueError(f"Site '{site_id}' uses browser auth but has no start_url")

    # Save credentials if present in config (so they exist for audits/rotation later)
    creds = conf.get("credentials", {}) or {}
    user = creds.get("username") or creds.get("email") or ""
    pwd = creds.get("password") or ""
    if user or pwd:
        arun(upsert_credentials(site_id, user, pwd))

    # Drive the browser to log in
    out = login_with_browser_use(conf["start_url"], user, pwd, site_id)
    storage_path = out["storage_state_path"]
    token_json = Path(storage_path).read_text()

    # Store storage_state JSON as a "token" row (kind=storage_state)
    arun(insert_token(site_id, "storage_state", token_json, None, None))

    return {
        "saved": True,
        "kind": "storage_state",
        "strategy": "browser_use",
        "cookies": out.get("cookies"),
        "path": storage_path,
    }

@app.task(name="tasks.call_all_probes")
def call_all_probes(site_id: str):
    """Call all probe_endpoints from the site config using bearer or cookie auth."""
    conf = _load(site_id)
    return [
        call_authed(site_id, ep["url"], ep.get("auth", "bearer"))
        for ep in conf.get("probe_endpoints", [])
    ]

# Optional: keep a dedicated name if you were queueing specifically on "auth"
@app.task(name="tasks.ensure_access_browser_use", queue="auth")
def ensure_access_browser_use(site_id: str):
    """Alias task that just calls ensure_access with browser-use flow."""
    return ensure_access(site_id)
