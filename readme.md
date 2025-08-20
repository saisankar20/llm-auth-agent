# LLM Auth Agent

This project uses a Large Language Model (LLM) to automate website logins and extract authentication tokens.

## Goal

The primary goal of this project is to programmatically log in to websites, even when the site's login form structure is unknown. It uses an LLM to analyze the HTML of a login page and identify the necessary input fields (username, password) and the submit button.

## How it works

The main logic is in the `browser_auth_llm.py` script. It uses the Playwright library to control a headless browser.

The process is as follows:
1.  Navigate to the login page.
2.  Extract the HTML of the page.
3.  Send the HTML to an LLM with a prompt asking it to identify the CSS selectors for the username, password, and submit button.
4.  Use the identified selectors to fill in the login form with the provided credentials.
5.  Submit the form.
6.  Wait for the page to load and extract the authentication cookies and any JWT tokens from local storage.

## Usage

To use the `login_with_llm` function in `browser_auth_llm.py`, you need to provide a starting URL and a dictionary of credentials.

Example:
```python
import asyncio
from browser_auth_llm import login_with_llm

async def main():
    credentials = {"username": "myuser", "password": "mypassword"}
    auth_info = await login_with_llm("https://example.com/login", credentials)
    print(auth_info)

if __name__ == "__main__":
    asyncio.run(main())
```

This will return a dictionary containing the type of authentication (`bearer` or `cookie`), the token (if found), and all the cookies.
