#!/usr/bin/env python3
"""Builder heartbeat: render builder/heartbeat.json into the shared Google Doc (create once, rewrite per checkpoint).
Usage: python3 scripts/heartbeat.py   (prints the doc link)
"""
import datetime
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from agent.google import Google  # noqa: E402

HB = ROOT / "builder" / "heartbeat.json"
STATE = ROOT / "state" / "heartbeat_doc.txt"

def html(hb):
    rows = "\n".join(f"<tr><td>{r[0]}</td><td>{r[1]}</td><td>{r[2]}</td><td>{r[3]}</td></tr>" for r in hb["rows"])
    bullets = "\n".join(f"<li>{b}</li>" for b in hb["latest"])
    return f"""<html><body>
<h1>BusinessAI — builder heartbeat</h1>
<p>Updated {hb['updated']} · branch {hb.get('branch', '?')} · main stays green</p>
<h2>Marathon progress: {hb.get('pct', 0)}%</h2>
<table border="1" cellpadding="6" cellspacing="0"><tr><th>#</th><th>Item</th><th>%</th><th>Status</th></tr>
{rows}</table>
<h2>Latest</h2>
<ul>{bullets}</ul>
</body></html>"""

def main():
    hb = json.loads(HB.read_text())
    hb["updated"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    g = Google()
    if not g.connected():
        raise SystemExit("Google not connected")
    if STATE.exists():
        file_id, link = STATE.read_text().splitlines()[:2]
        g.files_update(file_id.strip(), html(hb).encode(), mime="text/html")
        print("updated:", link.strip())
    else:
        d = g.upload_text(html(hb), "BusinessAI — builder heartbeat", mime="text/html")
        g.share_link(d["id"])
        STATE.write_text(d["id"] + "\n" + d["link"] + "\n")
        print("created:", d["link"])

if __name__ == "__main__":
    main()
