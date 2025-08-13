import os, json
from openai import OpenAI

_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

def login_plan_from_html(html: str, hints: dict) -> dict:
    """
    Ask an LLM to parse a login page and return selectors + a success signal.
    Returns a small JSON-ish dict. Falls back to sane defaults if parsing fails.
    """
    sys = (
        "You analyze a login page HTML and return ONLY compact JSON with:\n"
        "selectors: {username?, email?, password?, submit}\n"
        "use: \"username_password\" or \"email_password\"\n"
        "success_signal: {type: url_contains|dom_exists, value: string}\n"
        "token_sources: e.g. ['cookie:session','localStorage:access_token']\n"
        "No prose."
    )
    user = f"HINTS={json.dumps(hints)}\nHTML_START\n{html}\nHTML_END"

    res = _client.chat.completions.create(
        model=_MODEL,
        temperature=0,
        messages=[{"role":"system","content":sys},{"role":"user","content":user}],
    )
    txt = res.choices[0].message.content.strip()
    try:
        return json.loads(txt)
    except Exception:
        # In case the model responds with non-JSON
        return {
            "selectors": {},
            "use": "username_password",
            "success_signal": {"type": "url_contains", "value": "success"},
            "token_sources": ["cookie:session"],
        }
