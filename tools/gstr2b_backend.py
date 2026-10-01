"""Server-side GST portal GSTR-2B download flow for the Streamlit app.

The portal CAPTCHA/OTP remains user-entered. Browser sessions live only in the
current app process and are never persisted to disk.
"""
from __future__ import annotations

import os
import tempfile
import time
import uuid
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from tools import gstr2b_downloader as core

_sessions: dict[str, dict] = {}


def _wait_for_captcha_render(browser, timeout: float = 12) -> None:
    """Wait briefly for the GST Portal's asynchronous CAPTCHA image to render."""
    end = time.time() + timeout
    while time.time() < end:
        try:
            ready = browser.execute_script("""
                const imgs = [...document.images];
                const captcha = imgs.find(i => /captcha/i.test((i.id || '') + ' ' + (i.alt || '') + ' ' + (i.src || '')));
                const loading = document.body.innerText.toLowerCase().includes('loading captcha');
                return captcha ? (captcha.complete && captcha.naturalWidth > 0) : !loading;
            """)
            if ready:
                return
        except Exception:
            return
        time.sleep(0.4)


def _new_driver(download_dir: str):
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1440,1100")
    options.add_experimental_option("prefs", {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    })
    chrome = os.getenv("CHROME_BIN")
    driver = os.getenv("CHROMEDRIVER")
    if chrome:
        options.binary_location = chrome
    if driver and Path(driver).exists():
        from selenium.webdriver.chrome.service import Service
        browser = webdriver.Chrome(service=Service(driver), options=options)
    else:
        browser = webdriver.Chrome(options=options)
    # Headless Chrome on the hosted server needs an explicit download policy;
    # prefs alone can leave portal-generated files blocked or undetected.
    browser.execute_cdp_cmd("Page.setDownloadBehavior", {
        "behavior": "allow",
        "downloadPath": os.path.abspath(download_dir),
    })
    return browser


def start_login(session_id: str, username: str, password: str) -> bytes:
    """Start an ephemeral browser session, fill credentials, return portal screenshot."""
    close_session(session_id)
    download_dir = tempfile.mkdtemp(prefix="gst2b_")
    browser = _new_driver(download_dir)
    try:
        browser.set_page_load_timeout(45)
        browser.get(core.GST_LOGIN_URL)
        WebDriverWait(browser, 30).until(
            lambda d: d.find_elements(By.CSS_SELECTOR, "input[type='password']")
        )
        time.sleep(1)
        user_box, password_box = core.gst_login_boxes(browser)
        if not user_box or not password_box:
            raise RuntimeError("GST Portal login fields were not found.")
        user_box.clear()
        user_box.send_keys(username.strip())
        password_box.clear()
        password_box.send_keys(password)
        _sessions[session_id] = {
            "driver": browser,
            "download_dir": download_dir,
            "username": username.strip(),
            "password": password,
        }
        _wait_for_captcha_render(browser)
        return browser.get_screenshot_as_png()
    except Exception:
        browser.quit()
        raise


def screenshot(session_id: str) -> bytes:
    return _sessions[session_id]["driver"].get_screenshot_as_png()


def refresh_captcha(session_id: str) -> bytes:
    """Click the portal's refresh control; reload and refill credentials as fallback."""
    state = _sessions[session_id]
    browser = state["driver"]
    clicked = browser.execute_script("""
        const visible = e => !!(e && (e.offsetWidth || e.offsetHeight || e.getClientRects().length));
        const buttons = [...document.querySelectorAll('button,a,[role=button],input[type=button]')].filter(visible);
        let b = buttons.find(e => /refresh|reload|new captcha/i.test((e.innerText || '') + ' ' + (e.title || '') + ' ' + (e.getAttribute('aria-label') || '') + ' ' + (e.className || '') + ' ' + (e.innerHTML || '')));
        if (!b) {
            const field = [...document.querySelectorAll('input')].find(e => /captcha/i.test((e.id || '') + ' ' + (e.name || '') + ' ' + (e.placeholder || '')));
            let p = field;
            for (let i = 0; p && i < 4; i++, p = p.parentElement) {
                const nearby = [...p.querySelectorAll('button,[role=button],input[type=button]')].filter(visible);
                if (nearby.length) { b = nearby[nearby.length - 1]; break; }
            }
        }
        if (b) { b.click(); return true; }
        return false;
    """)
    if not clicked:
        browser.get(core.GST_LOGIN_URL)
        WebDriverWait(browser, 30).until(
            lambda d: d.find_elements(By.CSS_SELECTOR, "input[type='password']")
        )
    time.sleep(1)
    user_box, password_box = core.gst_login_boxes(browser)
    if user_box and not (user_box.get_attribute("value") or ""):
        user_box.send_keys(state["username"])
    if password_box and not (password_box.get_attribute("value") or ""):
        password_box.send_keys(state["password"])
    _wait_for_captcha_render(browser)
    return browser.get_screenshot_as_png()


def submit_portal_code(session_id: str, code: str) -> tuple[bool, bytes, str]:
    """Submit the currently visible CAPTCHA/OTP and report whether login completed."""
    browser = _sessions[session_id]["driver"]
    candidates = browser.find_elements(By.CSS_SELECTOR, "input")
    field = None
    for item in candidates:
        if not item.is_displayed() or not item.is_enabled():
            continue
        identity = " ".join((item.get_attribute(k) or "") for k in ("id", "name", "placeholder", "aria-label")).lower()
        if any(word in identity for word in ("captcha", "otp", "verification", "security")):
            field = item
            break
    if field is None:
        # GST login templates sometimes omit useful field identifiers. Use the
        # first visible, enabled text input other than username/password.
        for item in candidates:
            if item.is_displayed() and item.is_enabled() and (item.get_attribute("type") or "text").lower() not in ("password", "hidden"):
                identity = " ".join((item.get_attribute(k) or "") for k in ("id", "name", "placeholder")).lower()
                if "user" not in identity:
                    field = item
                    break
    if field is None:
        return False, browser.get_screenshot_as_png(), "Could not find a visible CAPTCHA/OTP field. Refresh the challenge and try again."
    field.clear()
    field.send_keys(code.strip())
    buttons = browser.find_elements(By.XPATH, "//button|//input[@type='submit']|//a[@role='button']")
    for button in buttons:
        label = " ".join((button.text or "", button.get_attribute("value") or "", button.get_attribute("aria-label") or "")).lower()
        if button.is_displayed() and button.is_enabled() and any(x in label for x in ("login", "sign in", "submit", "verify", "continue")):
            button.click()
            break
    else:
        field.submit()
    time.sleep(3)
    url = browser.current_url.lower()
    body = browser.find_element(By.TAG_NAME, "body").text.lower()
    logged_in = "/returns/auth/" in url or "logout" in body or "return dashboard" in body
    note = "GST Portal login succeeded." if logged_in else "Code was not accepted or another challenge is required. Password was refilled; enter the refreshed code below."
    if not logged_in:
        user_box, password_box = core.gst_login_boxes(browser)
        if user_box and not (user_box.get_attribute("value") or ""):
            user_box.send_keys(_sessions[session_id]["username"])
        if password_box and not (password_box.get_attribute("value") or ""):
            password_box.send_keys(_sessions[session_id]["password"])
        _wait_for_captcha_render(browser)
    return logged_in, browser.get_screenshot_as_png(), note


def download_periods(session_id: str, months: list[tuple[str, str]], quarterly: bool = False, progress=None) -> tuple[bytes, str]:
    """Download selected periods using existing parser/converter, return merged XLSX bytes."""
    state = _sessions[session_id]
    browser, download_dir = state["driver"], state["download_dir"]
    periods = list(months)
    if quarterly:
        periods, _, _, _ = core.resolve_quarterly_periods(periods)
    converted: list[str] = []
    errors: list[str] = []
    for index, (month, year) in enumerate(periods, 1):
        if progress:
            progress(f"Period {index}/{len(periods)} — opening {month} {year} on GST Portal…")
        try:
            status, info = core.gst_download_gstr2b_json(browser, month, year, download_dir, is_quarterly=quarterly)
        except Exception as exc:
            errors.append(f"{month} {year}: portal request failed: {str(exc)[:180]}")
            break
        if status != "downloaded":
            errors.append(f"{month} {year}: {info}")
            continue
        path = os.path.join(download_dir, info)
        converted_path = os.path.join(download_dir, f"{year}-{core.MONTHS.index(month)+1:02d}.xlsx")
        if progress:
            progress(f"Period {index}/{len(periods)} — converting {month} {year}…")
        core.convert_and_save_period_excel(path, converted_path, period_label=f"{month[:3]}-{year}", quarterly=quarterly)
        converted.append(converted_path)
    if not converted:
        raise RuntimeError("No GSTR-2B workbook was produced. " + "; ".join(errors))
    output = os.path.join(download_dir, "merged.xlsx")
    if progress:
        progress("Merging downloaded periods into one Excel workbook…")
    core.merge_all_gstr2b_periods(converted, output)
    with open(output, "rb") as handle:
        data = handle.read()
    description = f"Prepared {len(converted)} period(s)."
    if errors:
        description += " Some periods were skipped: " + "; ".join(errors)
    return data, description


def close_session(session_id: str) -> None:
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

