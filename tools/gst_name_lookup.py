"""Human-assisted GST taxpayer name lookup through the official GST Portal.

The portal CAPTCHA is shown to the user and must be entered by them. No CAPTCHA
solving or private credentials are used by this module.
"""
from __future__ import annotations

import os
import tempfile
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

from tools import gstr2b_backend

LOOKUP_URL = "https://services.gst.gov.in/services/searchtp"
LOOKUP_SESSION_TTL_SECONDS = 20 * 60
_sessions: dict[str, dict] = {}


def _expire_sessions() -> None:
    now = time.time()
    for key, state in list(_sessions.items()):
        if now - state.get("created_at", now) > LOOKUP_SESSION_TTL_SECONDS:
            close_lookup(key)


def _wait_for_challenge(browser, timeout: int = 15) -> None:
    """Wait for the portal CAPTCHA area to finish appearing after GSTIN entry."""
    WebDriverWait(browser, timeout).until(
        lambda d: any(
            element.is_displayed()
            for element in d.find_elements(
                By.XPATH,
                "//input[not(@type='hidden') and (contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'characters') or contains(translate(@aria-label,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'captcha') or contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'captcha') or contains(translate(@name,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'captcha'))]",
            )
        )
    )
    time.sleep(0.4)


def _captcha_field(browser):
    candidates = browser.find_elements(By.CSS_SELECTOR, "input")
    for item in candidates:
        if not item.is_displayed() or not item.is_enabled():
            continue
        identity = " ".join(
            (item.get_attribute(key) or "")
            for key in ("id", "name", "placeholder", "aria-label", "class")
        ).lower()
        if item.get_attribute("type") == "hidden":
            continue
        if item.get_attribute("id") == "for_gstin":
            continue
        if any(token in identity for token in ("captcha", "characters shown", "characters you see")):
            return item
    visible_text = [
        item for item in candidates
        if item.is_displayed()
        and item.is_enabled()
        and (item.get_attribute("type") or "text").lower() in ("text", "search")
        and item.get_attribute("id") != "for_gstin"
    ]
    return visible_text[0] if len(visible_text) == 1 else None


def _extract_names(browser) -> tuple[str, str]:
    """Read the labeled Legal Name and Trade Name fields from the result page."""
    values = browser.execute_script("""
        const clean = value => (value || '').replace(/\\s+/g, ' ').trim().toLowerCase();
        const labels = ['legal name of business', 'trade name'];
        const out = {};
        for (const labelText of labels) {
          const matches = [...document.querySelectorAll('th,td,label,b,strong,span,div')]
            .filter(el => clean(el.innerText || el.textContent) === labelText)
            .sort((a, b) => a.children.length - b.children.length);
          const label = matches[0];
          if (!label) continue;
          let node = label;
          for (let depth = 0; depth < 5 && node && node.parentElement; depth++, node = node.parentElement) {
            const parent = node.parentElement;
            const parentText = clean(parent.innerText || parent.textContent);
            if (labels.some(other => other !== labelText && parentText.includes(other))) continue;
            const children = [...parent.children];
            const labelIndex = children.findIndex(child => child === node || child.contains(node));
            const candidates = [];
            if (node.nextElementSibling) candidates.push(node.nextElementSibling);
            if (labelIndex >= 0) candidates.push(...children.slice(labelIndex + 1));
            const value = candidates
              .map(el => (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim())
              .find(text => text && !labels.some(other => clean(text) === other)
                && !['effective date of registration', 'constitution of business'].some(other => clean(text).startsWith(other)));
            if (value) { out[labelText] = value; break; }
          }
        }
        return out;
    """)
    legal = str(values.get("legal name of business", "")).strip()
    trade = str(values.get("trade name", "")).strip()

    # Responsive layouts can expose headings and values as consecutive body lines.
    lines = [line.strip() for line in browser.find_element(By.TAG_NAME, "body").text.splitlines() if line.strip()]
    headings = {"legal name of business", "trade name", "effective date of registration"}
    lowered = [line.lower().rstrip(":") for line in lines]
    def value_after(label):
        try:
            index = lowered.index(label) + 1
        except ValueError:
            return ""
        while index < len(lines) and lowered[index] in headings:
            index += 1
        return lines[index] if index < len(lines) else ""
    legal = legal or value_after("legal name of business")
    trade = trade or value_after("trade name")
    return legal, trade

def start_lookup(session_id: str, gstin: str) -> bytes:
    """Open taxpayer search, enter GSTIN, and return the visible CAPTCHA screenshot."""
    _expire_sessions()
    close_lookup(session_id)
    download_dir = tempfile.mkdtemp(prefix="gst_name_lookup_")
    browser = gstr2b_backend._new_driver(download_dir)
    try:
        browser.set_page_load_timeout(45)
        browser.get(LOOKUP_URL)
        field = WebDriverWait(browser, 25).until(
            lambda d: d.find_element(By.ID, "for_gstin")
        )
        field.clear()
        field.send_keys(str(gstin).strip().upper())
        # Leaving the GSTIN field triggers the portal CAPTCHA; do not press
        # SEARCH until the user has entered the challenge in the app.
        field.send_keys(Keys.TAB)
        _wait_for_challenge(browser)
        _sessions[session_id] = {
            "driver": browser,
            "download_dir": download_dir,
            "gstin": str(gstin).strip().upper(),
            "created_at": time.time(),
        }
        return browser.get_screenshot_as_png()
    except Exception:
        browser.quit()
        import shutil
        shutil.rmtree(download_dir, ignore_errors=True)
        raise


def refresh_lookup(session_id: str) -> bytes:
    """Refresh the CAPTCHA while keeping the entered GSTIN."""
    _expire_sessions()
    state = _sessions[session_id]
    state["created_at"] = time.time()
    browser = state["driver"]
    clicked = browser.execute_script("""
        const visible = el => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
        const candidates = [...document.querySelectorAll('button,a,[role=button],input[type=button]')].filter(visible);
        const button = candidates.find(el => /refresh|reload|captcha/i.test(
          (el.innerText || '') + ' ' + (el.title || '') + ' ' +
          (el.getAttribute('aria-label') || '') + ' ' + (el.className || '') + ' ' + (el.innerHTML || '')
        ));
        if (button) { button.click(); return true; }
        return false;
    """)
    if not clicked:
        field = browser.find_element(By.ID, "for_gstin")
        field.clear()
        field.send_keys(state["gstin"])
        browser.find_element(By.ID, "lotsearch").click()
    _wait_for_challenge(browser)
    return browser.get_screenshot_as_png()


def submit_captcha(session_id: str, code: str) -> tuple[str | None, bytes, str]:
    """Submit the user's CAPTCHA and return the portal's preferred business name."""
    _expire_sessions()
    state = _sessions[session_id]
    state["created_at"] = time.time()
    browser = state["driver"]
    field = _captcha_field(browser)
    if field is None:
        return None, browser.get_screenshot_as_png(), "Could not locate the CAPTCHA field. Refresh it and try again."
    field.clear()
    field.send_keys(code.strip())
    browser.find_element(By.ID, "lotsearch").click()

    end = time.time() + 25
    while time.time() < end:
        body = browser.find_element(By.TAG_NAME, "body").text
        lower = body.lower()
        if "legal name of business" in lower or "trade name" in lower:
            legal, trade = _extract_names(browser)
            if legal:
                chosen = trade if trade and trade.lower() not in ("na", "n/a", "not available", "-") else legal
                return chosen, browser.get_screenshot_as_png(), f"GST Portal name found: {chosen}"
        if any(message in lower for message in ("invalid captcha", "incorrect captcha", "captcha is invalid", "enter valid captcha")):
            _wait_for_challenge(browser)
            return None, browser.get_screenshot_as_png(), "CAPTCHA was not accepted. Enter the refreshed CAPTCHA."
        time.sleep(0.5)
    return None, browser.get_screenshot_as_png(), "The portal did not return a name in time. Refresh the CAPTCHA and try again."


def close_lookup(session_id: str | None) -> None:
    if not session_id:
        return
    state = _sessions.pop(session_id, None)
    if not state:
        return
    try:
        state["driver"].quit()
    except Exception:
        pass
    try:
        import shutil
        shutil.rmtree(state["download_dir"], ignore_errors=True)
    except Exception:
        pass
