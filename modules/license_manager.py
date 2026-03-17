# modules/license_manager.py
# GST Tool License Manager — Offline, MAC-locked, 7-day trial + 1-year key activation
# Keys are stored as SHA256 hashes — original keys are never embedded in the app

import os
import json
import hashlib
import platform
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

# ── Secret salt (makes brute-forcing hashes harder) ──────────────────────────
_SALT = "GST_TOOL_v4_SECURE_2024"

# ── Import the 500 valid key hashes ──────────────────────────────────────────
from modules.key_hashes import VALID_KEY_HASHES

# ── Where the license file lives on the user's machine ───────────────────────
def _get_license_path() -> Path:
    """Store license in user's AppData (Windows) or home dir (others)."""
    if platform.system() == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path.home()
    folder = base / "GSTToolLicense"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "license.dat"

# ── Get machine MAC address (most reliable hardware ID) ──────────────────────
def _get_mac_address() -> str:
    """Get the primary MAC address of this machine."""
    try:
        import uuid
        mac = uuid.getnode()
        # uuid.getnode can return a random number if MAC not found
        # Check if it's a real MAC (multicast bit should be 0)
        if (mac >> 40) % 2:
            raise ValueError("Random MAC detected")
        return ':'.join(f'{(mac >> (8*i)) & 0xff:02x}' for i in reversed(range(6)))
    except Exception:
        pass

    # Fallback: parse from system commands
    try:
        if platform.system() == "Windows":
            result = subprocess.check_output("getmac /fo csv /nh", shell=True).decode()
            mac = result.split(',')[0].strip().strip('"').replace('-', ':')
            return mac
        else:
            result = subprocess.check_output("cat /sys/class/net/*/address", shell=True).decode()
            macs = [m.strip() for m in result.strip().split('\n') if m.strip() != '00:00:00:00:00:00']
            if macs:
                return macs[0]
    except Exception:
        pass

    return "UNKNOWN_DEVICE"

# ── Hash a key (with salt) ────────────────────────────────────────────────────
def _hash_key(key: str) -> str:
    normalized = key.strip().upper()
    return hashlib.sha256(normalized.encode()).hexdigest()

# ── Hash a MAC (for secure storage) ──────────────────────────────────────────
def _hash_mac(mac: str) -> str:
    return hashlib.sha256(f"{_SALT}:{mac}".encode()).hexdigest()

# ── Read license file ─────────────────────────────────────────────────────────
def _read_license() -> dict:
    path = _get_license_path()
    if not path.exists():
        return {}
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except Exception:
        return {}

# ── Write license file ────────────────────────────────────────────────────────
def _write_license(data: dict):
    path = _get_license_path()
    with open(path, 'w') as f:
        json.dump(data, f)

# ═════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═════════════════════════════════════════════════════════════════════════════

def get_license_status() -> dict:
    """
    Returns a dict with:
      - status: 'trial' | 'active' | 'expired_trial' | 'expired_key' | 'blocked'
      - days_left: int (for trial or active license)
      - message: str (human-readable)
      - mac: str
    """
    mac = _get_mac_address()
    mac_hash = _hash_mac(mac)
    license_data = _read_license()
    now = datetime.now()

    # ── Case 1: Never launched before (fresh install) ─────────────────────────
    if not license_data:
        trial_start = now.isoformat()
        trial_end   = (now + timedelta(days=7)).isoformat()
        _write_license({
            "mode":        "trial",
            "mac_hash":    mac_hash,
            "trial_start": trial_start,
            "trial_end":   trial_end,
        })
        return {
            "status":    "trial",
            "days_left": 7,
            "message":   "Welcome! You have a 7-day free trial.",
            "mac":       mac,
        }

    # ── Case 2: MAC mismatch — different PC ───────────────────────────────────
    stored_mac_hash = license_data.get("mac_hash", "")
    if stored_mac_hash and stored_mac_hash != mac_hash:
        return {
            "status":    "blocked",
            "days_left": 0,
            "message":   "This license is registered to a different device. Please use your original PC or purchase a new license key.",
            "mac":       mac,
        }

    # ── Case 3: Trial mode ────────────────────────────────────────────────────
    if license_data.get("mode") == "trial":
        trial_end = datetime.fromisoformat(license_data["trial_end"])
        if now < trial_end:
            days_left = (trial_end - now).days + 1
            return {
                "status":    "trial",
                "days_left": days_left,
                "message":   f"Trial active — {days_left} day(s) remaining.",
                "mac":       mac,
            }
        else:
            return {
                "status":    "expired_trial",
                "days_left": 0,
                "message":   "Your 7-day trial has expired. Please enter an activation key to continue.",
                "mac":       mac,
            }

    # ── Case 4: Activated with a key ─────────────────────────────────────────
    if license_data.get("mode") == "activated":
        expiry = datetime.fromisoformat(license_data["expiry"])
        if now < expiry:
            days_left = (expiry - now).days + 1
            return {
                "status":    "active",
                "days_left": days_left,
                "message":   f"Licensed — {days_left} day(s) remaining (expires {expiry.strftime('%d %b %Y')}).",
                "mac":       mac,
            }
        else:
            return {
                "status":    "expired_key",
                "days_left": 0,
                "message":   "Your license key has expired. Please contact the seller for a renewal key.",
                "mac":       mac,
            }

    return {
        "status":    "blocked",
        "days_left": 0,
        "message":   "Invalid license data. Please contact support.",
        "mac":       mac,
    }


def activate_key(key: str) -> dict:
    """
    Attempt to activate the software with a given key.
    Returns: { 'success': bool, 'message': str }
    """
    mac      = _get_mac_address()
    mac_hash = _hash_mac(mac)
    key_hash = _hash_key(key)

    # Check if key is in the valid set
    if key_hash not in VALID_KEY_HASHES:
        return {"success": False, "message": "❌ Invalid key. Please check and try again."}

    # Check current license
    existing = _read_license()

    # If already activated with this key on this machine — allow (re-activate)
    if existing.get("key_hash") == key_hash and existing.get("mac_hash") == mac_hash:
        expiry = datetime.fromisoformat(existing["expiry"])
        return {
            "success": True,
            "message": f"✅ Already activated on this device. Expires {expiry.strftime('%d %b %Y')}."
        }

    # If this key was used on a DIFFERENT MAC — block it
    if existing.get("key_hash") == key_hash and existing.get("mac_hash") != mac_hash:
        return {
            "success": False,
            "message": "❌ This key is already registered to another device. Each key can only be used on one PC."
        }

    # Activate!
    now    = datetime.now()
    expiry = now + timedelta(days=365)

    _write_license({
        "mode":       "activated",
        "mac_hash":   mac_hash,
        "key_hash":   key_hash,
        "activated":  now.isoformat(),
        "expiry":     expiry.isoformat(),
    })

    return {
        "success": True,
        "message": f"✅ Activation successful! Licensed until {expiry.strftime('%d %b %Y')}."
    }


def is_allowed_to_run() -> bool:
    """Quick check — returns True if app should be allowed to run."""
    status = get_license_status()
    return status["status"] in ("trial", "active")
