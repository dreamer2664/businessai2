"""Wall memory — which sites and search engines walled me lately, so I stop knocking on the same doors.

Before: every job met the same walls again (Brave's CAPTCHA cost ~9 s on every search; Etsy walled twice per research; a
shop that showed DataDome at 10:00 was opened again at 10:05). Now one small file (state/walls.json) remembers, per host:
how many walls, which kind, when the last one was, and when the last clean read was. Three uses:

  order(items)     candidates from a search, walled hosts moved to the end (a clean site first, the cranky one if needed)
  skip(host)       True when the host walled twice in the last 2 h or four times in 24 h — the next site, not a third knock.
                   Never applied to a page the owner asked for by link (essential pages still get the solver + owner tap).
  engine_order()   the search engines, the ones that walled in the last 6 h last

A clean read forgives: it halves the count, and the host is out of `skip` again. Entries older than 7 days are dropped.
Text for the owner: /walls. Nothing here tries to pass a wall — it only avoids them.
"""
import json
import time
import urllib.parse

from . import config

FILE = config.STATE_DIR / "walls.json"
KEEP_DAYS = 7


def host_of(url):
    if not url:
        return ""
    if "://" not in url:
        return url.lower().removeprefix("www.")
    try:
        return (urllib.parse.urlparse(url).hostname or "").lower().removeprefix("www.")
    except Exception:
        return ""


class WallMemory:
    def __init__(self, path=None, clock=None, log=None):
        self.path = path or FILE
        self.clock = clock or time.time
        self.log = log or (lambda _k, **f: None)
        self.hosts = {}
        self._load()

    # ---- storage ---------------------------------------------------------------------
    def _load(self):
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
            self.hosts = d.get("hosts", {}) if isinstance(d, dict) else {}
        except Exception:
            self.hosts = {}
        self.forget_old()

    def _save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps({"hosts": self.hosts}, ensure_ascii=False, indent=0), encoding="utf-8")
        except Exception as e:
            self.log("walls_save_failed", error=str(e)[:80])

    def forget_old(self):
        cut = self.clock() - KEEP_DAYS * 86400
        for h in [h for h, r in self.hosts.items() if r.get("last", 0) < cut and r.get("ok", 0) < cut]:
            self.hosts.pop(h, None)

    # ---- recording ------------------------------------------------------------------
    def hit(self, url, kind="captcha"):
        """A wall was met on this host."""
        h = host_of(url)
        if not h:
            return
        r = self.hosts.setdefault(h, {"n": 0, "times": [], "kind": kind, "last": 0, "ok": 0})
        now = self.clock()
        r["n"] = r.get("n", 0) + 1
        r["times"] = [t for t in r.get("times", []) if t > now - 86400][-19:] + [now]
        r["kind"] = kind
        r["last"] = now
        self._save()
        self.log("wall_remembered", host=h, wall=kind, n24=len(r["times"]))

    def clear(self, url):
        """A clean read on this host: forgive half, remember the time."""
        h = host_of(url)
        r = self.hosts.get(h)
        if not r:
            return
        r["ok"] = self.clock()
        r["times"] = r.get("times", [])[len(r.get("times", [])) // 2 + (1 if r.get("times") else 0):]  # drop the older half + one
        r["n"] = max(0, r.get("n", 0) // 2)
        if not r["times"] and not r["n"]:
            self.hosts.pop(h, None)
        self._save()

    def forget(self, url=None):
        """/walls forget [site] — start fresh for one host or all."""
        if url:
            self.hosts.pop(host_of(url), None)
        else:
            self.hosts = {}
        self._save()

    # ---- questions --------------------------------------------------------------------
    def recent(self, url, hours=24):
        r = self.hosts.get(host_of(url))
        if not r:
            return 0
        cut = self.clock() - hours * 3600
        return sum(1 for t in r.get("times", []) if t > cut)

    def skip(self, url):
        """Leave this host alone for now? Two walls in 2 h, or four in 24 h — and no clean read since the last wall."""
        h = host_of(url)
        r = self.hosts.get(h)
        if not r or r.get("ok", 0) > r.get("last", 0):
            return False
        return self.recent(h, 2) >= 2 or self.recent(h, 24) >= 4

    def order(self, items, key=None):
        """Same items, hosts that walled in the last 24 h moved to the end (stable otherwise). key: item → url."""
        key = key or (lambda it: it["url"] if isinstance(it, dict) else it)
        return sorted(items, key=lambda it: (self.recent(key(it), 24) > 0, self.skip(key(it))))

    def engine_order(self, engines, hosts):
        """engines: names in the default order; hosts: name → search URL. Engines that walled in the last 6 h go last."""
        return sorted(engines, key=lambda e: self.recent(hosts.get(e, ""), 6))

    # ---- for the owner ----------------------------------------------------------------
    def text(self, limit=8):
        rows = sorted(((r.get("last", 0), h, r) for h, r in self.hosts.items() if r.get("times")), reverse=True)[:limit]
        if not rows:
            return "🧱 No walls remembered — no site has blocked me in the last 7 days."
        now = self.clock()

        def ago(t):
            m = int((now - t) // 60)
            return f"{m} min ago" if m < 60 else (f"{m // 60} h ago" if m < 1440 else f"{m // 1440} d ago")
        lines = ["🧱 Sites that walled me lately (I put them last, and skip them for a while after two walls):"]
        for last, h, r in rows:
            n24 = self.recent(h, 24)
            lines.append(f"• {h} — {n24}× in 24 h ({r.get('kind', 'captcha')}), last {ago(last)}" + (" · skipping for now" if self.skip(h) else "") +
                         (f" · clean read {ago(r['ok'])}" if r.get("ok") else ""))
        lines.append("Say `/walls forget` (or `/walls forget site.com`) to start fresh.")
        return "\n".join(lines)
