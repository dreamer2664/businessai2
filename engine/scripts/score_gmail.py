"""Score item 6 (Gmail half): threaded replies, read/archive tidy-up, server-side code search.

Offline: a stubbed transport records the HTTP the real Google methods would send.
"""
import base64
import email.message
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent.google import Google, GMAIL

CHECKS = []


def check(name):
    def deco(fn):
        CHECKS.append((name, fn))
        return fn
    return deco


def raw_mail(frm="owner@home.com", subject="status", body="hello there",
             msgid="<abc123@home.com>"):
    m = email.message.EmailMessage()
    m["From"], m["To"], m["Subject"], m["Message-ID"] = frm, "bot@gmail.com", subject, msgid
    m.set_content(body)
    return base64.urlsafe_b64encode(m.as_bytes()).decode()


class StubGoogle(Google):
    """Real Gmail methods, fake HTTP."""

    def __init__(self):
        super().__init__(log=lambda kind, **f: None)
        self.calls = []            # (url, method, data)
        self.list_ids = ["m1"]
        self.raws = {}

    def _req(self, url, method="GET", data=None, headers=None, raw=False, timeout=60):
        self.calls.append((url, method, json.loads(data.decode()) if data else None))
        if url.startswith(f"{GMAIL}/messages/send"):
            return {"id": "sent1", "threadId": "t1"}
        if url.endswith("/modify"):
            return {}
        if "/messages/" in url and not url.startswith(f"{GMAIL}/messages?"):
            mid = url.rsplit("/messages/", 1)[1].split("?")[0]
            return {"threadId": "t1", "labelIds": ["INBOX", "UNREAD"], "snippet": "snip",
                    "raw": self.raws.get(mid, raw_mail())}
        if url.startswith(f"{GMAIL}/messages?"):
            return {"messages": [{"id": i, "threadId": "t1"} for i in self.list_ids]}
        raise AssertionError(f"unexpected url {url}")

    def account(self):
        return "bot@gmail.com"


@check("recent_mail surfaces thread + msgid + labels")
def _():
    g = StubGoogle()
    (m,) = g.recent_mail("newer_than:1d", 5)
    assert m["thread"] == "t1" and m["msgid"] == "<abc123@home.com>", m
    assert "UNREAD" in m["labels"] and m["text"] == "hello there", m


@check("plain send has no thread baggage")
def _():
    g = StubGoogle()
    g.send_mail("a@b.com", "hi", "body")
    (url, method, data), = g.calls
    assert url.endswith("/messages/send") and method == "POST" and set(data) == {"raw"}, data


@check("reply send carries threadId + In-Reply-To")
def _():
    g = StubGoogle()
    g.send_mail("o@h.com", "Re: hi", "body", thread_id="t1", in_reply_to="<abc@h>")
    (url, method, data), = g.calls
    assert data["threadId"] == "t1", data
    raw = base64.urlsafe_b64decode(data["raw"] + "==").decode()
    assert "In-Reply-To: <abc@h>" in raw and "References: <abc@h>" in raw, raw[:300]


@check("mark_read removes UNREAD")
def _():
    g = StubGoogle()
    g.mark_read("m9")
    (url, method, data), = g.calls
    assert url.endswith("/messages/m9/modify") and data == {"removeLabelIds": ["UNREAD"]}, (url, data)


@check("archive removes INBOX")
def _():
    g = StubGoogle()
    g.archive("m9")
    (url, method, data), = g.calls
    assert url.endswith("/messages/m9/modify") and data == {"removeLabelIds": ["INBOX"]}, (url, data)


@check("from-query accepts safe tokens only")
def _():
    assert Google._from_query("fakemarket") == " from:(fakemarket)"
    assert Google._from_query("no-reply regular") == ""
    assert Google._from_query('a" OR b') == ""


@check("find_code searches server-side, reads the code")
def _():
    g = StubGoogle()
    g.raws["m1"] = raw_mail(frm="no-reply@fakemarket.test", subject="Your code",
                            body="Hi, your verification code is 481516. It expires soon.")
    queries = []
    real_recent = g.recent_mail
    g.recent_mail = lambda q, n=10: (queries.append(q), real_recent(q, n))[1]
    import agent.google as gmod
    real_sleep = gmod.time.sleep
    gmod.time.sleep = lambda s: None
    try:
        code, m = g.find_code(sender_hint="fakemarket", tries=1, wait=0)
    finally:
        gmod.time.sleep = real_sleep
    assert code == "481516", (code, m)
    assert queries and "from:(fakemarket)" in queries[0], queries


@check("find_link searches server-side, returns the verify link")
def _():
    g = StubGoogle()
    g.raws["m1"] = raw_mail(frm="n@shop.test", subject="Confirm",
                            body="Click https://shop.test/verify?token=zzz to confirm your email.")
    queries = []
    real_recent = g.recent_mail
    g.recent_mail = lambda q, n=10: (queries.append(q), real_recent(q, n))[1]
    import agent.google as gmod
    real_sleep = gmod.time.sleep
    gmod.time.sleep = lambda s: None
    try:
        link, m = g.find_link(sender_hint="shop", tries=1, wait=0)
    finally:
        gmod.time.sleep = real_sleep
    assert link == "https://shop.test/verify?token=zzz", link
    assert queries and "from:(shop)" in queries[0], queries


@check("thread rejection retries as a plain send")
def _():
    from agent.google import GoogleError
    g = StubGoogle()
    real_req = g._req
    calls = {"n": 0}

    def flaky(url, method="GET", data=None, headers=None, raw=False, timeout=60):
        if url.endswith("/messages/send"):
            calls["n"] += 1
            body = json.loads(data.decode())
            if calls["n"] == 1 and "threadId" in body:
                raise GoogleError("HTTP 400 Invalid threadId")
        return real_req(url, method, data, headers, raw, timeout)

    g._req = flaky
    g.send_mail("o@h.com", "Re: hi", "body", thread_id="t1", in_reply_to="<abc@h>")
    sends = [c for c in g.calls if c[0].endswith("/messages/send")]
    assert calls["n"] == 2 and len(sends) == 1 and "threadId" not in sends[0][2], (calls, sends)
    raw = base64.urlsafe_b64decode(sends[0][2]["raw"] + "==").decode()
    assert "In-Reply-To" not in raw, raw[:200]


def main():
    ok = 0
    for name, fn in CHECKS:
        try:
            fn()
            print(f"OK   {name}")
            ok += 1
        except Exception as e:
            print(f"FAIL {name}: {e!r}")
    print(f"GMAIL SCORE: {ok}/{len(CHECKS)} (offline)")
    return 0 if ok == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
