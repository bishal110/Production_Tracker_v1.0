# =============================================================================
# server.py v3 — Production-Ready Well Dashboard Backend
#
# NEW vs v2:
#   - config.json drives everything (column names, sheet names, server settings)
#   - Column mapping: your Excel headers → internal names (no code changes needed)
#   - Granular error handling: FILE_NOT_FOUND, FILE_LOCKED, SHEET_NOT_FOUND,
#     COLUMN_NOT_FOUND, READ_ERROR — each with specific hint messages
#   - Serves index.html directly at http://<ip>:5000/
#   - host=0.0.0.0 → accessible from any machine on the same network
#   - /health endpoint for quick server status check
#   - /config endpoint so frontend reads title, refresh rate from config
#   - New wells added to Excel → auto-detected, no restart needed
# =============================================================================

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
import pandas as pd
import json, os, sys, socket
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=BASE_DIR)
CORS(app)


# =============================================================================
# Load config.json — exits with clear message if missing or broken
# =============================================================================
def load_config():
    path = os.path.join(BASE_DIR, "config.json")
    if not os.path.exists(path):
        print(f"\n[FATAL] config.json not found at: {path}")
        print("        Make sure config.json is in the same folder as server.py\n")
        sys.exit(1)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"\n[FATAL] config.json has invalid JSON: {e}")
        print("        Fix the syntax error and restart server.py\n")
        sys.exit(1)

CFG             = load_config()
EXCEL_FILE      = os.path.join(BASE_DIR, CFG["excel"]["filename"])
WELLS_SHEET     = CFG["excel"]["wells_sheet"]
EVENTLOG_SHEET  = CFG["excel"]["eventlog_sheet"]
COL_MAP         = CFG["excel"]["column_map"]
ELOG_MAP        = CFG["excel"]["eventlog_column_map"]
STATUS_ON       = [s.upper() for s in CFG["excel"]["status_on"]]
STATUS_SHUT     = [s.upper() for s in CFG["excel"]["status_shut"]]
STATUS_TEST     = [s.upper() for s in CFG["excel"]["status_test"]]
SERVER_HOST     = CFG["server"]["host"]
SERVER_PORT     = int(CFG["server"]["port"])
REFRESH_MS      = int(CFG["server"]["refresh_ms"])


# =============================================================================
# Helpers
# =============================================================================

def classify_status(raw):
    """Maps any status value to ON / SHUT / TEST using config lists."""
    s = str(raw or "").upper().strip()
    if s in STATUS_ON:   return "ON"
    if s in STATUS_SHUT: return "SHUT"
    if s in STATUS_TEST: return "TEST"
    return s  # unknown — pass through as-is


def read_sheet(sheet_name):
    """
    Reads one sheet from Excel with granular error handling.
    Returns (df, None) on success or (None, error_dict) on failure.
    Error dict always has: code, error, hint
    """
    # 1. File missing
    if not os.path.exists(EXCEL_FILE):
        return None, {
            "code":  "FILE_NOT_FOUND",
            "error": f"File not found: {os.path.basename(EXCEL_FILE)}",
            "hint":  f"Expected at {EXCEL_FILE} — check config.json → excel.filename"
        }

    # 2. File locked (Excel has it open and unsaved)
    try:
        with open(EXCEL_FILE, "rb"):
            pass
    except PermissionError:
        return None, {
            "code":  "FILE_LOCKED",
            "error": f"{os.path.basename(EXCEL_FILE)} is locked by Excel",
            "hint":  "Save the file in Excel (Ctrl+S). Dashboard will update automatically."
        }

    # 3. Read
    try:
        df = pd.read_excel(EXCEL_FILE, sheet_name=sheet_name, engine="openpyxl", header=0)
        return df, None

    except PermissionError:
        return None, {
            "code":  "FILE_LOCKED",
            "error": f"{os.path.basename(EXCEL_FILE)} is locked",
            "hint":  "Close or save the file in Excel."
        }

    except ValueError as e:
        # Sheet name not found in workbook
        if "Worksheet" in str(e) or "sheet" in str(e).lower():
            return None, {
                "code":  "SHEET_NOT_FOUND",
                "error": f"Sheet '{sheet_name}' not found in {os.path.basename(EXCEL_FILE)}",
                "hint":  (
                    f"Update config.json → excel.wells_sheet (currently '{WELLS_SHEET}'). "
                    f"Sheet names are visible as tabs at the bottom of your Excel file."
                )
            }
        return None, {"code": "READ_ERROR", "error": str(e), "hint": "Check for merged cells or hidden rows."}

    except Exception as e:
        return None, {
            "code":  "UNKNOWN_ERROR",
            "error": f"Could not read '{sheet_name}': {str(e)}",
            "hint":  "Make sure the file is a valid .xlsx (not .xls or .csv)."
        }


def apply_mapping(df, mapping):
    """
    Renames df columns using the mapping dict {InternalName: YourExcelColumn}.
    Returns (renamed_df, []) on success.
    Returns (None, [missing_info,...]) if any mapped column is absent.
    """
    missing = []
    for internal, excel_col in mapping.items():
        if excel_col not in df.columns:
            missing.append({
                "internal_name":  internal,
                "expected_column": excel_col,
                "columns_in_file": sorted(df.columns.tolist())
            })
    if missing:
        return None, missing
    reverse = {v: k for k, v in mapping.items()}
    return df.rename(columns=reverse), []


def safe_num(series):
    """Converts a column to numeric, stripping commas/symbols, defaulting to 0."""
    return (
        series.astype(str)
              .str.replace(r"[₹$,\s]", "", regex=True)
              .pipe(pd.to_numeric, errors="coerce")
              .fillna(0)
    )


# =============================================================================
# Routes
# =============================================================================

@app.route("/")
def serve_dashboard():
    """Serves the dashboard HTML file directly — open http://<ip>:5000/ in any browser."""
    idx = os.path.join(BASE_DIR, "index.html")
    if not os.path.exists(idx):
        return ("<h2 style='font-family:monospace;padding:40px'>"
                "index.html not found.<br>"
                f"Put index.html in: {BASE_DIR}</h2>"), 404
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/health")
def health():
    """Returns server + file status. Open /health in browser to verify server is up."""
    locked = False
    if os.path.exists(EXCEL_FILE):
        try:
            with open(EXCEL_FILE, "rb"):
                pass
        except PermissionError:
            locked = True
    return jsonify({
        "status":       "running",
        "timestamp":    datetime.now().isoformat(),
        "excel_file":   os.path.basename(EXCEL_FILE),
        "file_exists":  os.path.exists(EXCEL_FILE),
        "file_locked":  locked,
        "wells_sheet":  WELLS_SHEET,
        "elog_sheet":   EVENTLOG_SHEET,
    })


@app.route("/config")
def get_cfg():
    """Returns display config to the frontend."""
    return jsonify({
        "title":      CFG["dashboard"]["title"],
        "subtitle":   CFG["dashboard"]["subtitle"],
        "platform":   CFG["dashboard"]["platform"],
        "refresh_ms": REFRESH_MS,
    })


@app.route("/data")
def get_data():
    """Live well data + KPIs from the Wells sheet."""

    df, err = read_sheet(WELLS_SHEET)
    if err:
        code = {"FILE_NOT_FOUND": 404, "FILE_LOCKED": 423}.get(err["code"], 500)
        return jsonify(err), code

    df, missing = apply_mapping(df, COL_MAP)
    if missing:
        return jsonify({
            "code":    "COLUMN_NOT_FOUND",
            "error":   f"Column mapping failed for sheet '{WELLS_SHEET}'",
            "missing": missing,
            "hint":    "Edit config.json → excel.column_map. Right side must exactly match your Excel column headers (case-sensitive)."
        }), 400

    # Keep only mapped columns
    df = df[list(COL_MAP.keys())].copy()

    # Clean Well and Status
    df["Well"]   = df["Well"].fillna("").astype(str).str.strip()
    df["Status"] = df["Status"].fillna("").astype(str).str.strip().apply(classify_status)

    # Drop empty/NaN well rows (Excel often has trailing empty rows)
    df = df[df["Well"].str.len() > 0]
    df = df[df["Well"].str.upper() != "NAN"]

    # Numeric columns
    for col in ["Choke", "WHP", "THP", "Oil", "Gas", "Water"]:
        df[col] = safe_num(df[col])

    wells    = df.to_dict(orient="records")
    on_wells = [w for w in wells if w.get("Status") == "ON"]

    return jsonify({
        "wells": wells,
        "kpi": {
            "total_oil":   round(sum(w["Oil"]   for w in on_wells), 1),
            "total_gas":   round(sum(w["Gas"]   for w in on_wells), 3),
            "total_water": round(sum(w["Water"] for w in on_wells), 1),
            "wells_on":    len(on_wells),
            "wells_total": len(wells),
        },
        "meta": {
            "rows":      len(wells),
            "timestamp": datetime.now().isoformat(),
        }
    })


@app.route("/events")
def get_events():
    """Event log from EventLog sheet. Non-fatal if sheet missing."""

    df, err = read_sheet(EVENTLOG_SHEET)
    if err:
        # EventLog is optional — return empty with warning instead of error
        return jsonify({"events": [], "warning": err["error"], "hint": err["hint"]})

    df, missing = apply_mapping(df, ELOG_MAP)
    if missing:
        return jsonify({
            "events":  [],
            "warning": "EventLog column mapping failed",
            "missing": missing,
            "hint":    "Edit config.json → excel.eventlog_column_map"
        })

    df = df[list(ELOG_MAP.keys())].copy()

    # Flexible datetime parsing — handles dd/mm/yyyy, dd.mm.yyyy, yyyy-mm-dd HH:MM, etc.
    df["DateTime"] = pd.to_datetime(df["DateTime"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["DateTime"])

    if df.empty:
        return jsonify({"events": []})

    df["Well"]  = df["Well"].fillna("").astype(str).str.strip()
    df["Event"] = df["Event"].fillna("").astype(str).str.strip()
    df["Cause"] = df["Cause"].fillna("").astype(str).str.strip()
    df = df[df["Well"].str.len() > 0]
    df = df.sort_values("DateTime", ascending=False)

    events = []
    for _, row in df.iterrows():
        dt   = row["DateTime"]
        ev   = row["Event"].upper()
        well = row["Well"]
        time_str = dt.strftime("%H%M hrs")
        date_str = dt.strftime("%d.%m.%Y")

        if any(s in ev for s in STATUS_SHUT):
            etype = "SHUT"; msg = f"{well} shut in at {time_str} on {date_str}"
        elif any(s in ev for s in STATUS_ON):
            etype = "ON";   msg = f"{well} started production at {time_str} on {date_str}"
        elif any(s in ev for s in STATUS_TEST):
            etype = "TEST"; msg = f"{well} put on test at {time_str} on {date_str}"
        else:
            etype = "NOTE"; msg = f"{well} — {row['Event']} at {time_str} on {date_str}"

        events.append({
            "datetime_display": f"{time_str}  {date_str}",
            "datetime_iso":     dt.isoformat(),
            "well":             well,
            "event":            row["Event"],
            "event_type":       etype,
            "cause":            row["Cause"],
            "message":          msg,
        })

    return jsonify({"events": events})


# =============================================================================
# Startup
# =============================================================================
if __name__ == "__main__":
    # Get local network IP
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        local_ip = "your-machine-ip"

    print("\n" + "=" * 65)
    print("  Well Production Dashboard — Server v3")
    print("=" * 65)
    print(f"  Excel file   : {EXCEL_FILE}")
    print(f"  Wells sheet  : {WELLS_SHEET}")
    print(f"  EventLog     : {EVENTLOG_SHEET}")
    print()
    print("  Column mapping active:")
    for k, v in COL_MAP.items():
        arrow = "  (same)" if k == v else f"→ maps to '{v}' in your Excel"
        print(f"    {k:10s} {arrow}")
    print()
import os
    port = int(os.environ.get("PORT", SERVER_PORT))
    print(f"  ┌─────────────────────────────────────────────────┐")
    print(f"  │  LOCAL    : http://127.0.0.1:{SERVER_PORT}              │")
    print(f"  │  NETWORK  : http://{local_ip}:{SERVER_PORT}        │")
    print(f"  │  HEALTH   : http://127.0.0.1:{SERVER_PORT}/health       │")
    print(f"  └─────────────────────────────────────────────────┘")
    print()
    print("  Share the NETWORK URL with colleagues on the same network.")
    print("  They can open it in any browser — no installation needed.")
    print()
    print("  Ctrl+C to stop.")
    print("=" * 65 + "\n")

    app.run(host="0.0.0.0", port=port,debug=False)
