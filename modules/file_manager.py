# modules/file_manager.py
import os
import platform
import subprocess

# Root folder for all clients
BASE_DIR = "GST_Clients_Data"

def get_client_path(name, gstin, fy, period):
    """
    Creates the directory structure: GST_Clients_Data / Client_Name_GSTIN / FY / Period
    Returns the absolute path.
    """
    # 1. Sanitize Folder Name (Remove bad characters)
    safe_name = "".join([c for c in name if c.isalnum() or c in (' ', '_', '-')]).strip()
    safe_gstin = "".join([c for c in gstin if c.isalnum()])
    
    # 2. Build Path
    # Example: GST_Clients_Data/ShyamCreation_24AA.../2025-2026/March
    folder_path = os.path.join(BASE_DIR, f"{safe_name}_{safe_gstin}", fy, period)
    
    # 3. Create Directory if it doesn't exist
    os.makedirs(folder_path, exist_ok=True)
    
    return os.path.abspath(folder_path)

def save_file_to_folder(folder_path, filename, file_bytes):
    """
    Saves a file (bytes) to the specified folder.
    """
    full_path = os.path.join(folder_path, filename)
    with open(full_path, "wb") as f:
        f.write(file_bytes)
    return full_path

def open_folder(path):
    """
    Opens the folder in Windows Explorer (or Finder on Mac).
    """
    if platform.system() == "Windows":
        os.startfile(path)
    elif platform.system() == "Darwin":  # macOS
        subprocess.Popen(["open", path])
    else:  # Linux
        subprocess.Popen(["xdg-open", path])