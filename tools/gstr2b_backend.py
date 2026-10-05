"""Server-side GST portal GSTR-2B download flow for the Streamlit app.

The portal CAPTCHA/OTP remains user-entered. Browser sessions live only in the
current app process and are never persisted to disk.
"""
from __future__ import annotations

import os
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
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
        time.sleep(0.1)


_FAST_PICK_JS = """
    const vis = e => !!(e && (e.offsetWidth || e.offsetHeight || e.getClientRects().length));
    const imgs = [...document.querySelectorAll('img, canvas')].filter(vis);
    const ident = e => ((e.id || '') + ' ' + (e.alt || '') + ' ' + (e.title || '') + ' ' + (e.className || '') + ' ' + ((e.src || '').slice(0, 200))).toLowerCase();
    const ok = e => { const r = e.getBoundingClientRect(); return r.width >= 60 && r.height >= 16 && r.width <= 900 && r.height <= 220; };
    const hit = imgs.find(e => ok(e) && ident(e).includes('captcha') && (e.tagName !== 'IMG' || (e.complete && e.naturalWidth > 0)));
    if (hit) hit.scrollIntoView({block: 'center'});
    return hit || null;
"""


def _challenge_preview(browser) -> bytes:
    """Return only the visible GST Portal CAPTCHA graphic, never the full login page."""
    try:
        element = browser.execute_script(_FAST_PICK_JS)
        if element is not None:
            png = element.screenshot_as_png
            if png:
                return png
    except Exception:
        pass
    return _slow_challenge_preview(browser)


def _slow_challenge_preview(browser) -> bytes:
    field_y = None
    for item in browser.find_elements(By.CSS_SELECTOR, "input"):
        if not item.is_displayed() or not item.is_enabled():
            continue
        identity = " ".join(
            (item.get_attribute(key) or "")
            for key in ("id", "name", "placeholder", "aria-label", "class")
        ).lower()
        if any(token in identity for token in ("captcha", "verification", "security", "characters")):
            field_y = item.location.get("y", 0)
            break

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
        if width < 60 or height < 16 or width > 900 or height > 220:
            continue
        if element.tag_name.lower() == "img":
            try:
                if not element.get_attribute("complete") and not element.get_attribute("src"):
                    continue
            except Exception:
                pass
        distance = abs(element.location.get("y", 0) - field_y) if field_y is not None else 9999
        if "captcha" in identity:
            candidates.append((0, distance, element))
        elif field_y is not None and distance <= 240:
            candidates.append((1, distance, element))
    if not candidates:
        return b""
    candidates.sort(key=lambda item: (item[0], item[1]))
    try:
        return candidates[0][2].screenshot_as_png
    except Exception:
        return b""


_CHROME_PATHS = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.join(os.getenv("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
)


def _driver_candidates() -> list[str]:
    """chromedriver locations to try, most specific first."""
    here = Path(__file__).resolve().parent
    found = []
    env = os.getenv("CHROMEDRIVER")
    if env:
        found.append(env)
    for folder in (here, here.parent, Path.cwd(), Path(r"C:\chromedriver")):
        for name in ("chromedriver.exe", "chromedriver"):
            found.append(str(folder / name))
    return [x for x in found if Path(x).is_file()]


def _new_driver(download_dir: str):
    def make_options():
        options = webdriver.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1440,1100")
        # Do not wait for every portal asset (images/ads/trackers) on each navigation.
        options.page_load_strategy = "eager"
        options.add_experimental_option("prefs", {
            "download.default_directory": download_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
        })
        chrome = os.getenv("CHROME_BIN") or next((x for x in _CHROME_PATHS if x and Path(x).is_file()), None)
        if chrome:
            options.binary_location = chrome
        return options

    from selenium.webdriver.chrome.service import Service

    errors = []
    browser = None
    # 1) a chromedriver we can see (CHROMEDRIVER env, next to the app, C:\chromedriver)
    for path in _driver_candidates():
        try:
            browser = webdriver.Chrome(service=Service(path), options=make_options())
            break
        except Exception as exc:
            errors.append(f"{path}: {str(exc)[:160]}")
    # 2) Selenium Manager (auto-download)
    if browser is None:
        try:
            browser = webdriver.Chrome(options=make_options())
        except Exception as exc:
            errors.append(f"Selenium Manager: {str(exc)[:160]}")
    # 3) webdriver-manager, if installed
    if browser is None:
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            browser = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=make_options())
        except Exception as exc:
            errors.append(f"webdriver-manager: {str(exc)[:160]}")
    if browser is None:
        raise RuntimeError(
            "Could not start Chrome. Download the chromedriver that matches your Chrome version "
            "(chrome://version) and put chromedriver.exe in the tools folder, or set CHROMEDRIVER. "
            "Tried: " + " | ".join(errors))
    # Headless Chrome on the hosted server needs an explicit download policy;
    # prefs alone can leave portal-generated files blocked or undetected.
    browser.execute_cdp_cmd("Page.setDownloadBehavior", {
        "behavior": "allow",
        "downloadPath": os.path.abspath(download_dir),
    })
    return browser


# ---- pre-warmed login browser ------------------------------------------------------------
# Chrome start-up + portal page load + CAPTCHA fetch take several seconds. While the user is
# still typing credentials we do that work in the background, so "Start secure portal session"
# only has to fill the form and grab the already-rendered CAPTCHA.
_warm: dict = {"driver": None, "dir": None, "ts": 0.0, "thread": None}
_warm_lock = threading.Lock()
_WARM_MAX_AGE = 120  # seconds; older pages are reloaded so the CAPTCHA is fresh


def _warm_worker() -> None:
    download_dir = tempfile.mkdtemp(prefix="gst2b_")
    browser = None
    try:
        browser = _new_driver(download_dir)
        browser.set_page_load_timeout(45)
        browser.get(core.GST_LOGIN_URL)
        WebDriverWait(browser, 30).until(
            lambda d: d.find_elements(By.CSS_SELECTOR, "input[type='password']")
        )
        _wait_for_captcha_render(browser)
        with _warm_lock:
            _warm.update(driver=browser, dir=download_dir, ts=time.time())
    except Exception:
        try:
            if browser:
                browser.quit()
        except Exception:
            pass
        import shutil
        shutil.rmtree(download_dir, ignore_errors=True)


def prewarm() -> None:
    """Idempotent: start one background login browser if none is ready or being prepared."""
    with _warm_lock:
        if _warm["driver"] is not None:
            return
        t = _warm["thread"]
        if t is not None and t.is_alive():
            return
        _warm["thread"] = threading.Thread(target=_warm_worker, daemon=True)
        _warm["thread"].start()


def _take_warm(wait: float = 20.0):
    """Hand over the pre-warmed browser (waiting briefly if it is still starting), else None."""
    t = _warm["thread"]
    if _warm["driver"] is None and t is not None and t.is_alive():
        t.join(wait)
    with _warm_lock:
        browser, download_dir, ts = _warm["driver"], _warm["dir"], _warm["ts"]
        _warm.update(driver=None, dir=None, ts=0.0)
    if browser is None:
        return None, None
    try:
        browser.current_url  # raises if Chrome died
        if time.time() - ts > _WARM_MAX_AGE:
            browser.get(core.GST_LOGIN_URL)
            WebDriverWait(browser, 30).until(
                lambda d: d.find_elements(By.CSS_SELECTOR, "input[type='password']")
            )
        return browser, download_dir
    except Exception:
        try:
            browser.quit()
        except Exception:
            pass
        return None, None


def start_login(session_id: str, username: str, password: str) -> bytes:
    """Start an ephemeral browser session, fill credentials, return the isolated CAPTCHA image."""
    close_session(session_id)
    browser, download_dir = _take_warm()
    if browser is None:
        download_dir = tempfile.mkdtemp(prefix="gst2b_")
        browser = _new_driver(download_dir)
    try:
        browser.set_page_load_timeout(45)
        if browser.current_url.rstrip("/") != core.GST_LOGIN_URL.rstrip("/"):
            browser.get(core.GST_LOGIN_URL)
        WebDriverWait(browser, 30).until(
            lambda d: d.find_elements(By.CSS_SELECTOR, "input[type='password']")
        )
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
        return _challenge_preview(browser)
    except Exception:
        browser.quit()
        raise


def screenshot(session_id: str) -> bytes:
    return _challenge_preview(_sessions[session_id]["driver"])


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
    return _challenge_preview(browser)


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
        return False, _challenge_preview(browser), "Could not find a visible CAPTCHA/OTP field. Refresh the challenge and try again."
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
    return logged_in, b"" if logged_in else _challenge_preview(browser), note


def failed_periods(session_id: str) -> list[tuple[str, str, str]]:
    """(month, year, reason) for every period that failed in the last run and has not succeeded since."""
    state = _sessions.get(session_id) or {}
    return [(m, y, why) for (m, y), why in (state.get("failed") or {}).items()]


def retry_failed(session_id: str, quarterly: bool = False, progress=None) -> tuple[bytes, str]:
    """Re-run only the periods that failed, then re-merge them with the ones that already succeeded."""
    state = _sessions[session_id]
    failed = list((state.get("failed") or {}).keys())
    if not failed:
        raise RuntimeError("There are no failed periods to retry.")
    return download_periods(session_id, state.get("req_months") or failed, quarterly=quarterly,
                            progress=progress, only=failed)


def download_periods(session_id: str, months: list[tuple[str, str]], quarterly: bool = False, progress=None,
                     only: list[tuple[str, str]] | None = None) -> tuple[bytes, str]:
    """Download each selected period, convert in the background, merge in memory.

    Fast route (the portal's own requests, replayed from the offline page) is tried first; any period
    it cannot serve is retried through the click-through route. Failed periods are remembered in the
    session so `retry_failed` can re-run just those. `only` limits this run to those periods while the
    merged workbook still includes every period that succeeded earlier in the session.
    """
    state = _sessions[session_id]
    browser, download_dir = state["driver"], state["download_dir"]
    periods = [(m, str(y)) for m, y in months]
    if quarterly:
        periods = [(m, str(y)) for m, y in core.resolve_quarterly_periods(periods)[0]]
    if only is None:                               # fresh full run
        state["files"], state["failed"] = {}, {}
        state["req_months"] = list(months)
    files: dict = state.setdefault("files", {})
    failed: dict = state.setdefault("failed", {})
    targets = [pr for pr in periods if only is None or pr in {(m, str(y)) for m, y in only}]

    errors: list[str] = []
    total = len(targets)
    timings = {"download": 0.0, "convert_wait": 0.0, "merge": 0.0}
    fast_ok, fast_fails, fast_used, ui_used = True, 0, 0, 0

    # One worker: conversion (CPU) overlaps with portal waiting (I/O). Progress is only ever
    # reported from this thread because Streamlit UI calls are not thread-safe.
    pool = ThreadPoolExecutor(max_workers=1)
    jobs: dict = {}                                # (month, year) -> future

    def fail(key, reason):
        failed[key] = reason
        errors.append(f"{key[0]} {key[1]}: {reason}")

    t_dl = time.perf_counter()
    for index, (month, year) in enumerate(targets, 1):
        key = (month, year)

        def cb(pct, message, month=month, year=year, index=index):
            if progress:
                progress(pct, f"{month} {year} ({index}/{total}) — {message}")

        if progress:
            progress(0, f"Downloading {month} {year} ({index}/{total})…")

        status, info = "fast_unavailable", ""
        try:
            if fast_ok:
                status, info = core.gst_download_gstr2b_json_fast(
                    browser, month, year, download_dir, is_quarterly=quarterly, progress_callback=cb)
                if status == "fast_unavailable":
                    fast_fails += 1
                    print(f"[GSTR-2B] fast route unavailable for {month} {year}: {info}")
                    if fast_fails >= 2:
                        fast_ok = False           # stop retrying direct route for this run
                else:
                    fast_fails = 0
                    fast_used += 1
            if status == "fast_unavailable":
                fast_info = info
                status, info = core.gst_download_gstr2b_json(
                    browser, month, year, download_dir, is_quarterly=quarterly, progress_callback=cb)
                ui_used += 1
                if status != "downloaded" and fast_info:
                    info = f"{info} [direct route: {str(fast_info)[:140]}]"
        except Exception as exc:
            fail(key, f"portal request failed: {str(exc)[:180]}")
            if progress:
                progress(100, f"{month} {year} ({index}/{total}) — failed; continuing to next period.")
            continue

        if status != "downloaded":
            fail(key, str(info))
            if progress:
                progress(100, f"{month} {year} ({index}/{total}) — {info}")
            continue

        failed.pop(key, None)
        files[key] = os.path.join(download_dir, info)
        jobs[key] = pool.submit(core.convert_period_to_workbook, files[key], quarterly)
        if progress:
            progress(100, f"Downloaded {month} {year} ({index}/{total}).")
    timings["download"] = time.perf_counter() - t_dl

    # Periods that succeeded in an earlier run are re-converted (the merge consumes its workbooks).
    for key in periods:
        if key in files and key not in jobs and os.path.isfile(files[key]):
            jobs[key] = pool.submit(core.convert_period_to_workbook, files[key], quarterly)

    if not jobs:
        pool.shutdown(wait=False)
        raise RuntimeError("No GSTR-2B files were downloaded. " + "; ".join(errors))

    t_cv = time.perf_counter()
    workbooks = []
    ordered = [k for k in periods if k in jobs]
    for n, key in enumerate(ordered, 1):
        month, year = key
        if progress:
            progress(int((n - 1) * 100 / len(ordered)), f"Converting — {month} {year} ({n}/{len(ordered)})…")
        try:
            workbooks.append(jobs[key].result())
        except Exception as exc:
            files.pop(key, None)
            fail(key, f"conversion failed: {str(exc)[:180]}")
        if progress:
            progress(int(n * 100 / len(ordered)), f"Converted {month} {year} ({n}/{len(ordered)}).")
    pool.shutdown(wait=True)
    timings["convert_wait"] = time.perf_counter() - t_cv
    if not workbooks:
        raise RuntimeError("Downloaded files could not be converted. " + "; ".join(errors))

    output = os.path.join(download_dir, "merged.xlsx")
    if progress:
        progress(0, "Merging converted periods into one Excel workbook…")
    t_mg = time.perf_counter()
    core.merge_period_workbooks(workbooks, output)
    timings["merge"] = time.perf_counter() - t_mg
    if progress:
        progress(100, "Merged workbook is ready.")
    with open(output, "rb") as handle:
        data = handle.read()

    print(f"[GSTR-2B timing] download={timings['download']:.1f}s convert_wait={timings['convert_wait']:.1f}s "
          f"merge={timings['merge']:.1f}s fast={fast_used} ui={ui_used}")
    description = (f"Prepared {len(workbooks)} period(s) "
                   f"(download {timings['download']:.0f}s, convert wait {timings['convert_wait']:.0f}s, "
                   f"merge {timings['merge']:.0f}s; direct {fast_used}, portal-UI {ui_used}).")
    if failed:
        description += (" Failed periods (use 'Retry failed months'): "
                        + "; ".join(f"{m} {y}: {why}" for (m, y), why in failed.items()))
    return data, description


def get_session_browser(session_id: str):
    """Return the live browser for an authenticated session, if it still exists."""
    state = _sessions.get(session_id)
    return state.get("driver") if state else None


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

