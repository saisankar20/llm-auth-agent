# /app/captcha_solver.py
import os, time, requests

TWO_CAPTCHA_KEY = os.getenv("TWOCAPTCHA_API_KEY")

def _poll_2captcha(req_id: str):
    for _ in range(24):  # ~2 minutes
        time.sleep(5)
        r = requests.get(
            "http://2captcha.com/res.php",
            params={"key": TWO_CAPTCHA_KEY, "action": "get", "id": req_id, "json": 1},
            timeout=30,
        ).json()
        if r.get("status") == 1:
            return r["request"]
        if r.get("request") != "CAPCHA_NOT_READY":
            raise RuntimeError(f"2captcha error: {r}")
    raise TimeoutError("2captcha timed out")

def _start_job(data: dict):
    if not TWO_CAPTCHA_KEY:
        raise RuntimeError("Set TWOCAPTCHA_API_KEY in your environment")
    data = {**data, "key": TWO_CAPTCHA_KEY, "json": 1}
    r = requests.post("http://2captcha.com/in.php", data=data, timeout=30).json()
    if r.get("status") != 1:
        raise RuntimeError(f"2captcha in error: {r}")
    return r["request"]

def solve_recaptcha_v2(page, pageurl: str):
    # Try get sitekey from DOM or iframe URL
    sitekey = page.eval_on_selector('div.g-recaptcha', 'e => e?.getAttribute("data-sitekey")') \
          or page.eval_on_selector('iframe[src*="recaptcha"]', 'e => new URL(e.src).searchParams.get("k")')
    if not sitekey:
        return False, None
    req_id = _start_job({"method": "userrecaptcha", "googlekey": sitekey, "pageurl": pageurl})
    token = _poll_2captcha(req_id)
    page.evaluate("""(tok) => {
        let ta = document.getElementById('g-recaptcha-response');
        if(!ta){
          ta = document.createElement('textarea');
        ta.id = 'g-recaptcha-response';
        ta.name = 'g-recaptcha-response';
        ta.style.display = 'none';
        document.body.appendChild(ta);
        }
        ta.value = tok;
        ta.dispatchEvent(new Event('input', {bubbles:true}));
        ta.dispatchEvent(new Event('change', {bubbles:true}));
    }""", token)
    return True, token

def solve_hcaptcha(page, pageurl: str):
    sitekey = page.eval_on_selector('[data-sitekey]', 'e => e?.getAttribute("data-sitekey")')
    if not sitekey:
        return False, None
    req_id = _start_job({"method": "hcaptcha", "sitekey": sitekey, "pageurl": pageurl})
    token = _poll_2captcha(req_id)
    page.evaluate("""(tok) => {
        let ta = document.querySelector('textarea[name="h-captcha-response"]');
        if(!ta){
          ta = document.createElement('textarea');
          ta.name = 'h-captcha-response';
          ta.style.display = 'none';
          document.body.appendChild(ta);
        }
        ta.value = tok;
    }""", token)
    return True, token
