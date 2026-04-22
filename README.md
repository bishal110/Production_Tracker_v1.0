# Well Production Dashboard v3
## Setup, Column Mapping & Intranet Hosting Guide

---

## WHAT'S NEW IN V3

1. **config.json** — all settings in one file, never touch server.py again
2. **Column mapping** — your Excel headers can be anything, map them in config
3. **New wells auto-detected** — add a row to Excel, save, dashboard picks it up
4. **Intranet ready** — anyone on your company network opens the URL in a browser
5. **Better errors** — locked file, wrong sheet, wrong column — each has a specific message

---

## FOLDER STRUCTURE

```
your-folder/
├── server.py              ← Python backend (run this)
├── index.html             ← Dashboard (served automatically by server.py)
├── config.json            ← ALL settings here — edit this, not server.py
├── production.xlsx        ← Your data file
└── create_sample_excel.py ← Run once to create sample Excel
```

---

## STEP 1 — Install packages (once only)

```bash
pip install flask flask-cors pandas openpyxl
```

---

## STEP 2 — Edit config.json for your Excel

Open `config.json` and change these to match your actual Excel file:

```json
{
  "excel": {
    "filename": "production.xlsx",       ← your Excel filename
    "wells_sheet": "Wells",              ← your sheet tab name
    "eventlog_sheet": "EventLog",        ← your event log sheet tab name

    "column_map": {
      "Well":   "Well Name",             ← RIGHT SIDE = your actual column header
      "Status": "Well Status",
      "Choke":  "Choke Opening",
      "WHP":    "Wellhead Pressure",
      "THP":    "Tubing Head Pressure",
      "Oil":    "Oil Rate BOPD",
      "Gas":    "Gas Rate MMSCFD",
      "Water":  "Water Rate BWPD"
    }
  }
}
```

The LEFT side (Well, Status, etc.) — NEVER change these.
The RIGHT side — change to exactly match your column headers.

---

## STEP 3 — Run the server

```bash
python server.py
```

You'll see:
```
  LOCAL    : http://127.0.0.1:5000
  NETWORK  : http://192.168.1.45:5000   ← share this with colleagues
  HEALTH   : http://127.0.0.1:5000/health
```

---

## STEP 4 — Open the dashboard

**On your own machine:**
```
http://127.0.0.1:5000
```

**From any other machine on the same network (intranet):**
```
http://192.168.1.45:5000        ← use the NETWORK URL shown in your terminal
```
No installation needed on the other machine — just a browser.

---

## HOW INTRANET ACCESS WORKS

```
Your machine running server.py
        ↓
  Company network (LAN / intranet)
        ↓
Colleague's browser → http://192.168.1.x:5000 → sees the dashboard live
```

Requirements:
- server.py must be running on your machine
- Both machines on the same LAN / intranet
- Windows Firewall must allow port 5000 (see below if blocked)

---

## WINDOWS FIREWALL — Allow port 5000

If colleagues can't reach the dashboard, the firewall is blocking it.
Run this once in Command Prompt as Administrator:

```cmd
netsh advfirewall firewall add rule name="WHP Dashboard" dir=in action=allow protocol=TCP localport=5000
```

To remove it later:
```cmd
netsh advfirewall firewall delete rule name="WHP Dashboard"
```

---

## NEW WELLS — DO NOTHING

Just add a new row to your Excel Wells sheet and save.
The dashboard picks it up automatically within 5 seconds.
No server restart. No config change.

---

## ADDING STATUS VALUES

If your company uses different status words (e.g. "PRODUCING" instead of "ON"),
add them to config.json:

```json
"status_on":   ["ON", "PRODUCING", "OPEN", "FLOWING", "ONLINE"],
"status_shut": ["SHUT", "SHUT-IN", "SHUTIN", "CLOSED", "OFF"],
"status_test": ["TEST", "TESTING", "ON TEST"]
```

---

## TROUBLESHOOTING

### Column not found error
Message: `"Column mapping failed — 'Wellhead Pressure' not found"`
Fix: Open config.json. The right side of column_map must exactly match
     your Excel header. Copy-paste from Excel to be safe. Case-sensitive.

### Sheet not found
Message: `"Sheet 'Wells' not found"`
Fix: Look at the sheet tabs at the bottom of your Excel file.
     Update config.json → excel.wells_sheet with the exact tab name.

### File locked
Message: `"production.xlsx is locked by Excel"`
Fix: Save the file in Excel (Ctrl+S). That releases the lock.
     You DON'T need to close Excel — just save.

### Colleague can't open the network URL
Fix 1: Run the firewall command above.
Fix 2: Check both machines are on the same network segment.
Fix 3: Try pinging your machine from theirs: `ping 192.168.1.x`

### Port 5000 already in use
Fix: In config.json change "port": 5000 to "port": 5001 (or any free port).
     Colleagues use the new port: http://192.168.1.x:5001

### Dashboard shows old data / not updating
Fix: Hard refresh in browser: Ctrl+Shift+R
     Check the "Updated:" timestamp in the top-right header.

### server.py won't start — config.json error
Fix: Open config.json in Notepad. Look for missing commas, unclosed braces.
     Paste the content into https://jsonlint.com to find the exact error.

---

## RUNNING AUTOMATICALLY ON STARTUP (Windows)

To make server.py start automatically when the machine boots:

1. Press Win+R → type `shell:startup` → press Enter
2. Create a file called `start_whp_dashboard.bat` with content:
```bat
@echo off
cd /d "C:\path\to\your\dashboard\folder"
python server.py
```
3. Save it in the Startup folder.

Now the server starts every time Windows boots.

---

## QUICK REFERENCE — API ENDPOINTS

| URL | What it does |
|-----|-------------|
| http://ip:5000/ | Opens the dashboard |
| http://ip:5000/health | Check if server is running |
| http://ip:5000/data | Raw well data JSON |
| http://ip:5000/events | Raw event log JSON |
| http://ip:5000/config | Dashboard config JSON |
