# GST Reconciliation Tool — Distribution Guide
## How to Build the .EXE and Distribute to Users

---

## 📦 What's In This Package

| File/Folder | Purpose |
|---|---|
| `app.py` | Main Streamlit app (with license gate added) |
| `launcher.py` | Entry point that PyInstaller wraps into .exe |
| `build_exe.bat` | One-click build script — run on your Windows PC |
| `modules/license_manager.py` | License + trial logic |
| `modules/key_hashes.py` | 500 valid key hashes (not plain text!) |
| `modules/` | All original app modules |

---

## 🚀 How to Build the .EXE (Do this once on your PC)

**Requirements:** Windows PC with Python 3.10+ installed

1. Open this folder in Windows Explorer
2. Double-click **`build_exe.bat`**
3. Wait ~5 minutes for PyInstaller to finish
4. Your .exe will appear in: `dist\GSTReconciliationTool\`

**To share with users:**
- Zip the entire `dist\GSTReconciliationTool\` folder
- Send the zip to your customer
- They extract it and double-click `GSTReconciliationTool.exe`
- The app opens in their browser automatically

---

## 🔐 How the License System Works

### For Users (what they experience):

**Days 1–7 (Free Trial)**
- App opens normally, shows a yellow banner: *"Trial Mode — X days remaining"*
- Full functionality is available
- No key needed

**Day 8+ (Trial Expired)**
- App shows a full-screen activation page
- User must enter a valid key to proceed
- They can contact you to purchase a key

**After Activation**
- Key is locked to their PC's MAC address (hardware ID)
- Works for exactly **1 year** from activation date
- Cannot be used on another PC

### For You (as the seller):

**Giving a key to a customer:**
1. Open the Excel file `activation_keys.xlsx`
2. Pick any key from the "Unused" rows
3. Send that key to your customer (WhatsApp/email is fine)
4. Mark it as "Active" in your Excel and note their name

**If a key expires:**
- Give them a new (unused) key from your list
- The old key is done — they activate with the new one

**If a customer changes PC:**
- Their old key is bound to old MAC — they need a new key
- Give them a fresh unused key

---

## 🛡️ Security Notes

- Keys are stored as **SHA256 hashes** inside the app — the original keys are NOT in the code
- Even if someone extracts the .exe, they cannot recover the valid keys from the hashes
- Each key-MAC combo is stored in the user's AppData folder (encrypted)
- Copying the folder to another PC will **not** work — MAC check will block it

---

## 📋 Your 500 Keys

See the files you already downloaded:
- `activation_keys.xlsx` — Track which keys are used
- `activation_keys.txt` — Plain list of all 500 keys

**Never share the full key list publicly.** Give one key per customer.

---

## ❓ Troubleshooting

| Problem | Solution |
|---|---|
| Build fails with "Python not found" | Install Python from python.org, check "Add to PATH" |
| Build fails with import error | Run `pip install streamlit pyinstaller --upgrade` manually |
| App doesn't open after double-click | Check Windows Defender isn't blocking it; try "Run as administrator" |
| User says key doesn't work | Make sure they type it exactly: `XXXX-XXXX-XXXX-XXXX` (caps don't matter) |
| User changed PC and key won't activate | Give them a fresh unused key from your list |
