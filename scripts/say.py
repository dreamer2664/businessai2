#!/usr/bin/env python3
"""Talk to the builder from the terminal (no chat needed).

    python3 scripts/say.py "your message"      → leaves a note for the builder (owner/inbox.md in the repo)
    python3 scripts/say.py                     → prints the builder's replies (builder/replies.md)
    python3 scripts/say.py --watch             → keeps printing new replies every 30 s (Ctrl-C to stop)

Everything goes through the GitHub repo with the token in .secrets/env — no git set-up needed on this side.
The builder reads owner/inbox.md at the start of every turn; a one-word "go" in the chat wakes it.
"""
import base64
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _env():
    env = dict(os.environ)
    f = ROOT / ".secrets" / "env"
    if f.exists():
        for line in f.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return env


ENV = _env()
OWNER = ENV.get("GH_OWNER", "dreamer2664")
REPO = ENV.get("GH_REPO", "businessai2")
TOKEN = ENV.get("GITHUB_TOKEN", "")
API = f"https://api.github.com/repos/{OWNER}/{REPO}/contents/"


def _req(path, method="GET", body=None, raw=False):
    req = urllib.request.Request(API + path + "?ref=main", method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/vnd.github.raw" if raw else "application/vnd.github+json")
    req.add_header("User-Agent", "businessai-say")
    data = json.dumps(body).encode() if body is not None else None
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=data, timeout=30) as r:
            out = r.read()
            return out.decode() if raw else json.loads(out)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise SystemExit(f"GitHub said {e.code}: {e.read()[:200].decode(errors='replace')}")


def read_replies():
    txt = _req("builder/replies.md", raw=True)
    return txt or "(no replies yet)"


def send(msg):
    if not TOKEN:
        raise SystemExit("No GITHUB_TOKEN in .secrets/env — I can't reach the repo from here.")
    cur = _req("owner/inbox.md")
    old = base64.b64decode(cur["content"]).decode() if cur else "# Notes from the owner to the builder\n\n"
    stamp = time.strftime("%Y-%m-%d %H:%M")
    new = old.rstrip("\n") + f"\n- {stamp} (owner): {msg.strip()}\n"
    body = {"message": f"owner note {stamp}", "content": base64.b64encode(new.encode()).decode()}
    if cur:
        body["sha"] = cur["sha"]
    _req("owner/inbox.md", method="PUT", body=body)
    print("✅ Sent. I read it at the start of my next turn — a one-word “go” in the chat wakes me.")
    print("   Read my replies:  python3 scripts/say.py        (or --watch to keep listening)")


def watch():
    last = ""
    print("Listening for the builder's replies (Ctrl-C to stop)…")
    while True:
        try:
            txt = read_replies()
            if txt != last:
                new = txt[len(last):] if txt.startswith(last) else txt
                print(new.strip("\n"))
                last = txt
        except SystemExit as e:
            print(e)
        time.sleep(30)


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--watch":
        watch()
    elif args:
        send(" ".join(args))
    else:
        print(read_replies())
