# modules/license_manager.py
# GST Tool License Manager — Cloud-aware version
# On Streamlit Cloud: All users get FREE access (no MAC lock)
# On Local EXE: MAC-locked, 7-day trial + 1-year key activation

import os
import json
import hashlib
import platform
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

_SALT = "GST_TOOL_v4_SECURE_2024"

from modules.key_hashes import VALID_KEY_HASHES

# ── Detect if running on Streamlit Cloud ─────────────────────────────────────
def _is_cloud() -> bool:
    """Returns True if running on Streamlit Cloud or any Linux server."""
    # Streamlit Cloud sets this env variable
    if os.environ.get("STREAMLIT_SHARING_MODE"):
        return True
    # Streamlit Cloud always runs on Linux; local EXE is always Windows
    if platform.system() == "Linux":
        return True
    return False

# ── License file path (local EXE only) ───────────────────────────────────────
def _get_license_path() -> Path:
    if platform.system() == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path.home()
    folder = base / "GSTToolLicense"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "license.dat"

# ── MAC address (local EXE only) ─────────────────────────────────────────────
def _get_mac_address() -> str:
    try:
        import uuid
        mac = uuid.getnode()
        if (mac >> 40) % 2:
            raise ValueError("Random MAC")
        return ':'.join(f'{(mac >> (8*i)) & 0xff:02x}' for i in reversed(range(6)))
    except Exception:
        pass
    try:
        if platform.system() == "Windows":
            result = subprocess.check_output("getmac /fo csv /nh", shell=True).decode()
            return result.split(',')[0].strip().strip('"').replace('-', ':')
        else:
            result = subprocess.check_output("cat /sys/class/net/*/address", shell=True).decode()
            macs = [m.strip() for m in result.strip().split('\n') if m.strip() != '00:00:00:00:00:00']
            if macs:
                return macs[0]
    except Exception:
        pass
    return "UNKNOWN_DEVICE"

def _hash_key(key: str) -> str:
    return hashlib.sha256(key.strip().upper().encode()).hexdigest()

def _hash_mac(mac: str) -> str:
    return hashlib.sha256(f"{_SALT}:{mac}".encode()).hexdigest()

def _read_license() -> dict:
    path = _get_license_path()
    if not path.exists():
        return {}
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except Exception:
        return {}

def _write_license(data: dict):
    path = _get_license_path()
    with open(path, 'w') as f:
        json.dump(data, f)

# ═════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═════════════════════════════════════════════════════════════════════════════

def get_license_status() -> dict:
    # ── CLOUD: Always active, no MAC lock ────────────────────────────────────
    if _is_cloud():
        return {
            "status":    "active",
            "days_left": 9999,
            "message":   "✅ Cloud version — Full access enabled.",
            "mac":       "CLOUD",
        }

    # ── LOCAL EXE: MAC-locked trial / key logic ───────────────────────────────
    mac      = _get_mac_address()
    mac_hash = _hash_mac(mac)
    data     = _read_license()
    now      = datetime.now()

    if not data:
        trial_end = (now + timedelta(days=7)).isoformat()
        _write_license({"mode": "trial", "mac_hash": mac_hash,
                        "trial_start": now.isoformat(), "trial_end": trial_end})
        return {"status": "trial", "days_left": 7,
                "message": "Welcome! You have a 7-day free trial.", "mac": mac}

    stored_mac = data.get("mac_hash", "")
    if stored_mac and stored_mac != mac_hash:
        return {"status": "blocked", "days_left": 0,
                "message": "This license is registered to a different device.", "mac": mac}

    if data.get("mode") == "trial":
        trial_end = datetime.fromisoformat(data["trial_end"])
        if now < trial_end:
            days = (trial_end - now).days + 1
            return {"status": "trial", "days_left": days,
                    "message": f"Trial active — {days} day(s) remaining.", "mac": mac}
        return {"status": "expired_trial", "days_left": 0,
                "message": "Your 7-day trial has expired. Please enter an activation key.", "mac": mac}

    if data.get("mode") == "activated":
        expiry = datetime.fromisoformat(data["expiry"])
        if now < expiry:
            days = (expiry - now).days + 1
            return {"status": "active", "days_left": days,
                    "message": f"Licensed — {days} day(s) remaining (expires {expiry.strftime('%d %b %Y')}).", "mac": mac}
        return {"status": "expired_key", "days_left": 0,
                "message": "Your license key has expired.", "mac": mac}

    return {"status": "blocked", "days_left": 0,
            "message": "Invalid license data.", "mac": mac}


def activate_key(key: str) -> dict:
    if _is_cloud():
        return {"success": True, "message": "✅ Cloud version — no activation needed."}

    mac      = _get_mac_address()
    mac_hash = _hash_mac(mac)
    key_hash = _hash_key(key)

    if key_hash not in VALID_KEY_HASHES:
        return {"success": False, "message": "❌ Invalid key. Please check and try again."}

    existing = _read_license()
    if existing.get("key_hash") == key_hash and existing.get("mac_hash") == mac_hash:
        expiry = datetime.fromisoformat(existing["expiry"])
        return {"success": True, "message": f"✅ Already activated. Expires {expiry.strftime('%d %b %Y')}."}

    if existing.get("key_hash") == key_hash and existing.get("mac_hash") != mac_hash:
        return {"success": False, "message": "❌ This key is registered to another device."}

    now    = datetime.now()
    expiry = now + timedelta(days=365)
    _write_license({"mode": "activated", "mac_hash": mac_hash, "key_hash": key_hash,
                    "activated": now.isoformat(), "expiry": expiry.isoformat()})
    return {"success": True, "message": f"✅ Activation successful! Licensed until {expiry.strftime('%d %b %Y')}."}


def is_allowed_to_run() -> bool:
    status = get_license_status()
    return status["status"] in ("trial", "active")
