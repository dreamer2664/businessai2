"""python3 -m agent.selfcheck — verify keys and the phone line without starting the loop."""
import sys
from . import config
from .telegram import Bot, TelegramError

ok = True
if not config.TELEGRAM_BOT_TOKEN:
    print("x TELEGRAM_BOT_TOKEN missing in .secrets/env"); ok = False
else:
    try:
        me = Bot().get_me()
        print(f"v telegram bot @{me.get('username')} reachable")
    except TelegramError as e:
        print("x telegram:", e); ok = False
if not config.TELEGRAM_OWNER_USERNAME and not config.TELEGRAM_OWNER_ID:
    print("x TELEGRAM_OWNER_USERNAME missing (who is allowed to talk to the bot)"); ok = False
else:
    print(f"v owner = @{config.TELEGRAM_OWNER_USERNAME or config.TELEGRAM_OWNER_ID}")
from .brain import Brain
print(("v" if Brain().ready else "-") + " brain:", Brain().describe())

# the browser — the thing that turned seven jobs into "could not start" on 2026-09-09
try:
    import playwright  # noqa: F401
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
        b.close()
    print("v browser: chromium launches")
except ImportError:
    print("x browser: the playwright module is missing → pip install playwright && python3 -m playwright install chromium-headless-shell"); ok = False
except Exception as e:
    msg = str(e).splitlines()[0][:100]
    print(f"x browser: cannot launch ({msg}) → python3 -m playwright install chromium-headless-shell && python3 -m playwright install-deps chromium"); ok = False

# the new pieces (2026-09-10): wall memory, listing card, sources, thinking model
try:
    from . import walls, listing, sources  # noqa: F401
    from .walls import WallMemory
    w = WallMemory()
    n = sum(1 for h in w.hosts if w.recent(h, 24))
    print(f"v walls memory: {len(w.hosts)} site(s) remembered, {n} walled in the last 24 h")
except Exception as e:
    print("x walls/listing/sources:", str(e)[:100]); ok = False
try:
    from .planner import Planner
    p = Planner()
    print(("v" if p.installed() else "-") + " thinking model: " + ("installed" if p.installed() else "not installed (rule-based replies only)"))
except Exception as e:
    print("- thinking model:", str(e)[:80])
try:
    from .idmail import IdMail
    m = IdMail()
    if not m.configured():
        print("- identity mailbox: not set (BAI_ACCOUNT_EMAIL + BAI_MAIL_PASSWORD in .secrets/env) → sign-ups cannot receive codes")
    else:
        good, note = m.check()
        print(("v" if good else "-") + f" identity mailbox: {m.address()} — {note}")
except Exception as e:
    print("- identity mailbox:", str(e)[:80])
try:
    from .google import Google
    g = Google()
    if g.connected():
        try:
            g._access_token()                                           # a real refresh: "connected" must mean it works, not "a token file exists"
            print("v google (optional): connected")
        except Exception as e:
            print("- google (optional): token dead — " + str(e)[:90])
    else:
        print("- google (optional): not connected" + (" — " + g.last_error[:90] if getattr(g, "last_error", "") else " (Docs/Drive links off; everything else works)"))
except Exception as e:
    print("- google (optional):", str(e)[:80])
sys.exit(0 if ok else 1)
