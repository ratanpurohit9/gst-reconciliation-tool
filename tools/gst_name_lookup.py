"""Human-assisted GST taxpayer name lookup through the official GST Portal.

The portal CAPTCHA is shown to the user and must be entered by them. No CAPTCHA
solving or private credentials are used by this module.
"""
from __future__ import annotations

import os
import re
import tempfile
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import ElementClickInterceptedException, ElementNotInteractableException
from selenium.webdriver.support.ui import WebDriverWait

from tools import gstr2b_backend

LOOKUP_URL = "https://services.gst.gov.in/services/searchtp"
AUTH_LOOKUP_URL = "https://services.gst.gov.in/services/auth/searchtp"
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


def _captcha_image_screenshot(browser) -> bytes:
    """Return only the CAPTCHA graphic, never a full-page portal screenshot."""
    field = _captcha_field(browser)
    if field is None:
        raise RuntimeError("The CAPTCHA entry field is not visible; refresh the challenge.")

    field_y = field.location.get("y", 0)
    candidates = []
    for element in browser.find_elements(By.CSS_SELECTOR, "img, canvas"):
        if not element.is_displayed():
            continue
        identity = " ".join(
            (element.get_attribute(key) or "")
            for key in ("id", "alt", "title", "src", "class")
        ).lower()
        size = element.size or {}
        width, height = size.get("width", 0), size.get("height", 0)
        if width < 70 or height < 18 or width > 700 or height > 180:
            continue
        distance = abs(element.location.get("y", 0) - field_y)
        if "captcha" in identity:
            candidates.append((0, distance, element))
        elif distance <= 180:
            candidates.append((1, distance, element))
    if not candidates:
        raise RuntimeError("Could not isolate the CAPTCHA image, so the portal page was not shown.")
    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[0][2].screenshot_as_png


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
        const clean = value => (value || '').replace(/\s+/g, ' ').trim().toLowerCase();
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
              .map(el => (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim())
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
    if legal and trade and trade.casefold() == legal.casefold():
        trade = ""
    return legal, trade

def open_taxpayer_search(browser) -> None:
    """Open the authenticated Search Taxpayer > Search by GSTIN/UIN page."""
    browser.set_page_load_timeout(35)
    current_url = (browser.current_url or "").lower()
    if "/services/auth/searchtp" in current_url:
        fields = browser.find_elements(By.ID, "for_gstin")
        if any(field.is_displayed() for field in fields):
            return

    # Prefer the same visible navigation path used by the GST Portal UI.
    menu_items = browser.find_elements(
        By.XPATH,
        "//*[self::a or self::button or @role='button'][contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'search taxpayer')]",
    )
    menu = next((item for item in menu_items if item.is_displayed()), None)
    if menu is not None:
        try:
            from selenium.webdriver import ActionChains
            ActionChains(browser).move_to_element(menu).perform()
        except Exception:
            pass
        try:
            menu.click()
        except Exception:
            browser.execute_script("arguments[0].click();", menu)

        option = None
        deadline = time.time() + 8
        while time.time() < deadline and option is None:
            options = browser.find_elements(
                By.XPATH,
                "//a[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'search by gstin/uin')]",
            )
            option = next((item for item in options if item.is_displayed()), None)
            if option is None:
                time.sleep(0.2)
        if option is not None:
            try:
                option.click()
            except Exception:
                browser.execute_script("arguments[0].click();", option)
            WebDriverWait(browser, 20).until(
                lambda d: any(field.is_displayed() for field in d.find_elements(By.ID, "for_gstin"))
            )
            return

    # A direct URL is a fallback when the portal changes its menu markup.
    browser.get(AUTH_LOOKUP_URL)
    WebDriverWait(browser, 20).until(
        lambda d: any(field.is_displayed() for field in d.find_elements(By.ID, "for_gstin"))
    )


def lookup_authenticated_name(browser, gstin: str) -> str:
    """Fetch one taxpayer name using an already authenticated GST Portal browser."""
    requested_gstin = str(gstin).strip().upper()
    if not re.fullmatch(r"[0-9A-Z]{15}", requested_gstin):
        raise ValueError("GSTIN must contain 15 letters and digits.")

    browser.set_page_load_timeout(35)
    open_taxpayer_search(browser)
    field = WebDriverWait(browser, 20).until(lambda d: d.find_element(By.ID, "for_gstin"))
    if not field.is_displayed() or not field.is_enabled():
        raise RuntimeError("GST Portal taxpayer search is not available in this session.")
    field.clear()
    field.send_keys(requested_gstin)
    search_button = WebDriverWait(browser, 12).until(
        lambda d: next(
            (button for button in d.find_elements(By.ID, "lotsearch")
             if button.is_displayed() and button.is_enabled()),
            False,
        )
    )
    browser.execute_script(
        "arguments[0].scrollIntoView({block:'center', inline:'center'});",
        search_button,
    )
    try:
        search_button.click()
    except (ElementClickInterceptedException, ElementNotInteractableException):
        # The authenticated portal can leave a loading overlay above the form.
        # Use the button's own DOM click handler as a fallback after scrolling.
        time.sleep(0.6)
        browser.execute_script("arguments[0].click();", search_button)

    deadline = time.time() + 22
    while time.time() < deadline:
        body = browser.find_element(By.TAG_NAME, "body").text
        header = re.search(
            r"Search\s+Result\s+based\s+on\s+GSTIN/UIN\s*:\s*([A-Z0-9]{15})",
            body,
            flags=re.IGNORECASE,
        )
        if header and header.group(1).upper() == requested_gstin:
            legal, trade = _extract_names(browser)
            chosen = trade if trade and trade.lower() not in ("na", "n/a", "not available", "-") else legal
            if chosen:
                return chosen
            raise RuntimeError("The GST Portal returned the GSTIN but no legal or trade name.")
        current_url = (browser.current_url or "").lower()
        if "/services/searchtp" in current_url and "/services/auth/searchtp" not in current_url:
            raise RuntimeError("GST Portal login has expired. Close this session and use the CAPTCHA lookup.")
        time.sleep(0.3)
    raise RuntimeError("GST Portal did not return a result for this GSTIN in time.")


def start_lookup(session_id: str, gstin: str) -> bytes:
    """Show the CAPTCHA for a GSTIN, reusing the user's browser session when possible."""
    _expire_sessions()
    state = _sessions.get(session_id)
    if state:
        browser = state["driver"]
        download_dir = state["download_dir"]
    else:
        download_dir = tempfile.mkdtemp(prefix="gst_name_lookup_")
        browser = gstr2b_backend._new_driver(download_dir)
        state = {"driver": browser, "download_dir": download_dir}
        _sessions[session_id] = state

    try:
        browser.set_page_load_timeout(45)
        browser.get(LOOKUP_URL)
        field = WebDriverWait(browser, 25).until(
            lambda d: d.find_element(By.ID, "for_gstin")
        )
        field.clear()
        requested_gstin = str(gstin).strip().upper()
        field.send_keys(requested_gstin)
        # Leaving the GSTIN field triggers the CAPTCHA. SEARCH is reserved for
        # the user's CAPTCHA submission.
        field.send_keys(Keys.TAB)
        _wait_for_challenge(browser)
        state.update(gstin=requested_gstin, created_at=time.time())
        return _captcha_image_screenshot(browser)
    except Exception:
        close_lookup(session_id)
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
    return _captcha_image_screenshot(browser)


def submit_captcha(session_id: str, code: str) -> tuple[str | None, bytes, str]:
    """Submit the user's CAPTCHA and return the portal's preferred business name."""
    _expire_sessions()
    state = _sessions[session_id]
    state["created_at"] = time.time()
    browser = state["driver"]
    field = _captcha_field(browser)
    if field is None:
        return None, _captcha_image_screenshot(browser), "Could not locate the CAPTCHA field. Refresh it and try again."
    field.clear()
    field.send_keys(code.strip())
    browser.find_element(By.ID, "lotsearch").click()

    end = time.time() + 25
    while time.time() < end:
        body = browser.find_element(By.TAG_NAME, "body").text
        lower = body.lower()
        result_match = re.search(
            r"Search\s+Result\s+based\s+on\s+GSTIN/UIN\s*:\s*([A-Z0-9]{15})",
            body,
            flags=re.IGNORECASE,
        )
        # Require the portal result header to match this lookup's GSTIN. This
        # prevents a previous result from being assigned to the next row.
        if result_match and result_match.group(1).upper() == state["gstin"]:
            legal, trade = _extract_names(browser)
            if legal:
                chosen = trade if trade and trade.lower() not in ("na", "n/a", "not available", "-") else legal
                return chosen, b"", f"GST Portal name found: {chosen}"
        if any(message in lower for message in ("invalid captcha", "incorrect captcha", "captcha is invalid", "enter valid captcha")):
            _wait_for_challenge(browser)
            return None, _captcha_image_screenshot(browser), "CAPTCHA was not accepted. Enter the refreshed CAPTCHA."
        time.sleep(0.5)
    return None, _captcha_image_screenshot(browser), "The portal did not return a name in time. Refresh the CAPTCHA and try again."


def lookup_authenticated_names(browser, gstins: list[str], progress=None) -> tuple[dict[str, str], dict[str, str]]:
    """Look up several taxpayer names sequentially in one authenticated portal session."""
    requested = list(dict.fromkeys(str(gstin).strip().upper() for gstin in gstins if str(gstin).strip()))
    found: dict[str, str] = {}
    errors: dict[str, str] = {}
    total = len(requested)
    for index, gstin in enumerate(requested, 1):
        if progress:
            progress(index - 1, total, gstin, "searching")
        try:
            found[gstin] = lookup_authenticated_name(browser, gstin)
            outcome = "found"
        except Exception as exc:
            detail = str(exc).split("Stacktrace:")[0].strip()
            errors[gstin] = f"{type(exc).__name__}: {detail[:180]}" if detail else type(exc).__name__
            outcome = "failed"
        if progress:
            progress(index, total, gstin, outcome)
        # Keep the portal request sequence gentle and avoid parallel requests.
        if index < total:
            time.sleep(0.35)
    return found, errors


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
