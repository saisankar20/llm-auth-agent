# /app/browser_auth_browser_use.py
import os, json, asyncio
from pathlib import Path
from urllib.parse import urlparse

from browser_use import Agent
from browser_use.browser import BrowserSession, BrowserProfile
from browser_use.llm import (
    ChatOpenAI, ChatAnthropic, ChatGoogle, ChatGroq,
    ChatAWSBedrock, ChatAzureOpenAI
)

def _make_llm():
    provider = (os.getenv("LLM_PROVIDER", "openai") or "openai").lower()
    # Sensible defaults per provider
    default_models = {
        "openai":    "gpt-4.1",                     # best perf (docs’ recommendation)
        "google":    "gemini-2.0-flash-exp",        # low cost + fast
        "anthropic": "claude-3-5-sonnet-20240620",
        "groq":      "meta-llama/llama-4-maverick-17b-128e-instruct",
        "azure":     "gpt-4.1",
        "bedrock":   "anthropic.claude-3-5-sonnet-20240620-v1:0",
    }
    model = os.getenv("LLM_MODEL", default_models.get(provider, "gpt-4.1"))

    if provider == "google":
        return ChatGoogle(model=model)              # needs GOOGLE_API_KEY
    if provider == "groq":
        return ChatGroq(model=model)                # needs GROQ_API_KEY
    if provider == "anthropic":
        return ChatAnthropic(model=model)           # needs ANTHROPIC_API_KEY
    if provider == "azure":
        return ChatAzureOpenAI(model=model)         # needs AZURE_* env vars
    if provider == "bedrock":
        return ChatAWSBedrock(model=model, aws_region=os.getenv("AWS_DEFAULT_REGION","us-east-1"))
    return ChatOpenAI(model=model)                  # needs OPENAI_API_KEY

async def _login_with_browser_use(start_url: str, username: str, password: str, site_id: str):
    # Save signed-in cookies/localStorage to a file the moment the context is created
    storage_dir = Path("/app/storage")
    storage_dir.mkdir(parents=True, exist_ok=True)
    storage_path = storage_dir / f"{site_id}.storage.json"

    # Lock navigation to this domain for safety
    parsed = urlparse(start_url)
    domain = f"https://{parsed.hostname}" if parsed.hostname else start_url

    session = BrowserSession(
        headless=True,
        user_data_dir=None,                         # use ephemeral context
        storage_state=str(storage_path),            # playwright storage_state JSON (cookies + localStorage)
        chromium_sandbox=False,                     # recommended inside Docker
        allowed_domains=[domain],                   # constrain agent’s navigation
        wait_for_network_idle_page_load_time=2.0,   # a bit more patience after login
    )

    task = (
        f"Open {start_url}. Log in using:\n"
        f"username: {username}\npassword: {password}\n"
        "After successful login, verify you’re signed in (e.g., a logout/account element). "
        "Do not change the password, do not sign up, then stop."
    )

    agent = Agent(task=task, llm=_make_llm(), browser_session=session)
    result = await agent.run(max_steps=30)          # keep it bounded

    # Ensure storage_state exists and return small summary
    if not storage_path.exists():
        raise RuntimeError("Login finished but no storage_state was written.")
    data = json.loads(storage_path.read_text())
    cookies = data.get("cookies", [])
    return {
        "ok": True,
        "storage_state_path": str(storage_path),
        "cookies": len(cookies),
        "notes": str(result)[:500],
    }

def login_with_browser_use(start_url: str, username: str, password: str, site_id: str):
    """Sync wrapper for Celery."""
    return asyncio.run(_login_with_browser_use(start_url, username, password, site_id))
