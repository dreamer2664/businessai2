"""The owner's 2026-09-10 session, check by check (docs/DIAGNOSIS_2026-09-10.md). Offline. Run: python3 engine/scripts/score_session.py"""
import os, sys, re, time
os.environ["BAI_STATE"] = "/tmp/bai_session_state"; os.environ["BAI_STORE_PORT"] = "8193"
sys.path.insert(0, ".")
import shutil; shutil.rmtree("/tmp/bai_session_state", ignore_errors=True)
from agent import brief as B
from agent import mind as M
from agent.pace import Pace
from agent.talk import Talk
from agent.browser import Browser, BrowserError
from agent.tasks import Tasks
from agent.deals import matches, rank_key, DealHunter

ok = tot = 0
def check(name, cond, got=""):
    global ok, tot
    tot += 1; ok += bool(cond); print(("✅" if cond else "❌"), name, "" if cond else f"→ {str(got)[:200]}")

OWNER = ("I want you to find me the best deals for this list that I'm about to send. Look in subito.it, Vinted, Facebook marketplace, etc. "
         "Facebook marketplace is only ok if they're in the city of BARLETTA. Also other used reselling websites like wallapop and others. "
         "Take around 5-6 hours. Build me a detailed google doc obviously.")

# --- 1/2 pace ------------------------------------------------------------------------------------------------
p = B.parse_pace(OWNER)
check("#1 'subito.it' is a site, not 'right away' → not quick", p["pace"] != "quick", p)
check("#2 'take around 5-6 hours' → floor 5 h, budget 6 h, slow", p["pace"] == "slow" and p["floor_min"] == 300 and p["budget_min"] == 360, p)
check("'fallo subito' is still quick", B.parse_pace("fallo subito, cerca tazze")["pace"] == "quick")
check("'cheap mugs on subito and vinted' is normal", B.parse_pace("find me cheap mugs on subito and vinted")["pace"] == "normal")
check("quoted 'quick' inside a complaint is not a wish", B.parse_pace('I said "take 5-6 hours" and you put "quick" as timing')["pace"] == "slow")
check("'Take it very slowly!' → slow", B.parse_pace("Take it very slowly!")["pace"] == "slow")

# --- 3/4 interrupts --------------------------------------------------------------------------------------------
m = M.Mind(); m.pace = Pace()
m.pace.set({"pace": "quick", "deadline_min": None, "budget_min": None, "floor_min": None, "why": ""}, "x")
m.begin("Find deals", "research", ["a", "b"])
w, r = m.interrupt('Hey, I said "take 5-6 hours" and you put "quick" as timing... Change that.')
check("#3 complaint about 'quick' → slows down (never 'Speeding up')", r.startswith("Slowing down") and "5 h" in r and m.pace.mode == "slow" and m.pace.floor_min == 300, (w, r, m.pace.mode))
w, r = m.interrupt("No, I said slow down!!")
check("#4 'No, I said slow down!!' mid-job → pace answer, not queued", w == "hurry" and r.startswith("Slowing down"), (w, r))
w, r = m.interrupt("hurry up")
check("'hurry up' still speeds up", r.startswith("Speeding up") and m.pace.mode == "quick", r)
w, r = m.interrupt("stop"); w2, r2 = m.interrupt("stop"); w3, r3 = m.interrupt("stop")
check("#5 second 'stop' → an honest 'still stopping' line, third → drop", w == "stop" and w2 == "stop_again" and "Still stopping" in r2 and w3 == "stop_again", (w, w2, w3))

# --- 4b pace-only messages are never jobs ---------------------------------------------------------------------
Bf = B.Brief()
for t in ("No, I said slow down!!", "Slow down, take it slowly", "Take it very slowly!", "take 5-6 hours"):
    check(f"pace-only {t!r} → chat, not a task", Bf.make(t)["kind"] == "chat" and Bf.make(t).get("pace_only"), Bf.make(t)["kind"])
check("'slow cooker deals on vinted' is NOT pace-only", not B.pace_only("slow cooker deals on vinted"))

# --- 6/10 the list that is about to arrive ---------------------------------------------------------------------
b = Bf.make(OWNER)
check("#6 'the list I'm about to send' → plan waits for the list", b.get("needs_list") and b["steps"][0].lower().startswith("wait for your list"), b["steps"][:1])
check("#6 topic is the items, never the Barletta sentence", "barletta" not in b["topic"].lower() and "facebook" not in b["topic"].lower(), b["topic"])
check("#6 Barletta rule kept as a condition", any("barletta" in c.lower() for c in b["constraints"]), b["constraints"])
check("#10 'I want you to find…' is not a condition", not any(c.lower().startswith("i want you") for c in b["constraints"]), b["constraints"])
check("sites read from the message", set(b["sites"]) >= {"subito", "vinted", "wallapop", "facebook marketplace"}, b["sites"])
items = B.Brief.list_items("nintendo switch — max 150\nps4 controller\niphone 12 under 300\n- dyson v8")
check("the list parses: names + price limits", [i["name"] for i in items] == ["nintendo switch", "ps4 controller", "iphone 12", "dyson v8"] and items[0]["max"] == 150 and items[2]["max"] == 300, items)
check("a comma list parses too", len(B.Brief.list_items("nintendo switch, ps4 controller, dyson v8")) == 3)
check("'ok' / 'go' / 'stop' are not one-item lists", not B.Brief.list_items("ok") and not B.Brief.list_items("go") and not B.Brief.list_items("stop"))
b2 = B.Brief.with_items(b, items)
check("plan + list → runnable research brief with items", b2.get("items") and not b2.get("needs_list") and "nintendo switch" in b2["topic"] and "3 items" in b2["goal"] or "4 items" in b2["goal"], b2["goal"])

# --- 7 deal matching / ranking ---------------------------------------------------------------------------------
check("#7 a Baricco novel does not match 'nintendo switch'", not matches({"title": "City - Alessandro Baricco"}, "nintendo switch"))
check("'Nintendo Switch Lite' matches 'nintendo switch'", matches({"title": "Nintendo Switch Lite"}, "nintendo switch"))
check("'Nintendo Switch V1 Joy-Con' matches", matches({"title": "Nintendo Switch V1 Joy-Con Grigi"}, "nintendo switch"))
k_real = rank_key({"title": "Nintendo Switch completa", "price": 120}, "nintendo switch", 120)
k_case = rank_key({"title": "Custodia per Nintendo Switch", "price": 9}, "nintendo switch", 120)
k_broken = rank_key({"title": "Nintendo Switch non funziona per ricambi", "price": 40}, "nintendo switch", 120)
check("the € 120 console ranks before a € 9 case and before a broken one", k_real < k_case and k_real < k_broken, (k_real, k_case, k_broken))

# --- 4c/8 browser: no fake URLs, banners handled in open() ------------------------------------------------------
try:
    br = Browser(log=lambda *a, **k: None, viewer=None)
    try:
        br.open("slow down"); check("#4c 'slow down' is refused as an address", False, "opened")
    except BrowserError as e:
        check("#4c 'slow down' is refused as an address", "not a web address" in str(e), e)
    check("#8 Browser.open() closes banners itself (method present, counts)", hasattr(br, "_banner_pass") and br.banners_closed == 0)
    try:
        br.open("http://127.0.0.1:1/x")                                    # an IP host with a port is a real address (the practice store lives there)
        check("#4c IP:port addresses are still addresses (connection refused, not 'not a web address')", False, "opened?")
    except BrowserError as e:
        check("#4c IP:port addresses are still addresses (connection refused, not 'not a web address')", "not a web address" not in str(e), e)
    import tempfile, pathlib
    f = pathlib.Path(tempfile.mkdtemp()) / "cmp.html"
    f.write_text("<html><body><h1>Shop</h1><p>Product € 10</p><div id=cmp style='position:fixed;bottom:0;left:0;width:100%;height:120px;background:#eee'>"
                 "We use cookies for tracking. <button onclick=\"document.getElementById('cmp').remove()\">Accetta</button>"
                 "<button onclick=\"document.getElementById('cmp').remove()\">Continua senza accettare →</button></div></body></html>", encoding="utf-8")
    br.open(f.as_uri())
    gone = br.page.evaluate("() => !document.getElementById('cmp')")
    check("#8 a fixed cookie bar with 'Continua senza accettare →' is closed by open() (reject preferred)", gone and br.banners_closed == 1, (gone, br.banners_closed))
    f2 = pathlib.Path(tempfile.mkdtemp()) / "modal.html"
    f2.write_text("<html><body><h1>Shop</h1><div role=dialog id=m style='position:fixed;top:40px;left:40px;width:400px;height:300px;background:#fff'>"
                  "<button aria-label='Chiudi' onclick=\"document.getElementById('m').remove()\">x</button><h2>Dove vivi?</h2><a href='#' onclick=\"document.getElementById('m').remove();return false\">Deutschland</a><br>"
                  "<a href='#' onclick=\"document.getElementById('m').remove();return false\">Italia</a></div></body></html>", encoding="utf-8")
    br.open(f2.as_uri())
    check("#8 a 'Dove vivi?' country modal is answered with Italia", br.page.evaluate("() => !document.getElementById('m')"), "still there")
    br.close()
except Exception as e:
    for n in ("#4c 'slow down' is refused as an address", "#8 open() closes banners", "#8 cookie bar", "#8 country modal"):
        check(n + " (browser unavailable here)", False, e)

# --- 4c tasks.summarize without a URL ------------------------------------------------------------------------
T = Tasks(log=lambda *a, **k: None)
r = T.summarize("slow down")
check("#4c summarize('slow down') answers in words, never navigates", "not a web address" in r, r)

# --- 9 clock ---------------------------------------------------------------------------------------------------
tk = Talk()
r = tk.quick("What time is it in the UK") or tk.reply("What time is it in the UK")
check("#9 'the UK' has a clock", isinstance(r, str) and r.startswith("In the UK it's"), r)
r = tk.quick("what time is it in the united kingdom") or ""
check("#9 'united kingdom' too", r.startswith("In the United Kingdom it's"), r)

# --- 11 lessons ------------------------------------------------------------------------------------------------
m2 = M.Mind(); m2.begin("Slow down", "summarize", ["a"])
les = m2._lesson(m2.job, "Task failed: BrowserError: 'slow down' is not a web address — nothing to open", False, False, "")
check("#11 a fake-URL failure is a planning slip lesson, not 'cheapest source' advice", "planning slip" in les, les)
m3 = M.Mind(); m3.begin("x", "research", ["a"]); m3.job["snags"] = ["owner said slow down", "owner said slow down", "owner said stop"]
les = m3._lesson(m3.job, "ok", True, False, "")
check("owner snags never become 'check the site's walls'", "walls" not in les, les)

print(f"SESSION SCORE: {ok}/{tot}")
