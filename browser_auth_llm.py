from typing import Dict
from playwright.async_api import async_playwright
from llm_agent import login_plan_from_html
import asyncio

async def login_with_llm(start_url: str, credentials: Dict[str, str]) -> dict:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # 1) Open page and let LLM plan the form interaction
        await page.goto(start_url, wait_until="domcontentloaded")
        html = await page.content()
        plan = login_plan_from_html(html, {"goal": "login", "start_url": start_url})
        sels = plan.get("selectors", {}) or {}

        # Known-good defaults for SauceDemo (demo site)
        if "saucedemo" in start_url:
            sels.setdefault("username", "#user-name")
            sels.setdefault("password", "#password")
            sels.setdefault("submit", "#login-button")
            plan.setdefault("success_signal", {"type": "url_contains", "value": "inventory"})

        # 2) Fill + submit
        if sels.get("username") and credentials.get("username"):
            await page.fill(sels["username"], credentials["username"])
        if sels.get("email") and credentials.get("email"):
            await page.fill(sels["email"], credentials["email"])
        if sels.get("password") and credentials.get("password"):
            await page.fill(sels["password"], credentials["password"])
        if sels.get("submit"):
            await page.click(sels["submit"])

        await page.wait_for_load_state("networkidle")

        # 3) Wait for "success"
        sig = plan.get("success_signal", {})
        if sig.get("type") == "url_contains" and sig.get("value"):
            await page.wait_for_url(f"**{sig['value']}**", timeout=20000)

        # 4) Harvest cookies + (optional) localStorage tokens
        cookies = {c["name"]: c.get("value") for c in await context.cookies()}
        ls = await page.evaluate(
            "Object.assign({}, ...['access_token','id_token','token'].map(k=>({[k]:localStorage.getItem(k)})))"
        )
        token = ls.get("access_token") or ls.get("id_token") or ls.get("token") or ""
        kind = "bearer" if token and ('.' in token or len(token) > 20) else "cookie"

        await context.close(); await browser.close()
        return {"kind": kind, "token": token or None, "cookies": cookies or {}}
