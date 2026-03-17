# launcher.py — Fixed for PyInstaller frozen .exe
import sys
import os

# ── Fix paths for frozen bundle ───────────────────────────────────────────────
if getattr(sys, 'frozen', False):
    # Running as .exe — set working directory to the bundle folder
    bundle_dir = sys._MEIPASS
    os.chdir(bundle_dir)
else:
    bundle_dir = os.path.dirname(os.path.abspath(__file__))

# ── FIX: Force developmentMode OFF before Streamlit loads any config ──────────
# When frozen by PyInstaller, Streamlit can default to developmentMode=true,
# which raises: "server.port does not work when global.developmentMode is true"
os.environ["STREAMLIT_GLOBAL_DEVELOPMENT_MODE"] = "false"
os.environ["STREAMLIT_SERVER_HEADLESS"] = "true"

import socket
import threading
import webbrowser
import time

def find_free_port(start=8501):
    for port in range(start, start + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("localhost", port))
                return port
            except OSError:
                continue
    return 8501

def open_browser(port):
    time.sleep(4)
    webbrowser.open(f"http://localhost:{port}")

def main():
    port = find_free_port()

    # Open browser in background
    threading.Thread(target=open_browser, args=(port,), daemon=True).start()

    app_path = os.path.join(bundle_dir, "app.py")

    # ── Run Streamlit inside a frozen .exe ────────────────────────────────────
    from streamlit.web import cli as stcli
    sys.argv = [
        "streamlit", "run",
        app_path,
        "--server.port",              str(port),
        "--server.headless",          "true",
        "--server.address",           "localhost",
        "--global.developmentMode",   "false",   # ← KEY FIX
        "--browser.gatherUsageStats", "false",
        "--theme.base",               "light",
        "--theme.primaryColor",       "#0f52ba",
    ]
    sys.exit(stcli.main())

if __name__ == "__main__":
    main()
