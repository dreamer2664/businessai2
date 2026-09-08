"""The thinking model ("planner") behind the agent.

Runs a local llama.cpp server (release/llm/llama-server + release/llm/model.gguf, fetched by
scripts/get_model.sh) and talks to it over the OpenAI-compatible API. Any other OpenAI-compatible
endpoint works too: set BAI_LLM_URL (+ BAI_LLM_KEY, BAI_LLM_MODEL) in .secrets/env.

Frugal: the server is started on first use and stopped after IDLE_STOP seconds without a call,
so the RAM (~1.3 GB for the default model) is only taken while the agent is thinking.

Everything it does is grounded: the caller passes evidence (knowledge-pack passages, page text);
the prompt says to answer from the evidence and to say so when the evidence isn't enough.

Public API:
  Planner().available()                   -> bool (starts the local server if needed)
  Planner().intent(message)               -> {"kind": ask|research|summarize|compare|chat|command, "topic": str}
  Planner().answer(question, evidence)    -> str (2-5 sentences, sources named)
  Planner().brief(topic, notes)           -> str (short research brief from several page notes)
  Planner().mcq(question, choices, evidence) -> (index, confidence, raw)
  Planner().chat(system, user, ...)       -> raw completion
"""
import json
import os
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request

from . import config

LLM_DIR = config.ROOT / "release" / "llm"
SERVER_BIN = LLM_DIR / "llama-server"
MODEL_FILE = LLM_DIR / "model.gguf"
PORT = int(os.environ.get("BAI_LLM_PORT", "8091"))
REMOTE_URL = os.environ.get("BAI_LLM_URL", "")
IDLE_STOP = int(os.environ.get("BAI_LLM_IDLE", "600"))
_CPUS = os.cpu_count() or 2
THREADS = os.environ.get("BAI_LLM_THREADS") or str(_CPUS if _CPUS <= 2 else _CPUS - 1)   # tiny machines need both cores (2× faster reading)


def _mem_available_mb():
    try:
        for line in open("/proc/meminfo"):
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024
    except Exception:
        pass
    return 99999

SYSTEM = ("You are the thinking part of a small business AI that helps its owner run an online store (dropshipping, "
          "marketing, suppliers, customers). Be brief, concrete and honest. Use only the EVIDENCE you are given; if it "
          "does not contain the answer, say so plainly. Never invent prices, names, dates or numbers.")

INTENT_PROMPT = """Classify the owner's message for a business assistant. Reply with one JSON object only:
{"kind": KIND, "topic": TOPIC}
KIND is one of:
- "ask": a question that can be answered from general business knowledge (what is X, how does Y work, difference between, is it worth it)
- "research": the owner wants something looked up, checked, found or investigated on the web (find out, look up, check, search, what do people say, latest, prices of)
- "summarize": the message contains a URL to read or summarize
- "compare": the owner wants suppliers / options / prices for a product compared
- "visit": the owner wants me to go to / open a specific website or app and report what is there (open YouTube, go to Amazon bestsellers, check Etsy trending)
- "watch": the owner wants me to watch a video, or videos about a topic, and tell them what it says
- "chat": greetings, thanks, small talk, feedback, or instructions about how to behave
TOPIC is the subject in a few words (for summarize: the URL). Examples:
"can you find out how epacket shipping works" -> {"kind": "research", "topic": "how ePacket shipping works"}
"what is a good margin for dropshipping" -> {"kind": "ask", "topic": "good profit margin for dropshipping"}
"look for suppliers of bamboo toothbrushes" -> {"kind": "compare", "topic": "bamboo toothbrush"}
"thanks that was useful" -> {"kind": "chat", "topic": "thanks"}
"open youtube and list the top 5 trending videos" -> {"kind": "visit", "topic": "youtube | list the top 5 trending videos"}
"watch a video about facebook ads for beginners and tell me what you learned" -> {"kind": "watch", "topic": "facebook ads for beginners"}
"go to amazon and tell me the bestsellers in kitchen" -> {"kind": "visit", "topic": "amazon | bestsellers in kitchen"}
For "visit", TOPIC is "<site> | <what to report>".
Message: """


class Planner:
    def __init__(self, log=None):
        self.log = log or (lambda kind, **f: None)
        self.remote = bool(REMOTE_URL)
        self.url = REMOTE_URL or f"http://127.0.0.1:{PORT}/v1/chat/completions"
        self.model = os.environ.get("BAI_LLM_MODEL", "local")
        self.key = os.environ.get("BAI_LLM_KEY", "")
        self._proc = None
        self.last_error = ""
        self._lock = threading.Lock()
        self.last_used = 0
        self.calls = self.tokens = 0

    # ---- local server lifecycle -----------------------------------------
    def installed(self):
        return self.remote or (SERVER_BIN.exists() and MODEL_FILE.exists())

    def _ping(self, timeout=2):
        try:
            with urllib.request.urlopen(self.url.rsplit("/v1/", 1)[0] + "/health", timeout=timeout) as r:
                return r.status == 200
        except Exception:
            return False

    def _start(self):
        if self.remote or (self._proc and self._proc.poll() is None):
            return True
        if not self.installed():
            return False
        env = dict(os.environ, LD_LIBRARY_PATH=str(LLM_DIR) + ":" + os.environ.get("LD_LIBRARY_PATH", ""))
        self.last_error = ""
        self._self_repair(env)
        config.LOG_DIR.mkdir(parents=True, exist_ok=True)
        config.LOG_DIR.mkdir(parents=True, exist_ok=True)                # a fresh state dir has no logs/ yet
        logf = open(config.LOG_DIR / "llm.log", "ab")
        args = [str(SERVER_BIN), "-m", str(MODEL_FILE), "--host", "127.0.0.1", "--port", str(PORT),
                "-c", "4096", "-np", "1", "-t", THREADS, "--no-warmup"]
        if _mem_available_mb() < 2000:
            # small machines: keep the weights memory-mapped (evictable) instead of copied into private RAM,
            # otherwise the browser + model together get the model killed by the kernel (OOM)
            args.append("--no-repack")
        try:
            self._proc = subprocess.Popen(args, env=env, stdout=logf, stderr=subprocess.STDOUT)
        except OSError as e:
            self.last_error = f"cannot execute llama-server: {e}"
            self.log("llm_start_failed", error=self.last_error)
            return False
        t0 = time.time()
        while time.time() - t0 < 180:
            if self._ping():
                self.log("llm_started", ms=int((time.time() - t0) * 1000))
                return True
            if self._proc.poll() is not None:
                break
            time.sleep(0.5)
        self.last_error = self._diagnose()
        self.log("llm_start_failed", error=self.last_error)
        self._proc = None
        return False

    STATIC_URL = "https://github.com/%s/%s/releases/download/latest/llama-server-static" % (
        os.environ.get("GH_OWNER", "dreamer2664"), os.environ.get("GH_REPO", "businessai2"))

    def _self_repair(self, env):
        """An old install may carry the upstream llama-server that needs system libraries (libgomp, newer glibc).
        If the binary cannot even print its version, swap in the project's self-contained static build (16 MB)."""
        try:
            r = subprocess.run([str(SERVER_BIN), "--version"], env=env, capture_output=True, timeout=20)
            out = (r.stdout + r.stderr).decode(errors="replace").lower()
            if r.returncode == 0 and "version" in out:
                return
        except Exception as e:
            out = str(e).lower()
        if not ("shared librar" in out or "glibc" in out or "not found" in out or "no such file" in out or "exec format" in out):
            return
        self.log("llm_repair", reason=out.strip()[-160:])
        try:
            import urllib.request
            tmp = SERVER_BIN.with_suffix(".new")
            with urllib.request.urlopen(self.STATIC_URL, timeout=120) as resp, open(tmp, "wb") as f:
                while True:
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
            os.chmod(tmp, 0o755)
            r = subprocess.run([str(tmp), "--version"], capture_output=True, timeout=20)
            if r.returncode == 0:
                os.replace(tmp, SERVER_BIN)
                for so in LLM_DIR.glob("*.so*"):
                    so.unlink()
                self.log("llm_repaired", size=SERVER_BIN.stat().st_size)
            else:
                tmp.unlink(missing_ok=True)
                self.log("llm_repair_failed", error=(r.stdout + r.stderr).decode(errors="replace")[-160:])
        except Exception as e:
            self.log("llm_repair_failed", error=str(e)[:160])

    def _diagnose(self):
        """Human-readable reason the local server did not come up (last lines of its log + common causes)."""
        try:
            tail = (config.LOG_DIR / "llm.log").read_text(errors="replace")[-3000:]
        except Exception:
            tail = ""
        low = tail.lower()
        if not SERVER_BIN.exists() or not MODEL_FILE.exists():
            return "not installed — run: sh scripts/get_model.sh"
        if not os.access(SERVER_BIN, os.X_OK):
            return "llama-server is not executable — run: chmod +x release/llm/llama-server"
        if "glibc" in low or "glibcxx" in low or "shared librar" in low or ("not found" in low and ".so" in low):
            return "the installed llama-server needs system libraries this machine lacks — run: sh scripts/get_model.sh (it swaps in the self-contained build), then restart me"
        if "cannot allocate" in low or "out of memory" in low or "failed to allocate" in low:
            return "not enough free RAM to load the model (~1.3 GB needed) — close other programs or pick a smaller model"
        if "address already in use" in low:
            return f"port {PORT} is taken — set BAI_LLM_PORT to another port"
        if "illegal instruction" in low:
            return "this CPU lacks instructions the build expects — run: sh scripts/get_model.sh --build"
        last = [l for l in tail.splitlines() if l.strip()][-3:]
        return "server exited: " + (" | ".join(last)[:300] if last else "no output — try running it by hand: sh scripts/get_model.sh --test")

    def stop(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(10)
            except Exception:
                self._proc.kill()
            self.log("llm_stopped")
        self._proc = None

    def tick(self):
        """Call periodically: frees the RAM after IDLE_STOP seconds without a call."""
        if self._proc and not self._lock.locked() and time.time() - self.last_used > IDLE_STOP:
            self.stop()

    def available(self):
        if self.remote:
            return True
        return self._ping() or self._start()

    def describe(self):
        if not self.installed():
            return "thinking model: not installed (sh scripts/get_model.sh)"
        if getattr(self, "last_error", ""):
            return f"thinking model: NOT RUNNING — {self.last_error}"
        where = "remote " + re.sub(r"^https?://([^/]+).*", r"\1", self.url) if self.remote else f"local {MODEL_FILE.stat().st_size >> 20} MB"
        state = "running" if (self.remote or self._ping()) else "asleep"
        return f"thinking model: {where}, {state}, {self.calls} calls"

    # ---- raw chat ---------------------------------------------------------
    def chat(self, system, user, max_tokens=256, temperature=0.0, timeout=180, stop=None):
        if getattr(threading.current_thread(), 'filler', False) and getattr(self, 'abort_filler', False):
            raise RuntimeError('self-training preempted by the owner')
        with self._lock:
            if not self.available():
                raise RuntimeError("thinking model not available")
            body = {"model": self.model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                    "max_tokens": max_tokens, "temperature": temperature, "cache_prompt": False}
            if stop:
                body["stop"] = stop
            req = urllib.request.Request(self.url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
            if self.key:
                req.add_header("Authorization", f"Bearer {self.key}")
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.loads(r.read().decode())
            self.last_used = time.time()
            self.calls += 1
            self.tokens += int(d.get("usage", {}).get("total_tokens", 0))
            self.log("llm_call", ms=int((time.time() - t0) * 1000), tokens=d.get("usage", {}).get("total_tokens"))
            return d["choices"][0]["message"]["content"].strip()

    # ---- skills -----------------------------------------------------------
    def intent(self, message):
        """What does the owner want? Cheap regex first; the model only for the unclear middle."""
        m = message.strip()
        low = m.lower()
        url = re.search(r"https?://\S+", m)
        if url and re.search(r"youtube\.com/watch|youtu\.be/|youtube\.com/shorts", url.group(0)):
            return {"kind": "watch", "topic": url.group(0)}
        if url:
            return {"kind": "summarize", "topic": url.group(0)}
        mw = re.search(r"\b(?:watch|look at)\s+(?:a|some|the)?\s*(?:youtube\s+)?videos?\s+(?:about|on|of)\s+(.+?)(?:\s+and\s+tell.*|\s+then.*)?$", low)
        if mw:
            return {"kind": "watch", "topic": mw.group(1).strip(" ?.")}
        if re.search(r"^(hi|hello|hey|thanks|thank you|ok|okay|good (morning|evening|night)|bye)\b", low) and len(low) < 40:
            return {"kind": "chat", "topic": m}
        mv = re.search(r"\b(?:open|go to|goto|visit|check out|look at|browse)\s+(?:the\s+)?([a-z][a-z0-9 .-]{1,25}?)(?:\s+(?:and|,|to|then)\s+|\s*$)(.*)", low)
        if mv and not url:
            return {"kind": "visit", "topic": f"{mv.group(1).strip()} | {mv.group(2).strip(' ?.')}"}
        if re.search(r"\b(find|look|search|check|research|investigate|dig|see what|what do people|latest|current|today)\b", low) and \
           re.search(r"\b(supplier|suppliers|vendors?|wholesale|manufacturer)s?\b", low) and re.search(r"\b(compare|options|prices?|for)\b", low):
            return {"kind": "compare", "topic": re.sub(r".*\b(of|for)\b", "", low).strip(" ?.") or m}
        try:
            raw = self.chat("You classify messages. Output JSON only.", INTENT_PROMPT + json.dumps(m), max_tokens=60, stop=["\n\n"])
            j = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
            kind = j.get("kind", "ask")
            if kind not in ("ask", "research", "summarize", "compare", "chat", "visit", "watch"):
                kind = "ask"
            return {"kind": kind, "topic": str(j.get("topic") or m)[:120]}
        except Exception as e:
            self.log("intent_fallback", error=str(e)[:80])
            wants_web = bool(re.search(r"\b(find|look up|search|check|research|investigate|latest|current|online)\b", low))
            return {"kind": "research" if wants_web else "ask", "topic": re.sub(r"^(can you|could you|please|would you)\s+", "", low).strip(" ?.")}

    def answer(self, question, evidence, max_tokens=220):
        ev = (evidence or "").strip()[:5000] or "(no evidence found)"
        user = (f"EVIDENCE:\n{ev}\n\nOWNER'S QUESTION: {question}\n\n"
                "Write the answer for the owner in 2-5 plain sentences, using only the evidence. Include concrete numbers or steps when "
                "the evidence has them. End with one line 'Sources: ' naming the source titles you used. If the evidence does not "
                "answer the question, say what is missing instead of guessing.")
        return self.chat(SYSTEM, user, max_tokens=max_tokens)

    def brief(self, topic, notes, max_tokens=300):
        """notes: list of (title, url, [key sentences]) → one short brief with sources."""
        ev = "\n\n".join(f"[{i+1}] {t}\n{u}\n" + "\n".join(f"- {s}" for s in ks) for i, (t, u, ks) in enumerate(notes))
        user = (f"NOTES FROM {len(notes)} WEB PAGES:\n{ev[:5500]}\n\nTOPIC: {topic}\n\n"
                "Write a short brief for the owner: first a 2-4 sentence direct answer, then up to 4 bullet points with the most useful "
                "concrete facts (numbers, steps, warnings). Cite pages as [1], [2]. Do not add anything that is not in the notes.")
        return self.chat(SYSTEM, user, max_tokens=max_tokens)

    def mcq(self, question, choices, evidence):
        letters = "ABCDEFGH"
        opts = "\n".join(f"{letters[i]}. {c}" for i, c in enumerate(choices))
        ev = (evidence or "").strip()[:3500] or "(none)"
        user = (f"EVIDENCE:\n{ev}\n\nQUESTION: {question}\n{opts}\n\nReply with exactly one line: 'Answer: <letter>' then "
                "'Confidence: high|medium|low'.")
        raw = self.chat(SYSTEM, user, max_tokens=24)
        m = re.search(r"Answer:\s*\(?([A-H])\b", raw) or re.search(r"\b([A-H])[.)]", raw) or re.search(r"\b([A-H])\b", raw)
        idx = letters.index(m.group(1)) if m and letters.index(m.group(1)) < len(choices) else 0
        cm = re.search(r"Confidence:\s*(high|medium|low)", raw, re.I)
        conf = {"high": 0.9, "medium": 0.6, "low": 0.3}.get((cm.group(1).lower() if cm else "medium"), 0.6)
        return idx, conf, raw

    def reply(self, message):
        """Small talk / instructions, no evidence needed."""
        return self.chat("You are a friendly, concise business assistant talking to your owner on Telegram. One or two sentences.",
                         message, max_tokens=60, temperature=0.3)
