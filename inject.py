"""
inject.py
Reads data.json produced by scan.py and injects it into index.html.
Strips any previous injection before adding the new one.
"""

import json
import os
import re

DATA_FILE     = "data.json"
TEMPLATE_FILE = "index.html"
OUTPUT_FILE   = "index.html"

# Marks the boundary of the injected block
INJECT_START = "// ─── INJECTED BY GITHUB ACTIONS"
INJECT_END   = "// ─────────────────────────────────────────────────────────────────────────────"
INIT_MARKER  = "// ── INIT ──────────────────────────────────────────────────────────────────────"

def main():
    if not os.path.exists(DATA_FILE):
        print("[!] data.json not found. Run scan.py first.")
        return

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
        html = f.read()

    # ── Strip ALL previous injections ────────────────────────────────────────
    # Remove every block from INJECT_START to INJECT_END (inclusive)
    pattern = re.compile(
        r'// ─── INJECTED BY GITHUB ACTIONS.*?// ─{20,}\n?',
        re.DOTALL
    )
    html = pattern.sub('', html)
    print(f"[+] Stripped old injections.")

    # ── Build new injection (uses correct JS names: data / render) ───────────
    injection = f"""// ─── INJECTED BY GITHUB ACTIONS ──────────────────────────────────────────────
const LIVE_DATA = {json.dumps(data, indent=2)};

window.addEventListener('DOMContentLoaded', function() {{
  if (LIVE_DATA.stocks && LIVE_DATA.stocks.length > 0) {{
    // Populate table with live stocks
    data = LIVE_DATA.stocks;
    render(data);
  }}

  // Market indices
  if (LIVE_DATA.market && LIVE_DATA.market.nifty) {{
    document.getElementById('niftyVal').textContent  = LIVE_DATA.market.nifty.toLocaleString('en-IN', {{minimumFractionDigits:2}});
    document.getElementById('sensexVal').textContent = LIVE_DATA.market.sensex.toLocaleString('en-IN', {{minimumFractionDigits:2}});
    const nChg = LIVE_DATA.market.niftyChg;
    const sChg = LIVE_DATA.market.sensexChg;
    const ne = document.getElementById('niftyChg');
    const se = document.getElementById('sensexChg');
    ne.textContent = (nChg >= 0 ? '+' : '') + nChg.toFixed(2) + '%';
    se.textContent = (sChg >= 0 ? '+' : '') + sChg.toFixed(2) + '%';
    ne.className = 'mpill-chg ' + (nChg >= 0 ? 'up' : 'dn');
    se.className = 'mpill-chg ' + (sChg >= 0 ? 'up' : 'dn');
  }}

  // Timestamp & session badge
  const lu = document.getElementById('lastUpdated');
  lu.textContent = 'Last scan: ' + LIVE_DATA.timestamp;
  const badge = document.createElement('span');
  badge.textContent = LIVE_DATA.session;
  badge.style.cssText = 'font-size:10px;padding:2px 8px;border-radius:4px;background:rgba(0,212,170,0.15);color:var(--accent);font-family:var(--font-mono);margin-left:8px;';
  lu.appendChild(badge);

  // Scan summary tags
  const scanTags = (LIVE_DATA.scan_summary || []).map(s => s.label + ' (' + s.count + ')').join(' · ');
  const stag = document.getElementById('stag');
  if (stag) stag.textContent = scanTags || 'Live Scan';
  const rmeta = document.getElementById('rmeta');
  if (rmeta) rmeta.textContent = LIVE_DATA.total + ' stocks · ' + LIVE_DATA.date;
}});
// ─────────────────────────────────────────────────────────────────────────────

"""

    # ── Insert just before the INIT marker ───────────────────────────────────
    if INIT_MARKER in html:
        html = html.replace(INIT_MARKER, injection + INIT_MARKER, 1)
        print(f"[+] Injected at INIT marker.")
    else:
        # Fallback: inject before closing </script>
        html = html.replace('</script>', injection + '\n</script>', 1)
        print(f"[!] INIT marker not found — injected before </script>.")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[+] Saved {OUTPUT_FILE}")
    print(f"[+] Stocks: {data['total']} | BUY: {data['buy_count']} | WATCH: {data['watch_count']} | AVOID: {data['avoid_count']}")
    print(f"[+] Session: {data['session']} | {data['timestamp']}")

if __name__ == "__main__":
    main()
