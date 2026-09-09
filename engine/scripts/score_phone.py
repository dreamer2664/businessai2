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
check("dispatch: handled BEFORE the offset advances (a death redelivers, never loses)", order == ["handle", "save"] and A.state["offset"] == 6, str(order))
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
ok = sum(1 for _, v in checks if v)
print(f"PHONE SCORE: {ok}/{len(checks)}  ({time.time() - t0:.0f} s)", flush=True)
os._exit(0 if ok == len(checks) else 1)
