"""Postly — a small fake social network for rehearsals (milestone 18). Runs on 127.0.0.1:<port>.

  /            feed (newest first), nav: Home · New post · Notifications · Profile · Log in / Log out
  /login       e-mail + password (any account created on /signup, plus the pre-seeded agent account)
  /signup      username + e-mail + password → active at once (verification is rehearsed on the sign-up site)
  /new         composer: textarea "What's new?" (max 300 characters, max 5 hashtags, counter "0/300"), photo upload, Publish
  /p/<id>      post page: text, photo, comments, comment form ("Write a reply…" + Reply)
  /notifications  comments others left on my posts
  /u/<name>    profile: my posts

Rules (so the agent learns limits like on real platforms): a post over 300 characters or with more than 5 hashtags is
refused with a red error; a new post immediately gets one comment from a fake buyer ("do you ship to Germany?").
State is in memory; `python3 tests/social/server.py 8096` to run by hand.
"""
import html
import http.cookies
import http.server
import json
import re
import sys
import threading
import time
import urllib.parse
import uuid

ACCOUNTS = {"stagebot@example.com": {"user": "businessai", "password": "BusinessAI001!"}}
SESSIONS = {}
POSTS = []          # dicts: id, user, text, image(bytes|None), t, comments[{who,text,t}]
NOTIFS = []
LIMIT, MAX_TAGS = 300, 5
BUYER_COMMENTS = ["Nice! Do you ship to Germany? 🇩🇪", "How long does delivery take to Spain?", "Is this available in blue?", "Love it 😍 what's the price?"]
LOCK = threading.Lock()


def seed():
    with LOCK:
        if POSTS:
            return
        for u, t, c in [("lena.makes", "Morning light in the studio ✨ new ceramic mugs coming this week. #handmade #ceramics", [("marco_b", "Those look great, price?")]),
                        ("greenthumb", "Repotted all the ferns today. Tip: water less in autumn 🌿 #plants", []),
                        ("bikekitchen", "Fixed 14 bikes at the community repair day 🚲 thanks everyone! #community #repair", [("anna.k", "Thank you for fixing mine!")])]:
            POSTS.append({"id": uuid.uuid4().hex[:8], "user": u, "text": t, "image": None, "t": time.time() - 3600 * len(POSTS),
                          "comments": [{"who": w, "text": x, "t": time.time()} for w, x in c]})


PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>{title} · Postly</title>
<style>body{{font-family:system-ui,sans-serif;max-width:640px;margin:0 auto;padding:14px;color:#222}}nav a{{margin-right:14px}}.post{{border:1px solid #ddd;border-radius:10px;padding:12px;margin:12px 0}}
.who{{font-weight:600}}.err{{color:#b00020;background:#fde7ea;padding:8px;border-radius:6px}}.ok{{color:#0a6b2a;background:#e6f6ea;padding:8px;border-radius:6px}}textarea,input{{width:100%;padding:8px;margin:6px 0;box-sizing:border-box}}
button{{padding:8px 16px}}.comment{{border-top:1px solid #eee;padding:6px 0}}img{{max-width:100%;border-radius:8px}}small{{color:#666}}</style></head><body>
<nav><a href="/">Home</a><a href="/new">New post</a><a href="/notifications">Notifications ({nn})</a>{user_nav}</nav><h2>{title}</h2>{body}</body></html>"""


class H(http.server.BaseHTTPRequestHandler):
    server_version = "Postly/1.0"

    def log_message(self, *a):
        pass

    # ---- helpers ----
    def user(self):
        c = http.cookies.SimpleCookie(self.headers.get("Cookie", ""))
        sid = c["sid"].value if "sid" in c else None
        return SESSIONS.get(sid)

    def page(self, title, body, code=200, cookie=None, location=None):
        u = self.user()
        user_nav = (f'<a href="/u/{u}">Profile ({u})</a><a href="/logout">Log out</a>' if u else '<a href="/login">Log in</a><a href="/signup">Sign up</a>')
        nn = sum(1 for n in NOTIFS if n["to"] == u) if u else 0
        data = PAGE.format(title=html.escape(title), body=body, user_nav=user_nav, nn=nn).encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        if location:
            self.send_header("Location", location)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def redirect(self, to, cookie=None):
        self.send_response(303)
        self.send_header("Location", to)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def form(self):
        ctype = self.headers.get("Content-Type", "")
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n)
        if ctype.startswith("multipart/form-data"):
            m = re.search(r'boundary="?([^";]+)"?', ctype)
            out = {}
            if not m:
                return out
            for part in raw.split(b"--" + m.group(1).encode()):
                if b"\r\n\r\n" not in part:
                    continue
                head, body = part.split(b"\r\n\r\n", 1)
                body = body[:-2] if body.endswith(b"\r\n") else body
                nm = re.search(rb'name="([^"]+)"', head)
                if not nm:
                    continue
                if re.search(rb'filename="', head):
                    out[nm.group(1).decode()] = body                          # file → bytes
                else:
                    out[nm.group(1).decode()] = body.decode(errors="ignore")
            return out
        return {k: v[0] for k, v in urllib.parse.parse_qs(raw.decode(errors="ignore")).items()}

    def render_post(self, p, full=False):
        img = f'<img src="/img/{p["id"]}" alt="photo">' if p.get("image") else ""
        cm = "".join(f'<div class="comment"><span class="who">{html.escape(c["who"])}</span> {html.escape(c["text"])}</div>' for c in p["comments"])
        head = f'<div class="post" id="post-{p["id"]}"><span class="who">@{html.escape(p["user"])}</span> <small>{time.strftime("%H:%M", time.localtime(p["t"]))}</small><p>{html.escape(p["text"])}</p>{img}'
        if full:
            return head + f'<h3>Comments ({len(p["comments"])})</h3>{cm}<form method="post" action="/p/{p["id"]}/comment"><label>Write a reply…<textarea name="text" rows="2" placeholder="Write a reply…"></textarea></label><button type="submit">Reply</button></form></div>'
        return head + f'<p><a href="/p/{p["id"]}">💬 {len(p["comments"])} comments</a></p></div>'

    # ---- routes ----
    def do_GET(self):
        seed()
        u = self.user()
        path = urllib.parse.urlparse(self.path).path
        if path == "/":
            return self.page("Feed", "".join(self.render_post(p) for p in sorted(POSTS, key=lambda p: -p["t"])))
        if path == "/login":
            return self.page("Log in", '<form method="post"><label>E-mail<input type="email" name="email" required></label><label>Password<input type="password" name="password" required></label><button type="submit">Log in</button></form><p><a href="/signup">Create an account</a></p>')
        if path == "/signup":
            return self.page("Sign up", '<form method="post"><label>Username<input name="username" required></label><label>E-mail<input type="email" name="email" required></label><label>Password<input type="password" name="password" required></label><label><input type="checkbox" name="terms" required style="width:auto"> I accept the terms</label><button type="submit">Create account</button></form>')
        if path == "/logout":
            c = http.cookies.SimpleCookie(self.headers.get("Cookie", ""))
            if "sid" in c:
                SESSIONS.pop(c["sid"].value, None)
            return self.redirect("/", cookie="sid=; Max-Age=0; Path=/")
        if path == "/new":
            if not u:
                return self.redirect("/login")
            return self.page("New post", f'''<form method="post" enctype="multipart/form-data"><label>What's new?<textarea name="text" rows="5" maxlength="{LIMIT}" placeholder="What's new?" oninput="document.getElementById('c').textContent=this.value.length+'/{LIMIT}'"></textarea></label>
<small id="c">0/{LIMIT}</small> · <small>max {MAX_TAGS} hashtags</small><label>Photo<input type="file" name="photo" accept="image/*"></label><label><input type="checkbox" name="story" style="width:auto"> Also share to story</label><button type="submit">Publish</button></form>''')
        if path == "/notifications":
            if not u:
                return self.redirect("/login")
            mine = [n for n in NOTIFS if n["to"] == u]
            return self.page("Notifications", "".join(f'<div class="post"><span class="who">{html.escape(n["who"])}</span> commented on <a href="/p/{n["post"]}">your post</a>: {html.escape(n["text"])}</div>' for n in reversed(mine)) or "<p>No notifications.</p>")
        m = re.fullmatch(r"/p/([0-9a-f]+)", path)
        if m:
            p = next((x for x in POSTS if x["id"] == m.group(1)), None)
            return self.page("Post", self.render_post(p, full=True)) if p else self.page("Not found", "<p>No such post.</p>", 404)
        m = re.fullmatch(r"/img/([0-9a-f]+)", path)
        if m:
            p = next((x for x in POSTS if x["id"] == m.group(1)), None)
            data = (p or {}).get("image") or b""
            self.send_response(200 if data else 404)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        m = re.fullmatch(r"/u/([\w.]+)", path)
        if m:
            return self.page(f"@{m.group(1)}", "".join(self.render_post(p) for p in sorted(POSTS, key=lambda p: -p["t"]) if p["user"] == m.group(1)) or "<p>No posts yet.</p>")
        if path == "/api/state":                                       # for the scorer
            data = json.dumps({"posts": [{k: v for k, v in p.items() if k != "image"} | {"has_image": bool(p.get("image"))} for p in POSTS], "accounts": list(ACCOUNTS), "notifs": NOTIFS}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        return self.page("Not found", "<p>Nothing here.</p>", 404)

    def do_POST(self):
        seed()
        u = self.user()
        path = urllib.parse.urlparse(self.path).path
        f = self.form()
        if path == "/login":
            a = ACCOUNTS.get((f.get("email") or "").strip().lower())
            if not a or a["password"] != f.get("password"):
                return self.page("Log in", '<p class="err">Wrong e-mail or password.</p><form method="post"><label>E-mail<input type="email" name="email" required></label><label>Password<input type="password" name="password" required></label><button type="submit">Log in</button></form>')
            sid = uuid.uuid4().hex
            SESSIONS[sid] = a["user"]
            return self.redirect("/", cookie=f"sid={sid}; Path=/")
        if path == "/signup":
            email = (f.get("email") or "").strip().lower()
            if not (email and f.get("password") and f.get("username")):
                return self.page("Sign up", '<p class="err">All fields are required.</p>')
            ACCOUNTS[email] = {"user": re.sub(r"[^\w.]", "", f["username"])[:20] or "user", "password": f["password"]}
            sid = uuid.uuid4().hex
            SESSIONS[sid] = ACCOUNTS[email]["user"]
            return self.redirect("/", cookie=f"sid={sid}; Path=/")
        if path == "/new":
            if not u:
                return self.redirect("/login")
            text = (f.get("text") or "").strip()
            if isinstance(text, bytes):
                text = text.decode(errors="ignore")
            tags = re.findall(r"#\w+", text)
            err = None
            if not text:
                err = "Write something first."
            elif len(text) > LIMIT:
                err = f"Too long: {len(text)}/{LIMIT} characters."
            elif len(tags) > MAX_TAGS:
                err = f"Too many hashtags: {len(tags)} (max {MAX_TAGS})."
            if err:
                return self.page("New post", f'<p class="err">{html.escape(err)}</p><p><a href="/new">Try again</a></p>', 400)
            img = f.get("photo") if isinstance(f.get("photo"), (bytes, bytearray)) and len(f.get("photo")) > 0 else None
            p = {"id": uuid.uuid4().hex[:8], "user": u, "text": text, "image": bytes(img) if img else None, "t": time.time(), "comments": []}
            with LOCK:
                POSTS.append(p)
            def later():
                time.sleep(1.5)
                c = {"who": "buyer_" + uuid.uuid4().hex[:4], "text": BUYER_COMMENTS[len(POSTS) % len(BUYER_COMMENTS)], "t": time.time()}
                with LOCK:
                    p["comments"].append(c)
                    NOTIFS.append({"to": u, "who": c["who"], "text": c["text"], "post": p["id"], "t": c["t"]})
            threading.Thread(target=later, daemon=True).start()
            return self.redirect(f"/p/{p['id']}")
        m = re.fullmatch(r"/p/([0-9a-f]+)/comment", path)
        if m:
            p = next((x for x in POSTS if x["id"] == m.group(1)), None)
            text = (f.get("text") or "").strip()
            if p and text:
                with LOCK:
                    p["comments"].append({"who": u or "anonymous", "text": text[:500], "t": time.time()})
            return self.redirect(f"/p/{m.group(1)}")
        return self.page("Not found", "<p>Nothing here.</p>", 404)


def serve(port):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), H)
    srv.daemon_threads = True
    return srv


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8096
    print(f"Postly on http://127.0.0.1:{port}")
    serve(port).serve_forever()
