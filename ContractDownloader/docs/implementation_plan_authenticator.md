# Implementation Plan – Authenticator Module

> **Substituído (2026-08-12):** Não implementar este plano histórico. A versão oficial 1.0.0 está descrita em [`authentication-architecture.md`](authentication-architecture.md): `SecureSessionStore`, perfil corporativo existente do Edge, captura explícita e crawler Direct HTTP. `src/engine/authenticator.py` permanece apenas como facade de compatibilidade.

## Goal
Create `src/engine/authenticator.py` that handles temporary Edge Selenium login, extracts session cookies, and returns them for the async HTTP engine.

## Design Overview
- Use `selenium.webdriver.Edge` with `options.add_argument('--headless')`.
- Open Coupa login page, wait for user to authenticate (manual). Detect successful login by URL change or presence of a specific DOM element.
- Capture all cookies via `driver.get_cookies()` and convert to a dict suitable for `httpx.CookieJar`.
- Close the driver immediately after extraction.
- Export a function `async def get_coupa_cookies() -> dict` that internally runs Selenium in a thread (to avoid blocking the async loop).
- Include robust error handling and a timeout.

## Implementation Steps
1. Add required imports (`selenium`, `asyncio`, `concurrent.futures`).
2. Define `def _run_selenium()` that launches the driver, waits for login, returns cookies.
3. Wrap with `async def get_coupa_cookies()` using `run_in_executor`.
4. Provide a small CLI entry point for manual testing.
5. Add type hints and docstrings.

## Verification Plan
- **Unit Test**: Mock Selenium driver to return a preset cookie list and assert `get_coupa_cookies` returns the correct dict.
- **Integration Test**: Run the function (requires Edge installed) and verify cookies are usable with `httpx` to make an authenticated request to a known endpoint.
- **Manual Test**: Run `python -m src.engine.authenticator` and ensure UI prompts for login and prints extracted cookies.

---
*Prepared by Antigravity – please review and approve.*
