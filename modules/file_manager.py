# modules/file_manager.py — Cloud-compatible version
import os
import platform
import subprocess

BASE_DIR = "GST_Clients_Data"

def get_client_path(name, gstin, fy, period):
    """
    Creates directory structure: GST_Clients_Data / Client_Name_GSTIN / FY / Period
    On cloud (Linux /tmp is writable), on Windows uses local folder.
    """
    safe_name  = "".join([c for c in name  if c.isalnum() or c in (' ', '_', '-')]).strip()
    safe_gstin = "".join([c for c in gstin if c.isalnum()])

    if platform.system() == "Linux":
        # Cloud: use /tmp which is always writable on Streamlit Cloud
        base = "/tmp/GST_Clients_Data"
    else:
        base = BASE_DIR

    folder_path = os.path.join(base, f"{safe_name}_{safe_gstin}", fy, period)
    os.makedirs(folder_path, exist_ok=True)
    return os.path.abspath(folder_path)


def save_file_to_folder(folder_path, filename, file_bytes):
    """Saves a file (bytes) to the specified folder."""
    full_path = os.path.join(folder_path, filename)
    with open(full_path, "wb") as f:
        f.write(file_bytes)
    return full_path


def open_folder(path):
    """
    Opens folder in file explorer.
    On cloud/Linux server this is a no-op (silently ignored).
    """
    try:
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", path])
        else:
            # Linux cloud server — cannot open folder in browser, silently pass
            pass
    except Exception:
        pass
