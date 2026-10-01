"""Install the per-user Windows launcher used by the hosted Module 2 button."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox


APP_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "GSTReconciliationTool" / "GSTR2BDownloader"
SOURCE_DIR = Path(__file__).resolve().parent


def install() -> None:
    if os.name != "nt":
        raise RuntimeError("This launcher installer is for Windows only.")

    source_script = SOURCE_DIR / "gstr2b_downloader.py"
    source_requirements = SOURCE_DIR / "requirements-downloader.txt"
    if not source_script.is_file() or not source_requirements.is_file():
        raise FileNotFoundError("Extract the complete setup ZIP before running the installer.")

    APP_DIR.mkdir(parents=True, exist_ok=True)
    script_path = APP_DIR / source_script.name
    requirements_path = APP_DIR / source_requirements.name
    shutil.copy2(source_script, script_path)
    shutil.copy2(source_requirements, requirements_path)

    venv_dir = APP_DIR / "venv"
    if not (venv_dir / "Scripts" / "python.exe").is_file():
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
    python_exe = venv_dir / "Scripts" / "python.exe"
    subprocess.run(
        [str(python_exe), "-m", "pip", "install", "-r", str(requirements_path)],
        check=True,
    )

    import winreg

    protocol = "gst2b-downloader"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{protocol}") as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "URL: GST GSTR-2B Downloader")
        winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
    command = f'"{python_exe}" "{script_path}" "%1"'
    with winreg.CreateKey(
        winreg.HKEY_CURRENT_USER,
        rf"Software\Classes\{protocol}\shell\open\command",
    ) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command)

    root = tk.Tk()
    root.withdraw()
    messagebox.showinfo(
        "Setup complete",
        "The Module 2 local downloader is installed for this Windows account.\n\n"
        "Return to Module 2 and click ‘Run Local GSTR-2B Downloader’. "
        "Chrome will open; you complete the CAPTCHA and OTP yourself.",
    )
    root.destroy()


if __name__ == "__main__":
    try:
        install()
    except Exception as exc:
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Setup failed", str(exc))
            root.destroy()
        except Exception:
            print(f"Setup failed: {exc}", file=sys.stderr)
        raise
