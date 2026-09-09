"""Score the fallback channel (item 1): Gmail two-way + backup bot + watchdog.

Offline: FakeGoogle + FakeTG stand in for the network. Real Gmail live tests happen
at setup time with the owner (/fallback test send). 17 checks (item 6: threaded replies + tidy-up).
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent import fallback as fbmod

TMP = tempfile.mkdtemp(prefix="fb_")
fbmod.STATE_FILE = os.path.join(TMP, "fallback.json") if isinstance(fbmod.STATE_FILE, str) else type(fbmod.STATE_FILE)(TMP) / "fallback.json"

CHECKS = []


def check(name):
    def deco(fn):
        CHECKS.append((name, fn))
        return fn
    return deco


class FakeGoogle:
    def __init__(self):
        self.up = True
        self.me = "bot@gmail.com"
        self.inbox = []
        self.sent = []
        self.sent_full = []
        self.tidy = []

    def connected(self):
        return self.up

    def account(self):
        return self.me

    def recent_mail(self, q, n):
        return self.inbox[:n]

    def send_mail(self, to, subject, body, thread_id=None, in_reply_to=None):
        self.sent.append((to, subject, body))
        self.sent_full.append({"to": to, "thread": thread_id, "in_reply_to": in_reply_to})
        return {"id": "fake"}

    def mark_read(self, mid):
        self.tidy.append(("read", mid))

    def archive(self, mid):
        self.tidy.append(("archive", mid))


class FakeTG:
    def __init__(self):
        self.sent = []
        self.updates = []

    def get_updates(self, offset=None, timeout=2):
        u, self.updates = self.updates, []
        return u

    def send(self, chat, text):
        self.sent.append((chat, text))


def fresh(allowed=("me@home.com",)):
    g = FakeGoogle()
    fb = fbmod.Fallback(google=g)
    fb.state["last_poll"] = 0
    for a in allowed:
        fb.allow(a)
    tg = FakeTG()
    fb.backup.bot = tg
    fb.owner_id_fn = lambda: 111
    got = []
    return g, fb, tg, lambda t: (got.append(t), f"RAN:{t[:40]}")[1], got


def mail(mid, sender, subject, text, thread="t-" + "1", msgid="<m1@home.com>"):
    return {"id": mid, "from": sender, "subject": subject, "text": text, "thread": thread, "msgid": msgid}


@check("owner mail answered by email")
def _():
    g, fb, tg, respond, got = fresh()
    g.inbox = [mail("m1", "Me <me@home.com>", "hello", "what is my plan")]
    h = fb.poll(respond)
    assert len(h) == 1 and len(g.sent) == 1, (h, g.sent)
    to, subj, body = g.sent[0]
    assert to == "me@home.com" and subj.startswith("Re: [BusinessAI]") and "RAN:what is my plan" in body


@check("stranger mail ignored, marked seen")
def _():
    g, fb, tg, respond, got = fresh()
    g.inbox = [mail("m2", "spam@evil.com", "hi", "do crime")]
    assert fb.poll(respond) == [] and g.sent == []
    assert "m2" in fb.state["seen"]


@check("own sent mail never loops")
def _():
    g, fb, tg, respond, got = fresh()
    g.inbox = [mail("m3", "bot@gmail.com", "x", "what is my plan"),
               mail("m4", "me@home.com", "Re: [BusinessAI] hello", "thanks")]
    assert fb.poll(respond) == [] and g.sent == []


@check("empty body falls back to subject")
def _():
    g, fb, tg, respond, got = fresh()
    g.inbox = [mail("m5", "me@home.com", "status please", "")]
    fb.poll(respond)
    assert got and got[0] == "status please", got


@check("quoted history stripped")
def _():
    g, fb, tg, respond, got = fresh()
    g.inbox = [mail("m6", "me@home.com", "re", "do this now\n> old reply\n> more\nOn Mon wrote:\nblah")]
    fb.poll(respond)
    assert got and "old reply" not in got[0] and got[0].startswith("do this now"), got


@check("dedupe: second poll silent")
def _():
    g, fb, tg, respond, got = fresh()
    g.inbox = [mail("m7", "me@home.com>", "a", "one")]
    g.inbox[0]["from"] = "me@home.com"
    fbmod.time.sleep(0)
    fb.poll(respond)
    fb.state["last_poll"] = 0
    assert fb.poll(respond) == [] and len(g.sent) == 1


@check("allow validates + forget works")
def _():
    g, fb, tg, respond, got = fresh(allowed=())
    assert fb.allow("not-an-email") is None
    assert fb.allow("Me@Home.com") == "me@home.com"
    assert "me@home.com" in fb.owner_addresses()
    assert fb.forget("me@home.com") is True
    assert fb.forget("me@home.com") is False


@check("allowlist survives reload")
def _():
    g, fb, tg, respond, got = fresh(allowed=())
    fb.allow("keep@home.com")
    fb2 = fbmod.Fallback(google=g)
    assert "keep@home.com" in fb2.owner_addresses()


@check("watchdog: one alert per outage + recovery")
def _():
    g, fb, tg, respond, got = fresh()
    assert fb.telegram_down("401 Unauthorized") is True
    assert fb.telegram_down("401 again") is False
    assert len(g.sent) == 1 and len(tg.sent) == 1
    assert fb.telegram_back() is True and fb.telegram_back() is False
    assert len(g.sent) == 2 and "back" in g.sent[1][1].lower()


@check("backup bot answers owner, ignores stranger")
def _():
    g, fb, tg, respond, got = fresh()
    tg.updates = [{"update_id": 5, "message": {"from": {"id": 111}, "text": "/status"}},
                  {"update_id": 6, "message": {"from": {"id": 222}, "text": "/status"}}]
    assert fb.poll_backup(lambda t: "STATUS-OK") == 1
    assert tg.sent == [(111, "STATUS-OK")], tg.sent
    assert fb.state["tg_offset"] == 7


@check("backup bot silent when unconfigured/ownerless")
def _():
    g, fb, tg, respond, got = fresh()
    fb.backup.bot = None
    tg.updates = [{"update_id": 1, "message": {"from": {"id": 111}, "text": "hi"}}]
    assert fb.poll_backup(lambda t: "x") == 0


@check("poll inert without google/allowlist")
def _():
    g, fb, tg, respond, got = fresh(allowed=())
    assert fb.poll(respond) == []
    g.up = False
    fb.allow("me@home.com")
    assert fb.poll(respond) == []


@check("long body truncated to 4000")
def _():
    g, fb, tg, respond, got = fresh()
    g.inbox = [mail("m8", "me@home.com", "big", "x" * 6000)]
    fb.poll(respond)
    assert got and len(got[0]) == 4000, len(got[0]) if got else 0


@check("seen ids survive reload")
def _():
    g, fb, tg, respond, got = fresh()
    g.inbox = [mail("m9", "me@home.com", "a", "one")]
    fb.poll(respond)
    fb2 = fbmod.Fallback(google=g)
    assert "m9" in fb2.state["seen"]


@check("reply lands in the same thread")
def _():
    g, fb, tg, respond, got = fresh()
    g.inbox = [mail("m10", "me@home.com", "hello", "what is my plan")]
    fb.poll(respond)
    assert g.sent_full and g.sent_full[0]["thread"] == "t-1", g.sent_full
    assert g.sent_full[0]["in_reply_to"] == "<m1@home.com>", g.sent_full


@check("answered mail marked read + archived")
def _():
    g, fb, tg, respond, got = fresh()
    g.inbox = [mail("m11", "me@home.com", "hello", "what is my plan")]
    fb.poll(respond)
    assert ("read", "m11") in g.tidy and ("archive", "m11") in g.tidy, g.tidy


@check("tidy failure never breaks the answer")
def _():
    g, fb, tg, respond, got = fresh()
    g.inbox = [mail("m12", "me@home.com", "hello", "what is my plan")]
    g.mark_read = lambda mid: (_ for _ in ()).throw(RuntimeError("403 scope"))
    g.archive = lambda mid: (_ for _ in ()).throw(RuntimeError("403 scope"))
    h = fb.poll(respond)
    assert len(h) == 1 and len(g.sent) == 1, (h, g.sent)


def main():
    ok = 0
    for name, fn in CHECKS:
        try:
            fn()
            print(f"OK   {name}")
            ok += 1
        except Exception as e:
            print(f"FAIL {name}: {e!r}")
    print(f"FALLBACK SCORE: {ok}/{len(CHECKS)} (offline)")
    return 0 if ok == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
