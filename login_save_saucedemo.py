# scripts/login_save_saucedemo.py
from playwright.sync_api import sync_playwright
import os, json, sys, time

SITE_URL = "https://www.saucedemo.com/"
INVENTORY_URL_SUFFIX = "/inventory.html"
STATE_PATH = "/app/storage/saucedemo.storage.json"

USER = os.environ.get("SAUCE_USER", "standard_user")
PWD  = os.environ.get("SAUCE_PWD",  "secret_sauce")

def main():
    p = sync_playwright().start()
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context()  # new clean context
    page = ctx.new_page()

    page.goto(SITE_URL, wait_until="domcontentloaded")
    page.fill("#user-name", USER)
    page.fill("#password", PWD)
    page.click("#login-button")

    # Confirm login by waiting for the inventory page
    page.wait_for_url(f"**{INVENTORY_URL_SUFFIX}", timeout=20000)
    page.wait_for_load_state("networkidle")

    # Save storage after login (captures localStorage for this origin)
    ctx.storage_state(path=STATE_PATH)

    # Print a tiny summary so you can verify
    data = json.load(open(STATE_PATH, "r"))
    origins = data.get("origins", [])
    ls_items = sum(len(o.get("localStorage", [])) for o in origins)
    print("saved_to:", STATE_PATH)
    print("cookies:", len(data.get("cookies", [])))
    print("origins:", len(origins))
    print("localStorage_items:", ls_items)

    browser.close()
    p.stop()

if __name__ == "__main__":
    main()
