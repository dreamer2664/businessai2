"""Score the own-account skill on a fake site: python3 engine/scripts/score_accounts.py [--show]
sign-up form recognised & filled from the identity · marketing box untouched · code fetched from (fake) Gmail and entered ·
account remembered · second visit logs in instead · checkbox CAPTCHA passed · never-sign-up list · owner told once.
Item 6: approval gate (fakes always fine, real sites need the owner) + --drill N training rounds on fresh fakes."""
import os, re, sys, time
sys.path.insert(0, "."); sys.path.insert(0, "tests/signup")
os.environ.pop("DISPLAY", None); os.environ["BAI_STATE"] = "/tmp/bai_accounts_state"
os.environ.setdefault("BAI_ACCOUNT_EMAIL", "busynessai001@gmail.com"); os.environ.setdefault("BAI_ACCOUNT_PASSWORD", "BusinessAI001!")
import server as fake
from agent.tasks import Tasks
from agent.accounts import Accounts, Identity, NEVER_SIGN_UP
show = "--show" in sys.argv
drill_n = 0
for a in sys.argv[1:]:
    if a == "--drill":
        drill_n = 4
    elif a.startswith("--drill=") and a[8:].isdigit():
        drill_n = int(a[8:])
ok = total = 0
def check(name, cond, detail=""):
    global ok, total
    total += 1; ok += bool(cond); print(f"{'OK  ' if cond else 'MISS'} {name}" + (f"  — {detail}" if detail and (show or not cond) else ""), flush=True)

class FakeGoogle:
    """Reads the fake site's outbox like the Gmail API would."""
    def connected(self): return True
    def find_code(self, sender_hint="", tries=6, wait=20, **k):
        for _ in range(tries):
            for to, subj, body in reversed(fake.MAILBOX):
                m = re.search(r"code is (\d{6})", body)
                if m: return m.group(1), {"from": "FakeMarket", "subject": subj}
            time.sleep(0.5)
        return None, None
    def find_link(self, *a, **k): return None, None

idn = Identity()
check("identity: email/password from env", idn.ready() and idn.email.endswith("@gmail.com"))
check("identity: field mapping", idn.value_for("Email address") == idn.email and idn.value_for("Confirm password") == idn.password and idn.value_for("First name") == "Business" and idn.value_for("Phone number") is None)
check("never-sign-up list: paypal / google accounts", NEVER_SIGN_UP.search("https://www.paypal.com/signup") and NEVER_SIGN_UP.search("https://accounts.google.com/signup") and not NEVER_SIGN_UP.search("https://www.trustpilot.com/users/connect"))


srv = fake.serve(8098, captcha=False); srv2 = fake.serve(8099, captcha=True)
notes = []
T = Tasks(log=lambda k, **f: None)
A = Accounts(google=FakeGoogle(), log=lambda k, **f: None, notify=lambda t: notes.append(t))
if os.path.exists("/tmp/bai_accounts_state/accounts.json"): os.remove("/tmp/bai_accounts_state/accounts.json"); A.data = {"accounts": []}
check("gate: local fine / never refused / unknown real needs asking",
      A._gate("http://127.0.0.1:8098/") == (True, "ok") and A._gate("http://localhost:9/x") == (True, "ok")
      and A._gate("file:///home/user/shop.html") == (True, "ok")
      and A._gate("https://www.paypal.com/signup")[0] is False and A._gate("https://example.com/join") == (None, "ask"))
check("gate: allow/forget round-trip",
      A.allow_site("Example.com/join") == "example.com" and A._gate("https://example.com/join") == (True, "ok")
      and A.forget_site("https://www.example.com/") is True and A.forget_site("example.com") is False
      and A._gate("https://example.com/join") == (None, "ask"))
check("gate: junk is not a site", A.allow_site("not a site") is None and A.allow_site("") is None)
check("gate: money sites never approvable", A.allow_site("paypal.com") is None and A.allow_site("https://www.revolut.com/") is None)
ok0, note0 = A.ensure_account(None, "https://example.com/join")
check("gate: unknown real site refused with no way to ask (no browser touched)", ok0 is False and "/accounts allow" in note0, note0)
A2 = Accounts(google=FakeGoogle(), log=lambda k, **f: None, notify=lambda t: None, ask=lambda *a: "Never")
ok0b, note0b = A2.ensure_account(None, "https://shop.test/join")
check("gate: owner 'Never' remembered", ok0b is False and A2._gate("https://shop.test/join") == (False, "refused"), note0b)

if drill_n:
    wins, times = 0, []
    for i in range(drill_n):
        port = 18200 + i
        fake.STATE["captcha_ok"].clear()
        A.data = {"accounts": []}                                   # every round signs up fresh (fakes first, always)
        srv = fake.serve(port, captcha=bool(i % 2))
        t0 = time.time()
        def run(p=port):
            b = T.browser()
            okd, noted = A.ensure_account(b, f"http://127.0.0.1:{p}/", why="drill round")
            return okd, noted, b.page.url
        try:
            okd, noted, url = T.on_hands(run, timeout=120)
        except Exception as e:
            okd, noted, url = False, f"error: {e}"[:80], ""
        dt = time.time() - t0
        srv.shutdown(); srv.server_close()
        good = bool(okd and url.endswith("/welcome"))
        wins += good
        if good:
            times.append(dt)
        print(f"drill {i + 1}/{drill_n} ({'captcha' if i % 2 else 'plain'}): {'OK' if good else 'MISS'} {dt:.0f}s {noted}", flush=True)
    med = sorted(times)[len(times) // 2] if times else 0
    print(f"DRILL: {wins}/{drill_n} fresh fake sign-ups passed (median {med:.0f}s)")
    T.on_hands(T.close_browser, timeout=30)
    sys.exit(0 if wins == drill_n else 1)
t0 = time.time()
def run1():
    b = T.browser()
    return A.ensure_account(b, "http://127.0.0.1:8098/", why="to read member-only reviews"), b.page.url, b.extract_text()[:200]
(ok1, note1), url1, txt1 = T.on_hands(run1, timeout=120)
check("sign-up: completed to the welcome page", ok1 and url1.endswith("/welcome"), f"{ok1} {note1} {url1}")
u = fake.STATE["users"].get(idn.email, {})
check("sign-up: identity typed (email, password, names, terms)", u.get("password") == idn.password and u.get("first") == "Business" and u.get("terms"), str({k: v for k, v in u.items() if k != 'password'}))
check("sign-up: marketing box NOT ticked", not u.get("news"))
check("sign-up: code fetched from mailbox and entered", "Welcome" in txt1)
check("memory: account remembered as active", (A.known("http://127.0.0.1:8098/x") or {}).get("status") == "active", str(A.data))
check("owner told once, one line", len(notes) == 1 and "creating an account" in notes[0], str(notes))
def run2():
    b = T.browser()
    return A.ensure_account(b, "http://127.0.0.1:8098/some/page"), b.page.url
(ok2, note2), url2 = T.on_hands(run2, timeout=120)
check("second visit: logs in (no new sign-up, owner not told again)", ok2 and note2 == "logged in" and url2.endswith("/welcome") and len(notes) == 1, f"{ok2} {note2} {url2}")
def run3():
    b = T.browser()
    return A.ensure_account(b, "http://127.0.0.1:8099/", why="captcha test"), b.page.url
(ok3, note3), url3 = T.on_hands(run3, timeout=120)
check("checkbox CAPTCHA passed, then signed up", ok3 and url3.endswith("/welcome"), f"{ok3} {note3} {url3}")
def run4():
    b = T.browser()
    return A.ensure_account(b, "https://www.paypal.com/signup")
ok4, note4 = T.on_hands(run4, timeout=30)
check("refuses money sites", not ok4 and "never-sign-up" in note4, note4)
T.on_hands(T.close_browser, timeout=30)
print(A.list_text() if show else "")
print(f"ACCOUNTS SCORE: {ok}/{total}  ({time.time() - t0:.0f}s)")
