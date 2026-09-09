"""Score the practice store end to end: python3 engine/scripts/score_store.py [--model]
Without --model: everything that needs no thinking model (shop works, ledger, days, proposals, reading its own pages,
operator on the store front, safety). With --model: also the customer replies from store customers (8 messages, incl. order questions)."""
import base64, http.cookiejar, json, os, re, sys, time, urllib.parse, urllib.request
sys.path.insert(0, ".")
os.environ.pop("DISPLAY", None)
os.environ["BAI_STATE"] = os.environ.get("BAI_STATE", "/tmp/bai_state_score_store")
from agent import store as ST
from agent.inbox import Inbox
from agent.shopfacts import ShopFacts
from agent.tasks import Tasks
from agent.operator import Operator

use_model = "--model" in sys.argv
PORT = 8097
checks = []


def check(name, ok, info=""):
    checks.append((name, bool(ok)))
    print(f"{'OK  ' if ok else 'FAIL'} {name}" + (f"  — {info}" if info else ""), flush=True)


import pathlib, shutil
shutil.rmtree(os.environ["BAI_STATE"], ignore_errors=True)          # a clean state for every run
pathlib.Path(os.environ["BAI_STATE"]).mkdir(parents=True, exist_ok=True)
from agent import config as _cfg
_cfg.ensure_dirs()
I = Inbox(planner=None)
S = ST.Store(log=lambda k, **f: None)
S.reset()
srv, url = ST.start(S, inbox=I, port=PORT)
cj = http.cookiejar.CookieJar(); op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
get = lambda p: op.open(url.rstrip("/") + p, timeout=10)
post = lambda p, **f: op.open(urllib.request.Request(url.rstrip("/") + p, data=urllib.parse.urlencode(f).encode()), timeout=10)
t0 = time.time()
try:
    # 1. the shop works like a shop
    b = get("/").read().decode(); check("front page lists the catalogue", b.count("class=card") == 5)
    b = get("/p/stoneware-mug").read().decode(); check("product page: price, options, details", "€ 14,90" in b and "Charcoal" in b and "Dishwasher safe" in b)
    r = post("/cart/add", id="stoneware-mug", option="Colour: Sand", qty="2"); check("add to cart → cart page", r.geturl().endswith("/cart") and "2 items" in r.read().decode())
    r = post("/checkout/pay", name="Anna Rossi", email="anna@example.com", country="IT"); b = r.read().decode()
    check("checkout (practice payment) → order page, Italian shipping € 3,90 not free under € 39", "/order/51001" in r.geturl() and "€ 3,90" in b and "€ 33,70" in b)
    check("stock reserved by the order", S.product("stoneware-mug")["stock"] == 19)
    post("/cart/add", id="cork-phone-case", option="Model: iPhone 14", qty="1")
    b = post("/checkout/pay", name="Jo", email="jo@example.com", country="GB").read().decode(); check("checkout outside the EU refused (shop says not yet)", "cannot ship" in b)
    try:
        get("/admin"); check("admin needs a login", False)
    except urllib.error.HTTPError as e:
        check("admin needs a login", e.code == 401)
    auth = {"Authorization": "Basic " + base64.b64encode(f"admin:{S.data['token']}".encode()).decode()}
    b = op.open(urllib.request.Request(url + "admin", headers=auth)).read().decode(); check("admin panel shows the order", "#51001" in b and "Anna Rossi" in b)
    # 2. days pass: visits, orders, messages; numbers add up
    tot_orders = 0; tot_msgs = 0
    for _ in range(4):
        r = S.simulate_day(inbox=I); tot_orders += len(r["orders"]); tot_msgs += len(r["messages"])
    n = S.numbers()
    check("4 practice days: visits, orders and customer messages happened", n["visits"] > 100 and tot_orders >= 3 and tot_msgs >= 4, f"visits {n['visits']}, orders {tot_orders}, messages {tot_msgs}")
    calc = round(n["revenue"] - n["cogs"] - n["shipping_cost"] - n["fees"] - n["losses"], 2)
    check("profit = revenue − goods − shipping − fees − refund losses", abs(calc - n["profit"]) < 0.02, f"{n['profit']}")
    check("every paid order's total = lines + shipping", all(abs(sum(l["qty"] * l["price"] for l in o["lines"]) + o["shipping"] - o["total"]) < 0.01 for o in S.data["orders"]))
    check("store customer messages landed in the inbox as channel 'store'", all(m["channel"] == "store" for m in I.items("new")) and len(I.items("new")) == tot_msgs)
    # 3. the AI's review proposes the right things, and nothing changes without a tap
    stock_before = {p["id"]: p["stock"] for p in S.products()}
    props = S.review()
    kinds = {(p["kind"], p["target"]) for p in props}
    check("proposes to ship every paid order", all(("ship", str(o["n"])) in kinds for o in S.data["orders"] if o["status"] == "paid"))
    check("proposes to reorder the sold-out and the low-stock product", ("stock", "beeswax-wraps") in kinds and ("stock", "led-desk-lamp") in kinds)
    check("proposes a price fix only where the margin is thin (lamp 54 %)", [p["target"] for p in props if p["kind"] == "price"] == ["led-desk-lamp"])
    check("proposals change nothing by themselves", {p["id"]: p["stock"] for p in S.products()} == stock_before and all(o["status"] == "paid" for o in S.data["orders"]))
    ship = next(p for p in props if p["kind"] == "ship"); out = S.apply(ship["id"])
    check("owner's tap applies a proposal (order shipped, tracking assigned)", "shipped" in out and S.order(int(ship["target"]))["status"] == "shipped" and S.order(int(ship["target"])).get("tracking"))
    check("a second tap on the same proposal does nothing", "no longer open" in S.apply(ship["id"]))
    price = next(p for p in props if p["kind"] == "price"); old = S.product("led-desk-lamp")["price"]; S.reject(price["id"])
    check("'Leave it' keeps the price", S.product("led-desk-lamp")["price"] == old and S.proposal(price["id"])["status"] == "rejected")
    check("review does not repeat open proposals", not [p for p in S.review() if p["kind"] == "stock"])
    check("ledger survives a restart", ST.Store(log=lambda k, **f: None).data["orders"][0]["n"] == 51001 and ST.Store(log=lambda k, **f: None).data["day"] == 4)
    # 3b. order questions are answered from the order system (no model: templates + safety flags)
    I3 = Inbox(planner=None, store=S)
    paid = next(o for o in S.data["orders"] if o["status"] == "paid"); shipped = S.order(int(ship["target"]))
    d = I3.draft({"id": "t", "from": paid["customer"]["email"], "channel": "store", "text": f"Where is my order {paid['n']}?"})
    check("'where is my order' on an unshipped order → 'still in the warehouse' (never 'I will check')", "warehouse" in d["text"] and "will check" not in d["text"] and not d["checks"])
    d = I3.draft({"id": "t", "from": shipped["customer"]["email"], "channel": "store", "text": f"Where is my order {shipped['n']}?"})
    check("'where is my order' on a shipped order → the real tracking number", shipped["tracking"] in d["text"] and not d["checks"])
    d = I3.draft({"id": "t", "from": "stranger@example.com", "channel": "store", "text": f"Where is my order {shipped['n']}?"})
    check("someone else's e-mail asks about that order → nothing revealed", shipped["tracking"] not in d["text"] and "shipped" not in d["text"].split(chr(10) + chr(10))[1] and "e-mail address" in d["text"])
    d = I3.draft({"id": "t", "from": shipped["customer"]["email"], "channel": "store", "text": f"Please cancel order {shipped['n']}."})
    check("cancel a shipped order → cannot cancel, return within 30 days", "cannot be cancelled" in d["text"] and "30 days" in d["text"] and S.proposal_for_message("cancel_or_change", shipped["n"]) is None)
    d = I3.draft({"id": "t", "from": paid["customer"]["email"], "channel": "store", "text": f"Please cancel order {paid['n']}."})
    prop = S.proposal_for_message("cancel_or_change", paid["n"])
    check("cancel an unshipped order → reply says it will be cancelled + a 'cancel' proposal for the owner (nothing changes until the tap)", "cancelled and refunded in full" in d["text"] and prop and prop["kind"] == "cancel" and S.order(paid["n"])["status"] == "paid")
    stock0 = S.product(paid["lines"][0]["id"])["stock"]; out = S.apply(prop["id"])
    check("owner taps → order cancelled, stock back on the shelf", "cancelled" in out and S.order(paid["n"])["status"] == "cancelled" and S.product(paid["lines"][0]["id"])["stock"] == stock0 + paid["lines"][0]["qty"])
    c = {"kind": "where_is_my_order", "needs": [], "order_no": str(paid["n"]), "order": {k: v for k, v in S.order_facts(shipped["n"]).items() if k != "order"}}
    c["order"]["status"] = "paid"; c["order"]["tracking"] = ""
    check("safety flag: model claims 'shipped' while the ledger says paid", any("warehouse" in f for f in I3._check(f"Your order {paid['n']} has been shipped and is on its way!", c, "")))
    check("safety flag: model says 'I will check your order' although the status is known", any("already known" in f for f in I3._check(f"Sorry! I will check your order {paid['n']} and get back to you.", c, "")))
    d = I3.draft({"id": "t", "from": shipped["customer"]["email"], "channel": "store", "text": "Where is my order? Nothing arrived yet."})
    check("no order number, but the sender's address has one live order → answered for that order", str(shipped["n"]) in d["text"] and shipped["tracking"] in d["text"] and not d["checks"])
    d = I3.draft({"id": "t", "from": shipped["customer"]["email"], "channel": "store", "text": "Where is my order 59999?"})
    check("a number that is not in the system → 'cannot find it, check the confirmation e-mail'", "cannot find" in d["text"] and "59999" in d["text"] and not d["checks"])
    d = I3.draft({"id": "t", "from": "nobody@example.com", "channel": "store", "text": "Where is my order?"})
    check("unknown address, no number → asks for the number, guesses nothing", "cannot find any order" in d["text"] and "warehouse" not in d["text"] and not d["checks"])
    d = I3.draft({"id": "t", "from": "x@example.com", "channel": "store", "text": "I want to cancel order 51002, I ordered the wrong model."})
    check("'cancel — I ordered the wrong model' is a cancellation, not a damage report", d["kind"] == "cancel_or_change" and "photo" not in d["text"])
    p0 = S.numbers()["profit"]; S.set_status(shipped["n"], "refunded"); n2 = S.numbers()
    fee = 0.029 * shipped["total"] + 0.30; post = 2.9 + 0.35 * sum(l["qty"] for l in shipped["lines"]); goods = sum(l["qty"] * l["cost"] for l in shipped["lines"])
    margin_before = shipped["total"] - goods - post - fee                       # what this order contributed while it counted as sold
    check("refunding a shipped order: its margin disappears AND the fee, postage and goods are lost", n2["refunded"] == 1 and abs((p0 - n2["profit"]) - (margin_before + fee + post + goods)) < 0.05, f"profit {p0} → {n2['profit']}, losses {n2['losses']}")
    a, b = S.propose("stock", "x", 1, "t"), S.propose("stock", "y", 1, "t")
    check("two proposals in the same millisecond get different ids", a["id"] != b["id"]); S.reject(a["id"]); S.reject(b["id"])
    T = Tasks()
    try:
        T.browser(); BROWSER_OK = True
    except Exception:
        BROWSER_OK = False
        print("(no browser here — section 4 skipped; run on the PC for the full score)")
    if BROWSER_OK:
        # 4. the AI reads its own store like any shop (needs a browser)
        F = ShopFacts(tasks=T, log=lambda k, **f: None)
        rep = F.learn(url)
        check("/shop on the store: help facts + 5 product pages (no model)", len(F.products) == 5 and F.covers("returns & refunds") and F.covers("delivery time") and F.covers("where we ship"), f"{len(F.facts)} facts")
        lamp = next(p for p in F.products if "Lamp" in p["name"])
        check("product page details kept word for word", any("no power adapter included" in d for d in lamp["details"]) and lamp["price"] == "€ 39,00")
        check("matches 'the cork case' to the product, not 'phone number'", F.match_products("Does the cork case fit the iPhone 14?") and not F.match_products("Is there a phone number?"))
    if BROWSER_OK:   # sections 5-6 need the browser too
        # 5. the operator works the store front (model-free rules)
        O = Operator(None, tasks=T, log=lambda k, **f: None)
        O._browser_open(url); seen = O._see("browser")
        step = O._obvious_step("Open the first product on the page and tell me its price", seen)
        ok = step and step["step"] == "click" and "Bamboo" in step["target"]
        if ok:
            O._act_click("browser", step["target"], seen); s2 = O._see("browser"); ok = "12,90" in s2["fulltext"]
        check("operator: 'open the first product' → toothbrush set page with its price", ok)
        O.history = []
        O._browser_open(url + "p/led-desk-lamp"); seen = O._see("browser")
        from agent.operator import DANGER
        labels = " | ".join(str(it) for it in seen["items"])
        check("'Add to cart' is visible to the operator and classed as a money/cart action (owner is asked first)", "Add to cart" in labels and bool(DANGER.search("Add to cart")) and not DANGER.search("Details"))
        T.close_browser()
        # 6. customer replies from store customers (model)
        if use_model:
            from agent.planner import Planner
            P = Planner(); I2 = Inbox(planner=P, shopfacts=F, store=S)
            paid2 = next(o for o in S.data["orders"] if o["status"] == "paid")
            good = 0; rows = [
                ("c@example.com", "How long does delivery to Germany take and what does it cost?", r"4.6 business days|4–6", r"7-15"),
                ("c@example.com", "Is the LED desk lamp still in stock? The page says only a few left.", r"3 left|only 3|few left|in stock|check", r"7-15"),
                ("c@example.com", "Does the desk lamp come with a power adapter?", r"\bno\b|not included|without", r"yes, it comes"),
                ("c@example.com", "Can I still return the mug after 3 weeks? Who pays the return shipping?", r"30 days", r"7-15"),
                ("c@example.com", "Do you ship to Switzerland? I'd like the cork phone case.", r"not yet|2027|do not ship|don't ship|only .*eu", r"yes, we ship"),
                (paid2["customer"]["email"], f"Hi, where is my order {paid2['n']}? Nothing arrived yet.", r"warehouse|not (yet |been )?shipped|has not (yet )?left", r"7-15|will check|has been shipped|on its way"),
                (shipped["customer"]["email"], f"Where is order {shipped['n']}? Can you give me a tracking number?", shipped["tracking"].lower(), r"7-15|will check|warehouse"),
                (shipped["customer"]["email"], f"I want to cancel order {shipped['n']}, I changed my mind.", r"cannot be cancel|can no longer|already (been )?shipped|already left", r"will be cancelled|has been cancelled"),
            ]
            try:
                for frm, msg, must, mustnot in rows:
                    d = I2.draft({"id": "t", "from": frm, "channel": "store", "text": msg}); low = d["text"].lower()
                    ok = re.search(must, low) and not re.search(mustnot, low) and not d["checks"]; good += bool(ok)
                    print(f"   {'ok ' if ok else 'BAD'} {msg[:55]} -> {d['text'].split(chr(10)+chr(10))[1][:150 if ok else 600]!r} {d['checks']}", flush=True)
            finally:
                P.stop()
            check("store customers answered from the store's own pages and order system (≥ 7/8)", good >= 7, f"{good}/8")
finally:
    ST.stop(S)
ok = sum(1 for _, v in checks if v)
print(f"STORE SCORE: {ok}/{len(checks)}  ({time.time() - t0:.0f} s)")
