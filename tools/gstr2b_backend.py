"""Backend GSTR-2B downloader; portal CAPTCHA/OTP is entered by the user."""
import os, shutil, tempfile, time
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from tools import gstr2b_downloader as core
_sessions={}
def _new_driver(folder):
    opts=webdriver.ChromeOptions()
    for a in ("--headless=new","--no-sandbox","--disable-dev-shm-usage","--disable-gpu","--window-size=1440,1100"): opts.add_argument(a)
    opts.add_experimental_option("prefs",{"download.default_directory":folder,"download.prompt_for_download":False,"download.directory_upgrade":True,"safebrowsing.enabled":True})
    if os.getenv("CHROME_BIN"): opts.binary_location=os.environ["CHROME_BIN"]
    driver=os.getenv("CHROMEDRIVER")
    if driver and Path(driver).exists():
        from selenium.webdriver.chrome.service import Service
        return webdriver.Chrome(service=Service(driver),options=opts)
    return webdriver.Chrome(options=opts)
def start_login(session_id,username,password):
    close_session(session_id); folder=tempfile.mkdtemp(prefix="gst2b_"); browser=_new_driver(folder)
    try:
        browser.get(core.GST_LOGIN_URL); WebDriverWait(browser,30).until(lambda d:d.find_elements(By.CSS_SELECTOR,"input[type='password']"))
        time.sleep(1); user,pw=core.gst_login_boxes(browser)
        if not user or not pw: raise RuntimeError("GST Portal login fields were not found.")
        user.clear(); user.send_keys(username.strip()); pw.clear(); pw.send_keys(password)
        _sessions[session_id]={"driver":browser,"folder":folder}
        return browser.get_screenshot_as_png()
    except Exception: browser.quit(); shutil.rmtree(folder,ignore_errors=True); raise
def submit_portal_code(session_id,code):
    browser=_sessions[session_id]["driver"]; inputs=browser.find_elements(By.CSS_SELECTOR,"input")
    field=next((e for e in inputs if e.is_displayed() and e.is_enabled() and any(k in " ".join((e.get_attribute(a) or "") for a in ("id","name","placeholder","aria-label")).lower() for k in ("captcha","otp","verification","security"))),None)
    if field is None:
        field=next((e for e in inputs if e.is_displayed() and e.is_enabled() and (e.get_attribute("type") or "text").lower() not in ("password","hidden") and "user" not in " ".join((e.get_attribute(a) or "") for a in ("id","name","placeholder")).lower()),None)
    if field is None:return False,browser.get_screenshot_as_png(),"Could not find visible CAPTCHA/OTP input."
    field.clear(); field.send_keys(code.strip()); buttons=browser.find_elements(By.XPATH,"//button|//input[@type='submit']|//a[@role='button']")
    button=next((b for b in buttons if b.is_displayed() and b.is_enabled() and any(k in " ".join((b.text or "",b.get_attribute("value") or "",b.get_attribute("aria-label") or "")).lower() for k in ("login","sign in","submit","verify","continue"))),None)
    button.click() if button else field.submit(); time.sleep(3); body=browser.find_element(By.TAG_NAME,"body").text.lower()
    logged="/returns/auth/" in browser.current_url.lower() or "logout" in body or "return dashboard" in body
    return logged,browser.get_screenshot_as_png(),"GST Portal login succeeded." if logged else "If the portal asks for another CAPTCHA or OTP, enter it here."
def download_periods(session_id,months,quarterly=False):
    state=_sessions[session_id]; browser,folder=state["driver"],state["folder"]; periods=list(months)
    if quarterly:periods,_,_,_=core.resolve_quarterly_periods(periods)
    converted=[]; failures=[]
    for month,year in periods:
        status,info=core.gst_download_gstr2b_json(browser,month,year,folder,is_quarterly=quarterly)
        if status!="downloaded":failures.append(f"{month} {year}: {info}"); continue
        source=os.path.join(folder,info); target=os.path.join(folder,f"{year}-{core.MONTHS.index(month)+1:02d}.xlsx")
        core.convert_and_save_period_excel(source,target,period_label=f"{month[:3]}-{year}",quarterly=quarterly); converted.append(target)
    if not converted:raise RuntimeError("No workbook was produced. "+"; ".join(failures))
    output=os.path.join(folder,"GSTR2B_MERGED.xlsx"); core.merge_all_gstr2b_periods(converted,output)
    with open(output,"rb") as f:data=f.read()
    summary=f"Prepared {len(converted)} period(s)."
    if failures:summary+=" Skipped: "+"; ".join(failures)
    return data,summary
def close_session(session_id):
    state=_sessions.pop(session_id,None)
    if not state:return
    try:state["driver"].quit()
    except Exception:pass
    shutil.rmtree(state["folder"],ignore_errors=True)
