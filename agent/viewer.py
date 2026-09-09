"""Live view of the agent at work — "its screen".

A tiny built-in web page (no dependencies, no external files) that shows:
  * the latest screenshot of the tab the agent is looking at (refreshes every second),
  * what the agent is doing, in plain words (opened / clicked / typed / stopped at a wall / done),
  * a toggle to see what the agent actually reads (the numbered-text view of the page).
It also keeps the latest screenshot in memory for Telegram (/screen, /watch on).

Frugal by design: screenshots are only taken while somebody is watching (the page was polled in the
last 20 s, or Telegram /watch is on). Nothing is written to disk.

Starts automatically with the agent:  http://localhost:8765   (BAI_VIEW_PORT / BAI_VIEW_HOST)
Demo without Telegram:                python3 -m agent.viewer --demo [--host 0.0.0.0]
"""
import collections
import datetime as _dt
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Business AI — live</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
 body{margin:0;background:#111;color:#ddd;font:14px system-ui,sans-serif}
 header{padding:6px 12px;background:#1c1c1c;display:flex;gap:12px;align-items:center;flex-wrap:wrap;border-bottom:1px solid #333}
 .badge{padding:2px 9px;border-radius:10px;background:#2a7;color:#fff;font-size:12px}
 .badge.captcha,.badge.login{background:#c33}.badge.idle{background:#555}
 #url{color:#9ad;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:50vw}
 main{display:grid;grid-template-columns:minmax(0,2fr) minmax(280px,1fr);height:calc(100vh - 40px)}
 #left{background:#000;display:flex;align-items:flex-start;justify-content:center;overflow:auto}
 #shot{max-width:100%;max-height:100%} #text{display:none;white-space:pre-wrap;font-size:12px;padding:10px;color:#cfc;margin:0}
 aside{overflow:auto;padding:8px 10px;border-left:1px solid #333}
 .ev{padding:4px 0;border-bottom:1px solid #222}.ev time{color:#777;margin-right:6px;font-size:12px}
 button{background:#333;color:#ddd;border:1px solid #555;border-radius:4px;padding:3px 8px;cursor:pointer}
 #plan{background:#161616;border-bottom:1px solid #333;padding:8px 10px;font-size:13px;display:none}
 #plan .goal{color:#fff;font-weight:600}#plan ol{margin:6px 0 0 18px;padding:0}#plan li{padding:1px 0;color:#999}
 #plan li.doing{color:#ffd166}#plan li.done{color:#6c6;text-decoration:line-through}
#think{background:#161616;border-bottom:1px solid #333;padding:8px 10px;font-size:13px;display:none}
#think .goal{color:#fff;font-weight:600}
 #timer{float:right;font-variant-numeric:tabular-nums;font-size:22px;font-weight:700;padding:0 6px;border-radius:6px}
 #timer.ok{color:#6c6}#timer.warn{color:#ffd166}#timer.late{color:#f66;animation:blink 1s step-end infinite}#timer.slow{color:#9ad;font-size:15px}
 @keyframes blink{50%{opacity:.4}}
 @media(max-width:700px){main{grid-template-columns:1fr;grid-template-rows:55vh 1fr}aside{border-left:0;border-top:1px solid #333}}
</style></head><body>
<header><b>Business AI — live</b><span id="task">…</span><span id="badge" class="badge idle">starting</span>
<span id="url"></span><button onclick="toggle()" id="tg">show what it reads</button></header>
<main><div id="left" style="flex-direction:column"><div id="plan"></div><img id="shot" alt="(no screenshot yet — the browser opens when a task starts)"><pre id="text"></pre></div>
<aside><div id="think"></div><div id="events"></div></aside></main>
<script>
let showText=false,lastShot=null;
function toggle(){showText=!showText;text.style.display=showText?'block':'none';shot.style.display=showText?'none':'block';
 tg.textContent=showText?'show the screen':'show what it reads';}
function mmss(sec){const a=Math.abs(sec),h=Math.floor(a/3600),m=Math.floor(a%3600/60),s=a%60;
 return (sec<0?'-':'')+(h?h+':':'')+String(m).padStart(2,'0')+':'+String(s).padStart(2,'0');}
function renderPlan(p){const el=document.getElementById('plan');if(!p||!p.goal){el.style.display='none';return;}el.style.display='block';
 let t='';const now=Date.now()/1000;
 if(p.deadline){const left=Math.round(p.deadline-now);t='<span id="timer" class="'+(left<0?'late':left<180?'warn':'ok')+'" title="owner wants it in '+p.deadline_min+' min">⏰ '+mmss(left)+(left<0?' late':'')+'</span>';}
 else if(p.budget_until){const left=Math.round(p.budget_until-now);t='<span id="timer" class="slow">🐢 owner away · '+mmss(Math.max(0,left))+' left</span>';}
 let h=t+'<div class=goal>'+esc(p.goal)+'</div>';
 if(p.steps&&p.steps.length){h+='<ol>';p.steps.forEach((s,i)=>{const c=i<p.step?'done':i===p.step?'doing':'';h+='<li class="'+c+'">'+(c==='doing'?'▶ ':'')+esc(s)+'</li>';});h+='</ol>';}
 if(p.note){h+='<div style="color:#bbb;margin-top:4px">'+esc(p.note)+'</div>';}
 el.innerHTML=h;}
function renderThink(t){const el=document.getElementById('think');if(!t){el.style.display='none';return;}el.style.display='block';
 let h='<div class=goal>🧠 Thinking</div><div>'+esc(t.why)+'</div><div style="color:#bbb">'+esc(t.status)+'</div>';
 h+='<div style="color:#888">Queue: '+esc(t.queue)+'</div>';
 if(t.lessons&&t.lessons.length){h+='<div style="margin-top:4px;color:#9ad">Lessons:</div>';t.lessons.forEach(l=>{h+='<div>• '+esc(l)+'</div>';});}
 el.innerHTML=h;}
function esc(x){return String(x).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
async function tick(){try{const s=await (await fetch('state.json',{cache:'no-store'})).json();
 task.textContent=s.task?('Task: '+s.task):'(no task running)';
 badge.textContent=s.idle?'browser closed':s.status;badge.className='badge '+(s.idle?'idle':s.status);
 url.textContent=s.title?(s.title+' — '+s.url):'';renderPlan(s.plan);renderThink(s.think);
 const ev=document.getElementById('events');ev.innerHTML='';
 for(const e of s.events){const d=document.createElement('div');d.className='ev';const t=document.createElement('time');t.textContent=e.t;
  d.appendChild(t);d.appendChild(document.createTextNode(e.text));ev.appendChild(d);}
 if(s.shot_time&&s.shot_time!==lastShot){lastShot=s.shot_time;shot.src='shot.jpg?t='+s.shot_time;}
 if(showText){text.textContent=await (await fetch('text',{cache:'no-store'})).text();}
}catch(e){}setTimeout(tick,1000);}tick();
</script></body></html>"""


def humanize(kind, f):
    """Turn a log record into one plain sentence for the owner."""
    g = lambda k, d="": f.get(k, d)
    return {
        "task_start": lambda: f"▶ Task: {g('cmd')} {g('arg')}",
        "plan": lambda: f"📋 New plan: {g('goal')} ({g('n')} steps)",
        "plan_step": lambda: f"▶ Step {g('n')}: {g('text')}",
        "pace_set": lambda: f"⏱ Pace {g('mode')}" + (f" — owner wants it in {g('deadline_min')} min" if g('deadline_min') else "") + (f" — owner away for {g('budget_min')} min" if g('budget_min') else ""),
        "pace_late": lambda: "⏰ Past the time the owner asked for — finishing as fast as I can",
        "brief": lambda: f"🧠 Understood: {g('task')} → {g('deliverable')} ({g('steps')} steps, pace {g('pace')})",
        "doc_saved": lambda: f"📄 Document written: {g('title')} ({g('options')} options)",
        "drive_upload": lambda: f"☁️ Uploaded to my Drive: {g('name')}",
        "seller_check": lambda: f"🔎 Checking seller: {g('name')}",
        "task_done": lambda: f"✔ Done in {int(g('ms', 0)) / 1000:.0f} s — report of {g('chars')} characters sent",
        "browser_open": lambda: f"Opened {g('url')} ({int(g('ms', 0)) / 1000:.1f} s)",
        "browser_click": lambda: f"Clicked [{g('n')}] '{g('label')}'" + (" → a new tab opened" if g("new_tab") else ""),
        "browser_type": lambda: f"Typed '{g('text')}' into [{g('n')}] '{g('label')}'" + (" and pressed Enter" if g("enter") else ""),
        "search_engine_skip": lambda: f"{g('engine')} showed a {g('reason')} wall — I don't pass those; trying the next search engine",
        "task_wall": lambda: f"Skipped {g('url')}: it is behind a {g('wall')} wall",
        "browser_headed_unavailable": lambda: "No display found — running the browser invisibly (watch it here instead)",
        "session_closed": lambda: "Closed my browser (idle for 10 minutes)",
        "in": lambda: f"Owner: {g('text')}",
        "out": lambda: f"Me: {str(g('text'))[:160]}",
        "start": lambda: f"Agent started (version {g('version')})",
    }.get(kind, lambda: f"{kind}: " + ", ".join(f"{k}={str(v)[:60]}" for k, v in f.items()))()


def _is_wsl():
    try:
        return "microsoft" in open("/proc/version").read().lower()
    except Exception:
        return False


class Viewer:
    def __init__(self, port=None, host=None, on_step=None):
        self.port = int(port or os.environ.get("BAI_VIEW_PORT", "8765"))
        # Under WSL, Windows only reliably reaches ports bound on all interfaces; elsewhere stay local-only.
        self.host = host or os.environ.get("BAI_VIEW_HOST") or ("0.0.0.0" if _is_wsl() else "127.0.0.1")
        self.on_step = on_step                # callback(action_text, jpeg_bytes) — used for Telegram /watch
        self.force = False                    # take screenshots even when nobody polls the page
        self.shot, self.shot_time = None, 0
        self.url = self.title = self.text = ""
        self.status, self.tabs, self.task = "idle", 0, None
        self.plan = None                      # {"goal", "steps", "step", "deadline", "deadline_min", "budget_until", "note"}
        self.listener = None                  # Mind.on_event(kind, fields) — the agent's own journal listens to what the screen shows
        self.thinker = None                   # Mind (item 9): state() pulls its live beliefs into the thinking panel
        self.browser_open = False
        self.events = collections.deque(maxlen=200)
        self._seen = 0
        self._srv = None

    # ---- what the browser pushes -----------------------------------------
    def watching(self):
        return self.force or (time.time() - self._seen) < 20

    def note(self, kind, fields):
        if kind in ("poll_error",):
            return
        self.events.appendleft({"t": _dt.datetime.now().strftime("%H:%M:%S"), "text": humanize(kind, fields)})
        if self.listener:
            try:
                self.listener(kind, fields)
            except Exception:
                pass

    def step(self, action, url, title, status, tabs, shot=None):
        self.url, self.title, self.status, self.tabs = url, title, status, tabs
        if shot:
            self.shot, self.shot_time = shot, int(time.time() * 1000)
        if self.on_step and action:
            try:
                self.on_step(action, shot)
            except Exception:
                pass

    def state(self):
        think = None
        if self.thinker is not None:
            try:
                think = self.thinker.think_snapshot()
            except Exception:
                think = None
        return {"url": self.url, "title": self.title, "status": self.status, "tabs": self.tabs, "task": self.task,
                "plan": self.plan, "shot_time": self.shot_time, "idle": not self.browser_open, "events": list(self.events)[:60],
                "think": think}

    # ---- the plan panel (milestone 13) ----------------------------------------
    def show_plan(self, goal, steps, pace=None, note=""):
        p = {"goal": goal, "steps": list(steps), "step": 0, "note": note, "deadline": None, "deadline_min": None, "budget_until": None}
        if pace is not None:
            p["deadline"], p["budget_until"] = pace.deadline, pace.budget_until
            p["deadline_min"] = pace.deadline_min
        self.plan = p
        self.note("plan", {"goal": goal, "n": len(p["steps"])})

    def plan_step(self, i, note=""):
        if self.plan:
            self.plan["step"] = i
            if note:
                self.plan["note"] = note
            self.note("plan_step", {"n": i + 1, "text": self.plan["steps"][i] if 0 <= i < len(self.plan["steps"]) else note})

    def plan_done(self, note="done"):
        if self.plan:
            self.plan["step"] = len(self.plan["steps"])
            self.plan["note"] = note

    def clear_plan(self):
        self.plan = None

    # ---- http --------------------------------------------------------------
    def start(self):
        viewer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, ctype, body):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                p = self.path.split("?")[0]
                if p == "/":
                    return self._send(200, "text/html; charset=utf-8", PAGE.encode())
                if p == "/state.json":
                    viewer._seen = time.time()
                    return self._send(200, "application/json", json.dumps(viewer.state()).encode())
                if p == "/shot.jpg":
                    viewer._seen = time.time()
                    return self._send(200, "image/jpeg", viewer.shot) if viewer.shot else self._send(204, "text/plain", b"")
                if p == "/text":
                    return self._send(200, "text/plain; charset=utf-8", (viewer.text or "(nothing read yet)").encode())
                self._send(404, "text/plain", b"not found")

        try:
            self._srv = ThreadingHTTPServer((self.host, self.port), H)
        except OSError as e:
            self.note("viewer_error", {"error": str(e)})
            return self
        self._srv.daemon_threads = True
        threading.Thread(target=self._srv.serve_forever, daemon=True).start()
        return self

    def address(self):
        host = "localhost" if self.host in ("127.0.0.1", "0.0.0.0") else self.host
        return f"http://{host}:{self.port}"


def _demo(argv):
    """Run a few read-only tasks in a loop so the live page has something to show (no Telegram needed)."""
    from .tasks import Tasks
    host = argv[argv.index("--host") + 1] if "--host" in argv else None
    v = Viewer(host=host).start()
    v.force = True
    tasks = [a for a in argv if not a.startswith("--") and a != host] or [
        "summarize https://en.wikipedia.org/wiki/Dropshipping",
        "research what is ePacket shipping",
        "compare bamboo toothbrush",
        "research how to calculate customer acquisition cost",
    ]

    def log(kind, **f):
        v.note(kind, f)
        print(humanize(kind, f), flush=True)

    T = Tasks(log=log, viewer=v)
    print(f"live view at {v.address()}", flush=True)
    while True:
        for t in tasks:
            v.task = t
            out = T.run(t)
            v.task = None
            v.note("report", {"text": out[:300].replace("\n", " ")})
            time.sleep(15)


if __name__ == "__main__":
    if "--demo" in sys.argv:
        _demo(sys.argv[1:])
    else:
        print(__doc__)
