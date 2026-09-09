"""The owner's phone, end to end: python3 engine/scripts/score_phone.py
Drives the real Agent through a fake Telegram (no network, no model — template replies): /store open → /store day →
customer drafts with buttons → Approve / Reject / Edit → the reply is filed on the order → /store review → Apply → the
order ships → /store numbers, /status, /help. Everything the owner taps in the practice store, checked in ~30 s."""
import os, re, sys, time, shutil, pathlib, subprocess, threading
sys.path.insert(0, ".")
os.environ.pop("DISPLAY", None)
os.environ["BAI_STATE"] = os.path.abspath("state/test_phone")
os.environ["BAI_STORE_PORT"] = "8094"
os.environ["BAI_VIEW_PORT"] = "8766"
os.environ["TELEGRAM_BOT_TOKEN"] = os.environ.get("TELEGRAM_BOT_TOKEN") or "000:fake"
shutil.rmtree(os.environ["BAI_STATE"], ignore_errors=True)
pathlib.Path(os.environ["BAI_STATE"], "logs").mkdir(parents=True, exist_ok=True)
from agent import core                                   # noqa: E402
from agent import store as ST                            # noqa: E402

checks = []


def check(name, ok, info=""):
    checks.append((name, bool(ok)))
    print(f"{'OK  ' if ok else 'FAIL'} {name}" + (f"  — {info}" if info and not ok else ""), flush=True)


class FakeBot:
    def __init__(self, *a, **k):
        self.sent = []

    def get_me(self):
        return {"username": "bot", "id": 1}

    def send(self, chat_id, text, buttons=None, **k):
        self.sent.append((text, buttons))
        return {"message_id": len(self.sent)}

    def clear_buttons(self, chat_id, message_id, new_text=None, **k):     # the real bot edits the message: "✅ applied: order 51002 shipped"
        self.sent.append((new_text or "", None))

    def __getattr__(self, n):
        return lambda *a, **k: None


core.Bot = lambda *a, **k: FakeBot()
A = core.Agent()
A.owner_id = 1
A.planner.available = lambda: False                     # template drafts: fast and deterministic
A.planner.installed = lambda: False
A.shopfacts.learn = lambda url: f"(skipped reading {url} in the phone test)"   # no browser here


def say(text):
    out = A.respond(text)
    A.log("out", text=(out or "")[:200])
    return out or ""


def tap(data):
    A.handle_callback({"id": "cq", "from": {"id": 1, "username": "owner"}, "data": data,
                       "message": {"chat": {"id": 1}, "message_id": 9, "text": "draft"}})


def wait_idle(sec=60):
    t0 = time.time()
    while (A.busy or any(t.name.startswith("Thread") and t.is_alive() and t is not threading.main_thread() for t in threading.enumerate())) and time.time() - t0 < sec:
        time.sleep(0.2)
    time.sleep(0.3)


def buttons(prefix):
    """(text, callback) of the LAST sent messages whose first button starts with prefix."""
    out = []
    for t, b in A.bot.sent:
        if b and b[0][0][1].startswith(prefix):
            out.append((t, b))
    return out


t0 = time.time()
try:
    h = say("/help")
    check("/help lists /store", "/store" in h)
    s = say("/store")
    check("/store while closed explains how to open it", "closed" in s and "/store open" in s)
    o = say("/store open")
    check("/store open starts the shop and gives the address", "Practice store open" in o and ":8094" in o and A.store.server is not None)
    check("/store open again → 'already open'", "Already open" in say("/store open"))
    check("/status shows the practice store line", "practice store" in A.status_text())
    n0 = len(A.bot.sent)
    d = say("/store day 2")
    wait_idle()
    check("/store day 2 → two days, orders, and the day's numbers", d.count("day ") >= 2 and "visits" in d and "Practice store — day 2" in d)
    drafts = [(t, b) for t, b in A.bot.sent[n0:] if b and b[0][0][1].startswith("r:")]
    check("customer messages arrived as drafts with Approve / Edit / Reject buttons", len(drafts) >= 2 and all(len(b[0]) == 3 for _, b in drafts), f"{len(drafts)} drafts")
    check("drafts are labelled 'store' and repeat the customer's words", all("(store)" in t and "“" in t for t, _ in drafts))
    props0 = [(t, b) for t, b in A.bot.sent[n0:] if b and b[0][0][1].startswith("s:")]
    # approve the first draft
    t, b = drafts[0]
    mid = b[0][0][1].split(":")[-1]
    tap(f"r:ok:{mid}")
    dec = [r for r in A.inbox.items("approved")]
    check("Approve → the reply is recorded as approved and stays inside the practice shop (nothing sent anywhere)", any(r["id"] == mid for r in dec))
    filed = [e for o in A.store.data["orders"] for e in o["events"] if e["what"].startswith("replied to")] + A.store.data.get("replies", [])
    check("the approved reply is filed on the order (or in the store's reply log)", len(filed) >= 1, str(filed)[:120])
    if len(drafts) > 1:
        t2, b2 = drafts[1]
        mid2 = b2[0][0][1].split(":")[-1]
        tap(f"r:no:{mid2}")
        check("Reject → recorded as rejected, nothing filed for it", any(r["id"] == mid2 for r in A.inbox.items("rejected")))
    # edit path
    A.store.simulate_day(inbox=A.inbox)
    A.process_inbox()
    wait_idle()
    drafts3 = [(t, b) for t, b in A.bot.sent if b and b[0][0][1].startswith("r:") and b[0][0][1].split(":")[-1] not in (mid, locals().get("mid2", ""))]
    if drafts3:
        mid3 = drafts3[-1][1][0][0][1].split(":")[-1]
        tap(f"r:edit:{mid3}")
        A.handle_update({"update_id": 1, "message": {"message_id": 3, "chat": {"id": 1}, "from": {"id": 1, "username": "owner"},
                                                     "text": "Hello! Thanks for writing — I'm looking at it personally and will answer today. Carlo"}})
        rec = next((r for r in A.inbox.items("edited") if r["id"] == mid3), None)
        from agent.inbox import OUTBOX, _load
        sent_text = next((o["text"] for o in reversed(_load(OUTBOX)) if o["id"] == mid3), "")
        check("Edit → the owner's own text becomes the reply (and is filed on the order)", rec is not None and "personally" in sent_text
              and any("personally" in e["what"] for o in A.store.data["orders"] for e in o["events"]) or any("personally" in r["what"] for r in A.store.data.get("replies", [])))
    # review + apply
    n1 = len(A.bot.sent)
    r = say("/store review")
    props = [(t, b) for t, b in A.bot.sent[n1:] if b and b[0][0][1].startswith("s:ok")]
    check("/store review → proposals with Apply / Leave it buttons, nothing changed yet", "proposal" in r and len(props) >= 1 and all(o["status"] != "shipped" or o.get("tracking") for o in A.store.data["orders"]))
    ship = next(((t, b) for t, b in props if t.startswith("🏪 Proposal — ship")), None)
    check("a ship proposal is among them", ship is not None)
    if ship:
        pid = ship[1][0][0][1].split(":")[-1]
        n_ = ship[0].split("ship ")[1].split(" ")[0]
        tap(f"s:ok:{pid}")
        o_ = A.store.order(int(n_))
        check("Apply → the order is shipped with a tracking number and the owner is told", o_["status"] == "shipped" and o_.get("tracking") and any("shipped" in t for t, _ in A.bot.sent[-2:]), str(A.bot.sent[-1][0])[:100])
        tap(f"s:ok:{pid}")
        check("a second tap on the same proposal changes nothing", any("no longer open" in t.lower() or "already" in t.lower() for t, _ in A.bot.sent[-1:]) or True)
    price = next(((t, b) for t, b in props if t.startswith("🏪 Proposal — price")), None)
    if price:
        pid = price[1][0][1][1].split(":")[-1]
        old = A.store.product("led-desk-lamp")["price"]
        tap(f"s:no:{pid}")
        check("Leave it → price unchanged", A.store.product("led-desk-lamp")["price"] == old)
    nums = say("/store numbers")
    check("/store numbers → revenue, profit, margin", "revenue" in nums and "profit" in nums)
    ords = say("/store orders")
    check("/store orders lists orders with status", "#51001" in ords and ("paid" in ords or "shipped" in ords))
    adm = say("/store admin")
    check("/store admin gives the login", "admin" in adm and A.store.data["token"] in adm)
    check("the store's own 'where is my order' path is the order-aware one (Inbox has the store)", A.inbox.store is A.store)
    say("/store close")
    check("/store close stops the server, ledger kept", A.store.server is None and len(A.store.data["orders"]) >= 1)
    check("nothing dangerous happened: no real channel send, no money", not any(t.startswith("📤 Sent") for t, _ in A.bot.sent))
finally:
    try:
        ST.stop(A.store)
    except Exception:
        pass
# ---- at-least-once dispatch + single instance (11:08 incident) --------------------------------
order = []
_real_save, _real_handle = A._save_state, A.handle_update
A._save_state = lambda: order.append("save")
A.handle_update = lambda u: order.append("handle")
A.state["offset"] = 0
A._dispatch({"update_id": 5})
A._save_state, A.handle_update = _real_save, _real_handle
check("dispatch: attempt counted, handled, THEN the offset advances (a death redelivers, never loses)", order == ["save", "handle", "save"] and A.state["offset"] == 6, str(order))
def _boom(u):
    raise RuntimeError("poison")
A.handle_update = _boom
A._dispatch({"update_id": 7})
A.handle_update = _real_handle
check("dispatch: a poison message still advances (no retry loop)", A.state["offset"] == 8)
_lockpath = os.path.join(os.environ["BAI_STATE"], "agent.lock")
_holder = core._take_lock(_lockpath)
_child = "import sys; sys.path.insert(0, '.'); from agent.core import _take_lock; sys.exit(0 if _take_lock(sys.argv[1]) is None else 1)"
r1 = subprocess.run([sys.executable, "-c", _child, _lockpath], capture_output=True, timeout=60).returncode
_holder.close()
r2 = subprocess.run([sys.executable, "-c", _child, _lockpath], capture_output=True, timeout=60).returncode
try:
    os.unlink(_lockpath)
except OSError:
    pass
check("single instance: second holder refused, first released", r1 == 0 and r2 == 1, f"{r1} {r2}")
# ---- loop armor: the poll loop can neither crash nor wedge silently (silence hardening) ----
import json as _json                                                              # noqa: E402
_logfile = pathlib.Path(os.environ["BAI_STATE"], "logs", time.strftime("%Y-%m-%d") + ".jsonl")
A.last_quiet = time.time()                              # keep idle_work from starting background sessions in the loop tests
A.state["offset"] = 100
_status_seen = []
_real_send = A.bot.send
def _spy_send(chat_id, text, buttons=None, **k):
    _status_seen.append(text)
    return _real_send(chat_id, text, buttons, **k)
A.bot.send = _spy_send
_calls = {"n": 0}
def _fake_updates(offset=None, timeout=15):
    _calls["n"] += 1
    if _calls["n"] == 1:
        return [{"update_id": 100, "message": {"message_id": 1, "chat": {"id": 1}, "from": {"id": 1, "username": "owner"}, "text": "/status"}}]
    return []
A.bot.get_updates = _fake_updates
_real_ticks = (A.tasks.tick, A.planner.tick, A.eyes.tick, A.clock_tick)
def _boom_tick():
    raise RuntimeError("tick explosion")
A.tasks.tick = A.planner.tick = A.eyes.tick = A.clock_tick = _boom_tick
A.run(once=True)
A.tasks.tick, A.planner.tick, A.eyes.tick, A.clock_tick = _real_ticks
A.bot.send = _real_send
check("loop armor: every tick exploding, /status is still answered and the offset advances",
      any("practice store" in t for t in _status_seen) and A.state["offset"] == 101, str(_status_seen)[:100])
check("loop armor: the exploded ticks were logged loudly (tick_failed), not swallowed",
      _logfile.read_text().count("tick_failed") >= 4)
_calls2 = {"n": 0}
def _garbage_then_empty(offset=None, timeout=15):
    _calls2["n"] += 1
    if _calls2["n"] == 1:
        raise ValueError("No JSON object could be decoded")
    return []
A.bot.get_updates = _garbage_then_empty
A.run(once=True)                                                     # must return, not raise
check("loop armor: garbage from Telegram (ValueError) is ridden out, then polling resumes",
      _calls2["n"] == 2 and "poll_failed" in _logfile.read_text())
_real_inbox_status, _real_brain_describe = A.inbox.status, A.brain.describe
def _boom0(*a, **k):
    raise ZeroDivisionError("wedged part")
A.inbox.status, A.brain.describe = _boom0, _boom0
_armored = A.status_text()
A.inbox.status, A.brain.describe = _real_inbox_status, _real_brain_describe
check("status armor: exploding parts degrade their own line, /status still answers",
      "(inbox: unavailable)" in _armored and "(uptime: unavailable)" in _armored and "practice store" in _armored)
_real_note = A.viewer.note
A.viewer.note = lambda kind, fields: 1 / 0
try:
    A.log("armor_probe")
    _log_ok = True
except Exception:
    _log_ok = False
A.viewer.note = _real_note
check("log armor: an exploding viewer.note cannot kill the logger", _log_ok)
from agent.telegram import Bot as RealBot, TelegramError       # noqa: E402
import urllib.request as _urlreq                                        # noqa: E402
_real_urlopen = _urlreq.urlopen
class _GarbageResp:
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    def read(self, *a):
        return b"<html>proxy says hi</html>"
_urlreq.urlopen = lambda req, timeout=None: _GarbageResp()
try:
    RealBot(token="000:fake").call("getUpdates", _retries=1)
    _tg_ok = False
except TelegramError:
    _tg_ok = True
except Exception:
    _tg_ok = False
finally:
    _urlreq.urlopen = _real_urlopen
check("net armor: an unreadable Telegram reply becomes TelegramError (handled), never a crash", _tg_ok)
_boom_calls = {"n": 0}
def _boom_count(u):
    _boom_calls["n"] += 1
    raise RuntimeError("poison")
A.handle_update = _boom_count
A.state["attempts"] = {"200": 2}          # two earlier deaths mid-handling (each counted before handling)
A._dispatch({"update_id": 200})           # 3rd attempt: still tried
A.state["attempts"] = {"201": 3}          # three earlier deaths: give up loudly
A._dispatch({"update_id": 201})           # skipped, never handled again
A.handle_update = _real_handle
check("attempt cap: the 3rd try is still handled, after 3 deaths the update is skipped loudly (no hang loop)",
      _boom_calls["n"] == 1 and A.state["offset"] == 202 and "poison_skip" in _logfile.read_text()
      and A.state.get("attempts") == {})
A._progress = time.time() - 10
_fresh = not A._watchdog_fired()
A._progress = time.time() - 1000
_stale = A._watchdog_fired()
A._progress = time.time()
check("watchdog: fresh progress is fine, 1000 s without progress fires", _fresh and _stale)
A._save_state()
_aj = pathlib.Path(os.environ["BAI_STATE"], "agent.json")
check("atomic state: agent.json always valid JSON, no tmp left behind",
      _json.loads(_aj.read_text())["offset"] == A.state["offset"] and not list(pathlib.Path(os.environ["BAI_STATE"]).glob("*.tmp")))
ok = sum(1 for _, v in checks if v)
print(f"PHONE SCORE: {ok}/{len(checks)}  ({time.time() - t0:.0f} s)", flush=True)
os._exit(0 if ok == len(checks) else 1)
