"""The agent's own browser (eyes + hands), driven by plain commands.

A headless Chromium controlled through Playwright. The agent never sees pixels
unless it asks for a screenshot: every page is rendered as clean, numbered text
("[3] link: Pricing", "[7] button: Add to cart", "[9] textbox: Search …"), and
actions refer to those numbers. That makes browsing reliable on a small CPU,
and every step is logged in readable form.

Rules built in (see docs/PLAN.md):
- Never solves CAPTCHAs or logs in by itself: when it meets one it stops and
  reports (owner is asked through Telegram by the caller).
- Read-only by default: form submission / clicks on pay-or-post-like controls
  require allow_actions=True from the caller (milestone 4+).
- Blocklist: no adult, gambling, or banking domains (BLOCKED).

Commands (Browser methods): open(url), tabs(), switch(i), close_tab(i), read(),
find(text), click(n), type(n, text, enter=False), scroll(dir), back(), forward(),
screenshot(path), search(query), links(), extract_text(), download_text(url).
"""
import json
import os
import re
import time
import urllib.parse

from . import config

BLOCKED = re.compile(r"(porn|xxx|casino|bet365|poker|bank(ing)?\.|paypal\.com/(signin|myaccount))", re.I)
CAPTCHA_HINTS = re.compile(r"(captcha|verify you are human|unusual traffic|are you a robot|cloudflare.*checking your browser|"
                           r"access denied|press and hold|just a moment|performing security verification|verifying you are|"
                           r"verifica di sicurezza|checking if the site connection is secure|verify that you are not a bot|"
                           r"enable javascript and cookies to continue)", re.I)
LOGIN_HINTS = re.compile(r"(sign in to continue|log in to continue|please log in|create an account to)", re.I)
MAX_TEXT = 12000          # characters of page text handed to the planner per read()
INTERACTIVE = "a[href], button, input, select, textarea, [role=button], [role=link], [role=tab], [role=menuitem], [onclick], summary"

_JS_SNAPSHOT = r"""
(maxItems) => {
  const seen = new Set(); const items = []; let n = 0;
  const vis = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
      return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const fieldLabel = (el) => {
    if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
    const lb = el.getAttribute('aria-labelledby'); if (lb) { const e = document.getElementById(lb); if (e) return e.innerText || e.textContent; }
    if (el.id) { const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]'); if (l) return l.innerText || l.textContent; }
    const wrap = el.closest('label'); if (wrap) return (wrap.innerText || wrap.textContent || '').replace(el.value || '', '');
    return el.getAttribute('placeholder') || el.getAttribute('title') || el.name || el.id || el.type || '';
  };
  const label = (el) => {
    const tag = el.tagName; let t = '';
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') t = fieldLabel(el);
    else t = (el.getAttribute('aria-label') || el.getAttribute('title') || el.getAttribute('alt') || el.innerText || el.textContent || '');
    t = (t || '').trim().replace(/\s+/g, ' ').replace(/[:*]+$/, '').trim();
    return t.slice(0, 80);
  };
  const role = (el) => {
    const tag = el.tagName.toLowerCase(); const type = (el.getAttribute('type') || '').toLowerCase();
    if (tag === 'a') return 'link'; if (tag === 'button' || type === 'submit' || type === 'button' || el.getAttribute('role') === 'button') return 'button';
    if (tag === 'input') return (type === 'checkbox' || type === 'radio') ? type : 'textbox';
    if (tag === 'textarea') return 'textbox'; if (tag === 'select') return 'select'; return el.getAttribute('role') || tag;
  };
  document.querySelectorAll('[data-bai]').forEach(e => e.removeAttribute('data-bai'));
  for (const el of document.querySelectorAll(%s)) {
    if (!vis(el)) continue; const lab = label(el); if (!lab && role(el) !== 'textbox') continue;
    const key = role(el) + '|' + lab + '|' + (el.getAttribute('href') || ''); if (seen.has(key)) continue; seen.add(key);
    n += 1; el.setAttribute('data-bai', String(n));
    const nav = !!el.closest('nav, header, footer, aside, [role=navigation], [role=banner], [role=contentinfo], [role=menubar], .nav, .navbar, .menu, .sidebar, .side_categories, .breadcrumb');
    items.push({n, role: role(el), label: lab, href: el.tagName === 'A' ? el.href : undefined, nav: nav || undefined,
                value: (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') ? (el.value || '') : undefined});
    if (n >= maxItems) break;
  }
  return items;
}
""" % json.dumps(INTERACTIVE)

_JS_TEXT = r"""
() => {
  const skip = new Set(['SCRIPT','STYLE','NOSCRIPT','SVG','IFRAME','NAV','FOOTER','HEADER','ASIDE','FORM','TEMPLATE','FIGURE','FIGCAPTION']);
  const out = [];
  const walk = (node) => {
    if (node.nodeType === 3) { const t = node.textContent.replace(/\s+/g, ' ').trim(); if (t) out.push(t); return; }
    if (node.nodeType !== 1 || skip.has(node.tagName)) return;
    const s = getComputedStyle(node); if (s.display === 'none' || s.visibility === 'hidden') return;
    const tag = node.tagName; const block = /^(P|DIV|LI|H[1-6]|TR|TD|TH|BR|SECTION|ARTICLE|BLOCKQUOTE|PRE|DT|DD|OL|UL|TABLE|LABEL|OPTION)$/.test(tag);
    if (/^H[1-6]$/.test(tag)) out.push('\n' + '#'.repeat(+tag[1]) + ' ');
    if (block) out.push('\n'); if (tag === 'LI') out.push('• ');
    const b = node.getAttribute && node.getAttribute('data-bai'); if (b) out.push('[' + b + '] ');
    for (const c of node.childNodes) walk(c);
    if (block) out.push('\n');
  };
  const root = document.querySelector('main, article, [role=main]') || document.body; walk(root);
  return out.join(' ').replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').replace(/ +/g, ' ').trim();
}
"""


class BrowserError(Exception):
    pass


class Browser:
    # one renderer for all tabs, no site-isolation processes, no background chatter: ~150-250 MB less on heavy shop pages
    LEAN_ARGS = ["--renderer-process-limit=1", "--process-per-site", "--disable-features=BackForwardCache,IsolateOrigins,site-per-process,Translate,OptimizationHints",
                 "--disable-background-networking", "--disable-component-update", "--disable-extensions", "--mute-audio", "--no-first-run",
                 "--disable-dev-shm-usage"]

    def __init__(self, headless=None, allow_actions=False, log=None, state_dir=None, viewer=None, lean=False):
        """headless=None → visible window when a display exists (or BAI_HEADED=1), else invisible.
        viewer: agent.viewer.Viewer — receives a screenshot + a plain-words line after every step."""
        from playwright.sync_api import sync_playwright
        self.log = log or (lambda kind, **f: None)
        self.viewer = viewer
        if headless is None:
            want_headed = os.environ.get("BAI_HEADED", "").lower() in ("1", "true", "yes") or bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
            headless = not want_headed
        self._pw = sync_playwright().start()
        from . import markets as _markets      # lazy: markets imports BrowserError from this module
        stealth = _markets.stealth_enabled()
        proxy = _markets.proxy_config()
        args = ["--disable-gpu", "--no-sandbox"] + self.LEAN_ARGS + (["--in-process-gpu"] if headless else [])
        if stealth:
            args += _markets.STEALTH_ARGS
        launch = dict(args=args)
        if proxy:
            launch["proxy"] = proxy
            self.log("browser_proxy", server=proxy["server"])
        try:
            self._browser = self._pw.chromium.launch(headless=headless, slow_mo=0 if headless else 250, **launch)
        except Exception as e:
            if headless:
                raise
            self.log("browser_headed_unavailable", error=str(e)[:120])
            headless = True
            self._browser = self._pw.chromium.launch(headless=True, **launch)
        self.headless = headless
        ua = _markets.pick_ua() if stealth else ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                                             "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
        self._ctx = self._browser.new_context(viewport={"width": 1280, "height": 900}, locale="en-US", user_agent=ua)
        if stealth:
            self._ctx.add_init_script(_markets.STEALTH_INIT)
            self.log("browser_stealth", ua=ua[:60])
        self._ctx.set_default_timeout(20000)
        self.lean = lean
        if lean:                                   # small machines: no pictures, videos or web fonts — the text is what I read anyway
            self._ctx.route("**/*", lambda route: route.abort() if route.request.resource_type in ("image", "media", "font") else route.continue_())
        self.allow_actions = allow_actions
        self.state_dir = state_dir or (config.STATE_DIR / "browser")
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.page = self._ctx.new_page()
        self.items = []
        self.history = []
        self.last_used = time.time()
        if self.viewer:
            self.viewer.browser_open = True

    def park(self):
        """Free the page's memory (navigate to about:blank) while the agent thinks; the tab stays open."""
        try:
            self.page.goto("about:blank", timeout=3000)
        except Exception:
            pass

    def alive(self):
        try:
            return self._browser.is_connected() and bool(self._ctx.pages)
        except Exception:
            return False

    def _show(self, action=""):
        """Push the current tab to the live viewer (screenshot only while somebody is watching)."""
        self.last_used = time.time()
        if not self.viewer:
            return
        shot = None
        if self.viewer.watching():
            try:
                shot = self.page.screenshot(type="jpeg", quality=55, timeout=4000)
            except Exception:
                pass
        try:
            self.viewer.step(action, self.page.url, self.page.title()[:80], self.status(), len(self._ctx.pages), shot)
        except Exception:
            pass

    # ---- lifecycle -----------------------------------------------------
    def close(self):
        if self.viewer:
            self.viewer.browser_open = False
        try:
            self._ctx.close(); self._browser.close(); self._pw.stop()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    # ---- tabs ----------------------------------------------------------
    def tabs(self):
        return [{"i": i, "title": p.title()[:60], "url": p.url, "active": p is self.page} for i, p in enumerate(self._ctx.pages)]

    def switch(self, i):
        self.page = self._ctx.pages[int(i)]
        self.page.bring_to_front()
        return self.read()

    def new_tab(self, url=None):
        self.page = self._ctx.new_page()
        return self.open(url) if url else "new empty tab"

    def close_tab(self, i=None):
        p = self._ctx.pages[int(i)] if i is not None else self.page
        p.close()
        self.page = self._ctx.pages[-1] if self._ctx.pages else self._ctx.new_page()
        return f"closed; {len(self._ctx.pages)} tab(s) open"

    # ---- navigation ----------------------------------------------------
    def _check(self, url):
        if BLOCKED.search(url):
            raise BrowserError(f"blocked domain: {url}")

    def open(self, url):
        if not re.match(r"^(https?|file)://", url):
            url = "https://" + url
        self._check(url)
        t0 = time.time()
        for attempt in (1, 2):
            try:
                self.page.goto(url, wait_until="domcontentloaded")
                self.page.wait_for_load_state("networkidle", timeout=8000)
                break
            except Exception as e:
                if "Timeout" in type(e).__name__ or "timeout" in str(e).lower():
                    break
                if attempt == 1 and "interrupted by another navigation" in str(e):   # a dead link just before us left the tab mid-load
                    time.sleep(0.8)
                    continue
                raise BrowserError(f"could not open {url}: {str(e)[:120]}")
        self.history.append(url)
        self.log("browser_open", url=url, ms=int((time.time() - t0) * 1000))
        self._show(f"Opened {url}")
        return self.read()

    def back(self):
        self.page.go_back(wait_until="domcontentloaded"); return self.read()

    def forward(self):
        self.page.go_forward(wait_until="domcontentloaded"); return self.read()

    ENGINES = {"brave": "https://search.brave.com/search?q={q}&source=web",
               "yahoo": "https://search.yahoo.com/search?p={q}",
               "bing": "https://www.bing.com/search?q={q}",
               "duckduckgo": "https://html.duckduckgo.com/html/?q={q}"}
    ENGINE_HOSTS = re.compile(r"brave\.com|yahoo\.com|bing\.com|duckduckgo|/search\?|admarketplace|r\.search\.|/ct\?", re.I)

    def search(self, query, engine=None):
        """Web search; returns the results page as text (links numbered). Tries the engines in turn and
        moves on when one shows a bot check or returns no results (headless visitors are often challenged)."""
        q = urllib.parse.quote_plus(query)
        order = [engine] if engine else ["brave", "yahoo", "bing", "duckduckgo"]
        last = ""
        for eng in order:
            try:
                last = self.open(self.ENGINES[eng].format(q=q))
            except BrowserError as e:
                last = str(e); continue
            if self.status() == "ok" and self._organic(limit=3):
                self.engine_used = eng
                return last
            self.log("search_engine_skip", engine=eng, reason=self.status())
        self.engine_used = None
        return last

    def _organic(self, limit=10):
        out, seen = [], set()
        for l in self.links(150):
            h = l.get("href") or ""
            if not h.startswith("http") or self.ENGINE_HOSTS.search(h) or h in seen:
                continue
            seen.add(h)
            out.append({"n": l["n"], "title": re.sub(r"^\S+ \S+ › .*?  ", "", l["text"])[:90], "url": h})
            if len(out) >= limit:
                break
        return out

    def search_results(self, query, limit=10):
        """Structured results: [{n, title, url}] with the search engine's own links filtered out."""
        self.search(query)
        return self._organic(limit)

    # ---- reading -------------------------------------------------------
    _JS_COOKIE = r"""
() => {
  const words = /(cookie|consent|privacy|gdpr|tracking|personal information)/i;
  const rejectRe = /^(reject( all)?( cookies)?|decline( all)?|refuse( all)?|deny( all)?|only (essential|necessary|required)( cookies)?|(essential|necessary|required)( cookies)? only|use (essential|necessary)( cookies)? only|continue without (accepting|agreeing)|no,? thanks|do not (sell|share)( or share)?( my)?( personal)?( information| data)?|opt out|rifiuta( tutto| tutti)?( i cookie)?|rifiuto|non accetto|continua senza accettare|solo (i )?(cookie )?(essenziali|necessari|tecnici)|ablehnen|alle ablehnen|nur notwendige( cookies)?|nur erforderliche|tout refuser|refuser( tout)?|continuer sans accepter|rechazar( todo| todas)?|solo (las )?necesarias|alles weigeren|weigeren|alleen noodzakelijk)$/i;
  const okRe = /^(ok|okay|got it|i understand|understood|close|closer|dismiss|x|✕|×|accept|accept all|allow all|agree|i agree|accept( all)? cookies|yes,? i agree|accetta( tutto| tutti)?( i cookie)?|accetto|ho capito|chiudi|va bene|alle akzeptieren|akzeptieren|zustimmen|einverstanden|schließen|tout accepter|accepter( tout)?|j'accepte|fermer|aceptar( todo| todas)?|cerrar|alles accepteren|accepteren|akkoord|sluiten)$/i;
  const vis = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
      return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const cands = Array.from(document.querySelectorAll('div, section, aside, dialog, footer, form, [role=dialog], [role=alertdialog]'))
    .filter(el => vis(el) && el.querySelector('button, a, input[type=button], [role=button]'))
    .filter(el => { const s = getComputedStyle(el); const r = el.getBoundingClientRect();
      const floating = s.position === 'fixed' || s.position === 'sticky' || el.getAttribute('role') === 'dialog' || el.tagName === 'DIALOG' || (window.self !== window.top);
      return floating && words.test((el.innerText || '').slice(0, 1500)); });
  if (!cands.length) return null;
  const box = cands.sort((a, b) => a.innerText.length - b.innerText.length)[0];
  const btns = Array.from(box.querySelectorAll('button, a, input[type=button], input[type=submit], [role=button]')).filter(vis);
  const txt = (b) => ((b.innerText || b.value || b.getAttribute('aria-label') || b.getAttribute('title') || '').trim().replace(/\s+/g, ' '));
  let pick = btns.find(b => rejectRe.test(txt(b))) || btns.find(b => okRe.test(txt(b)));
  if (!pick) return {found: true, clicked: null, text: (box.innerText || '').slice(0, 120)};
  const label = txt(pick); pick.click();
  return {found: true, clicked: label, text: (box.innerText || '').slice(0, 120)};
}
"""

    def dismiss_banner(self):
        """Close a cookie / consent banner if one covers the page: prefers 'reject' / 'necessary only', else 'ok'/'accept'.
        Looks in the page and in consent iframes (Sourcepoint, OneTrust, Didomi …). Returns the label clicked, or ''."""
        frames = [self.page.main_frame] + [f for f in self.page.frames if f is not self.page.main_frame and
                                             re.search(r"consent|privacy|cookie|cmp|sp_message|onetrust|didomi|quantcast|trustarc", (f.name or "") + " " + (f.url or "") + " " + self._frame_title(f), re.I)]
        for fr in frames[:6]:
            try:
                r = fr.evaluate(self._JS_COOKIE)
            except Exception:
                continue
            if r and r.get("clicked"):
                time.sleep(0.8)
                self.log("browser_banner", clicked=r["clicked"], text=r.get("text", "")[:80], frame=("main" if fr is self.page.main_frame else "iframe"))
                return r["clicked"]
        return ""

    def _frame_title(self, fr):
        try:
            el = fr.frame_element()
            return el.get_attribute("title") or ""
        except Exception:
            return ""

    def snapshot(self, max_items=150):
        self.items = self.page.evaluate(_JS_SNAPSHOT, max_items)
        return self.items

    BOT_WALL_MARKERS = re.compile(r"(datadome|captcha-delivery\.com|geo\.captcha-delivery|cf-chl|challenge-platform|/cdn-cgi/challenge|"
                                  r"px-captcha|perimeterx|_Incapsula_Resource|akamai.*bot|arkoselabs|awswaf|"
                                  r"g-recaptcha[^>]{0,200}data-size=.invisible.{0,400}(checking|verif))", re.I)

    def status(self):
        """Detect walls the agent must not try to pass. A bot-check (DataDome, Cloudflare challenge, PerimeterX, hCaptcha…) is
        usually an almost empty page whose HTML carries the vendor's markers — it counts as a captcha."""
        try:
            body = self.page.inner_text("body", timeout=3000)[:4000]
        except Exception:
            body = ""
        title = self.page.title()
        if CAPTCHA_HINTS.search(title) or CAPTCHA_HINTS.search(body):
            return "captcha"
        if len(body.strip()) < 600:
            try:
                self.page.wait_for_load_state("load", timeout=4000)     # a half-loaded page looks empty; give it a moment
                body = self.page.inner_text("body", timeout=3000)[:4000]
            except Exception:
                pass
        if len(body.strip()) < 600:
            try:
                html = self.page.content()[:40000]
            except Exception:
                html = ""
            if self.BOT_WALL_MARKERS.search(html):
                return "captcha"
        if LOGIN_HINTS.search(body):
            return "login"
        return "ok"

    def read(self, max_chars=MAX_TEXT):
        """The page as the agent sees it: header, wall status, numbered interactive items inline in the text."""
        self.snapshot()
        try:
            text = self.page.evaluate(_JS_TEXT)
        except Exception as e:
            text = f"(could not read page: {e})"
        st = self.status()
        head = f"URL: {self.page.url}\nTITLE: {self.page.title()}\nTABS: {len(self._ctx.pages)}  STATUS: {st}\n"
        if st != "ok":
            head += ("!! This page shows a CAPTCHA / bot check. I must not try to pass it — stop and ask the owner.\n"
                     if st == "captcha" else "!! This page asks for a login. I must not log in by myself — stop and ask the owner.\n")
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n… (truncated; {len(text) - max_chars} more characters — use scroll or find)"
        if self.viewer:
            self.viewer.text = head + "\n" + text
        return head + "\n" + text

    def links(self, limit=60):
        self.snapshot()
        return [{"n": it["n"], "text": it["label"], "href": it.get("href")} for it in self.items if it["role"] == "link"][:limit]

    def find(self, needle, context=160):
        """Find text on the page; returns snippets around each match (case-insensitive)."""
        text = self.page.evaluate(_JS_TEXT)
        out, low, n = [], text.lower(), needle.lower()
        i = low.find(n)
        while i != -1 and len(out) < 10:
            out.append(text[max(0, i - context):i + len(needle) + context].replace("\n", " "))
            i = low.find(n, i + 1)
        return out or [f"'{needle}' not found on this page"]

    def extract_text(self):
        return self.page.evaluate(_JS_TEXT)

    def screenshot(self, path=None, full=False):
        path = str(path or self.state_dir / f"shot_{int(time.time())}.png")
        self.page.screenshot(path=path, full_page=full)
        return path

    # ---- acting --------------------------------------------------------
    def _el(self, n):
        loc = self.page.locator(f"[data-bai='{int(n)}']")
        if loc.count() == 0:
            self.snapshot()
            loc = self.page.locator(f"[data-bai='{int(n)}']")
            if loc.count() == 0:
                raise BrowserError(f"no element [{n}] on the current page (call read() again)")
        return loc.first

    def _settle(self, url_before, sig_before, wait=6.0):
        """After a click/Enter: wait until the new page is really drawn. Two shop habits are handled: (a) the address
        changes first and the content arrives a few seconds later (IKEA) — wait for it; (b) single-page shops change the
        address but never draw the new page (Unieuro: old title and heading stay) — then load the new address itself."""
        t0 = time.time()
        head = lambda sig: sig.split("|")[:2]                              # title + first heading
        changed_at = None
        while time.time() - t0 < wait + 4:
            if self.page.url == url_before:
                return False
            try:
                sig = self._dom_sig()
                if head(sig) != head(sig_before):
                    changed_at = changed_at or time.time()
                    complete = self.page.evaluate("() => document.readyState") == "complete"
                    if len(self.page.inner_text("body", timeout=2000)) > 800 or complete or time.time() - changed_at > 3:
                        return False                                       # new page drawn (or as drawn as it gets)
            except Exception:
                pass                                                       # mid-navigation: try again
            time.sleep(0.7)
        if changed_at:
            return False
        try:
            url = self.page.url
            self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(1.5)
            self.log("browser_reload_after_stuck_route", url=url[:120])
            return True
        except Exception:
            return False

    def _dom_sig(self):
        """Cheap fingerprint of what is on the page (to notice a click that changed nothing): title, first heading,
        number of links, and whether a dialog is open. Rotating banners do not change it; a real navigation or popup does."""
        try:
            return self.page.evaluate("() => [document.title, (document.querySelector('h1') || {}).innerText || '', document.links.length, "
                                      "!!document.querySelector('[role=dialog], dialog[open], [aria-modal=true]')].join('|')")
        except Exception:
            return ""

    def _item(self, n):
        for it in self.items:
            if it["n"] == int(n):
                return it
        return {}

    STAGE_HOSTS = {"127.0.0.1", "localhost", "0.0.0.0"}

    def _is_stage(self):
        """Pages served by the agent itself (practice shop, rehearsal network, test sites) are a stage: nothing there is real,
        so the post/submit gate does not apply. Real sites keep the gate."""
        try:
            host = urllib.parse.urlparse(self.page.url).hostname or ""
        except Exception:
            return False
        return host in self.STAGE_HOSTS or self.page.url.startswith("file://")

    def click(self, n):
        it = self._item(n)
        lab = (it.get("label") or "").lower()
        if not self.allow_actions and re.search(r"\b(buy|pay|checkout|place order|purchase|submit|post|publish|send|delete|confirm|subscribe|order now)\b", lab) \
                and not self._is_stage():
            raise BrowserError(f"refusing to click '{it.get('label')}' — actions that buy/pay/post/submit need owner approval")
        el = self._el(n)
        before = len(self._ctx.pages)
        url_before, sig_before = self.page.url, self._dom_sig()
        try:
            with self._ctx.expect_page(timeout=1500) as newp:
                el.click()
            self.page = newp.value
        except Exception:
            pass  # no new tab opened — normal click
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=8000)
        except Exception:
            pass
        href = it.get("href") or ""
        if len(self._ctx.pages) == before and self.page.url != url_before:
            self._settle(url_before, sig_before)
        if href.startswith("http") and len(self._ctx.pages) == before and self.page.url == url_before \
                and href.split("#")[0] != url_before.split("#")[0]:
            time.sleep(1.0)                                    # some shops' scripts swallow the click: if nothing changed, open the link's address
            if self.page.url == url_before and self._dom_sig() == sig_before:
                self._check(href)
                self.page.goto(href, wait_until="domcontentloaded", timeout=30000)
                self.log("browser_click_fallback", n=int(n), href=href[:120])
        self.log("browser_click", n=int(n), label=it.get("label"), role=it.get("role"), new_tab=len(self._ctx.pages) > before)
        self._show(f"Clicked '{it.get('label')}'")
        return self.read()

    def type(self, n, text, enter=False):
        it = self._item(n)
        el = self._el(n)
        url_before, sig_before = self.page.url, self._dom_sig()
        el.click(timeout=8000)
        # Some sites (Wikipedia, many shops) swap the search box for a new widget on focus, so the numbered element
        # goes stale. After the click the keyboard goes to whatever is focused, so type through the page keyboard.
        try:
            el.fill("", timeout=1500)
        except Exception:
            try:
                self.page.keyboard.press("Control+A")
                self.page.keyboard.press("Backspace")
            except Exception:
                pass
        self.page.keyboard.type(text, delay=20)
        if enter:
            self.page.keyboard.press("Enter")
            try:
                self.page.wait_for_load_state("domcontentloaded", timeout=8000)
            except Exception:
                pass
            time.sleep(0.5)
            t0 = time.time()
            while self.page.url == url_before and time.time() - t0 < 6:      # single-page shops change the address a few seconds later
                if self._dom_sig().split("|")[:2] != sig_before.split("|")[:2] or self.page.url.startswith("file://"):
                    break                                                    # results drawn in place (no address change) — fine
                time.sleep(0.5)
            if self.page.url != url_before:
                self._settle(url_before, sig_before)
        self.log("browser_type", n=int(n), label=it.get("label"), text=text[:80], enter=enter)
        self._show(f"Typed '{text[:40]}' into '{it.get('label')}'")
        return self.read() if enter else f"typed into [{n}] {it.get('label')!r}"

    def select(self, n, value):
        el = self._el(n)
        el.select_option(label=value)
        return f"selected {value!r} in [{n}]"

    def scroll(self, direction="down", pages=1):
        dy = 800 * pages * (1 if direction == "down" else -1)
        self.page.mouse.wheel(0, dy)
        time.sleep(0.4)
        self._show(f"Scrolled {direction}")
        return self.read()

    def download_text(self, url, max_chars=60000):
        """Fetch a document (html/txt/pdf) in the browser context and return its text."""
        self._check(url)
        r = self._ctx.request.get(url, timeout=30000)
        ctype = r.headers.get("content-type", "")
        if "pdf" in ctype or url.lower().endswith(".pdf"):
            try:
                import io
                from pypdf import PdfReader
                rd = PdfReader(io.BytesIO(r.body()))
                txt = "\n".join((p.extract_text() or "") for p in rd.pages[:40])
            except Exception as e:
                txt = f"(pdf could not be read: {e})"
        else:
            txt = re.sub(r"<[^>]+>", " ", r.text())
            txt = re.sub(r"\s+", " ", txt)
        return txt[:max_chars]
