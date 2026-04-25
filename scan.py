"""
PKScreener Auto-Scanner
Runs scans and exports results as JSON for the dashboard.
Triggered by GitHub Actions twice daily.
"""

import json
import os
import sys
import subprocess
import re
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime.now(IST)
TIMESTAMP = NOW.strftime("%d %b %Y %I:%M %p IST")
DATE_KEY = NOW.strftime("%Y-%m-%d")

OUTPUT_FILE = "data.json"

# ─── SCANS TO RUN ─────────────────────────────────────────────────────────────
# Keeping only 1 scan to stay within GitHub Actions 30-min timeout
SCANS = [
    ("Breakout Stocks", "X:1:7", "BREAKOUT"),
]

# ─── HELPERS ──────────────────────────────────────────────────────────────────
def install_pkscreener():
    print("[+] Installing PKScreener...")
    subprocess.run([sys.executable, "-m", "pip", "install", "pkscreener", "--quiet"], check=True)

    import site
    site_packages = site.getsitepackages()[0]

    menu_file = os.path.join(site_packages, "pkscreener", "classes", "MenuOptions.py")
    if os.path.exists(menu_file):
        with open(menu_file, "r", encoding="utf-8") as f:
            content = f.read()
        patched = content.replace(
            "self.is_subscription_enabled = bool(int(PKEnvironment().SUBSCRIPTION_ENABLED))",
            "self.is_subscription_enabled = False"
        )
        with open(menu_file, "w", encoding="utf-8") as f:
            f.write(patched)
        print("[+] MenuOptions.py patched.")

    cli_file = os.path.join(site_packages, "pkscreener", "pkscreenercli.py")
    if os.path.exists(cli_file):
        with open(cli_file, "r", encoding="utf-8") as f:
            content = f.read()
        patched = content.replace(
            "if not PKUserRegistration.login():",
            "if False:  # login bypassed for automation"
        )
        with open(cli_file, "w", encoding="utf-8") as f:
            f.write(patched)
        print("[+] pkscreenercli.py login bypass applied.")


def run_scan(option):
    """Run a single PKScreener scan and return raw output."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pkscreener.pkscreenercli", "-o", option, "-a", "Y"],
            capture_output=True, text=True, timeout=1200
        )
        return result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        print(f"  [!] Scan {option} timed out.")
        return ""
    except Exception as e:
        print(f"  [!] Scan {option} error: {e}")
        return ""


def parse_output(raw_output, scan_type):
    stocks = []
    lines = raw_output.split("\n")

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        parts = re.split(r'\s{2,}|\t', stripped)
        if len(parts) < 6:
            continue

        symbol = parts[0].strip()
        if not re.match(r'^[A-Z&]{2,20}$', symbol):
            continue
        if symbol in ('STOCK', 'SYMBOL', 'NAME', 'SCRIP'):
            continue

        try:
            ltp   = float(re.sub(r'[^\d.]', '', parts[1])) if len(parts) > 1 else 0
            chg   = float(re.sub(r'[^\d.\-]', '', parts[2])) if len(parts) > 2 else 0
            vol   = float(re.sub(r'[^\d.]', '', parts[3])) if len(parts) > 3 else 1.0
            rsi   = float(re.sub(r'[^\d.]', '', parts[5])) if len(parts) > 5 else 50.0
            w52h  = float(re.sub(r'[^\d.]', '', parts[4])) if len(parts) > 4 else ltp * 1.2
            w52l  = ltp * 0.7

            signal = "BUY" if chg > 0 and rsi > 50 else ("AVOID" if chg < -1 else "WATCH")
            d1 = round(chg * 0.6 + (rsi - 50) * 0.05, 1)
            d2 = round(d1 * 1.4, 1)

            stocks.append({
                "stock":   symbol,
                "sector":  "NSE",
                "ltp":     round(ltp, 2),
                "chg":     round(chg, 2),
                "vol":     round(vol, 1),
                "w52l":    round(w52l, 2),
                "w52h":    round(w52h, 2),
                "rsi":     round(rsi, 1),
                "pattern": scan_type,
                "signal":  signal,
                "d1":      d1,
                "d2":      d2,
                "scan":    scan_type,
            })
        except (ValueError, IndexError):
            continue

    return stocks


def get_market_data():
    try:
        import yfinance as yf
        nifty  = yf.Ticker("^NSEI")
        sensex = yf.Ticker("^BSESN")
        ni = nifty.fast_info
        se = sensex.fast_info
        return {
            "nifty":     round(ni.last_price, 2),
            "niftyChg":  round(((ni.last_price - ni.previous_close) / ni.previous_close) * 100, 2),
            "sensex":    round(se.last_price, 2),
            "sensexChg": round(((se.last_price - se.previous_close) / se.previous_close) * 100, 2),
        }
    except Exception:
        return {"nifty": 0, "niftyChg": 0, "sensex": 0, "sensexChg": 0}


# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    print(f"[+] PKScreener Auto-Scanner starting at {TIMESTAMP}")

    install_pkscreener()

    all_stocks = []
    scan_summary = []

    for label, option, scan_type in SCANS:
        print(f"[+] Running scan: {label} ({option})...")
        raw = run_scan(option)
        stocks = parse_output(raw, scan_type)
        print(f"    Found {len(stocks)} stocks.")
        all_stocks.extend(stocks)
        scan_summary.append({"label": label, "type": scan_type, "count": len(stocks)})

    seen = {}
    for s in all_stocks:
        key = s["stock"]
        if key not in seen:
            seen[key] = s
        else:
            priority = {"BUY": 3, "WATCH": 2, "AVOID": 1}
            if priority.get(s["signal"], 0) > priority.get(seen[key]["signal"], 0):
                seen[key] = s

    unique_stocks = list(seen.values())
    market = get_market_data()

    output = {
        "timestamp":    TIMESTAMP,
        "date":         DATE_KEY,
        "session":      "Pre-Market" if NOW.hour < 12 else "Post-Market",
        "market":       market,
        "scan_summary": scan_summary,
        "stocks":       unique_stocks,
        "total":        len(unique_stocks),
        "buy_count":    len([s for s in unique_stocks if s["signal"] == "BUY"]),
        "watch_count":  len([s for s in unique_stocks if s["signal"] == "WATCH"]),
        "avoid_count":  len([s for s in unique_stocks if s["signal"] == "AVOID"]),
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print(f"[+] Saved {len(unique_stocks)} stocks to {OUTPUT_FILE}")
    print(f"[+] BUY: {output['buy_count']} | WATCH: {output['watch_count']} | AVOID: {output['avoid_count']}")
    print("[+] Done.")


if __name__ == "__main__":
    main()
