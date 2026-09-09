"""Native Google Docs writer: offline logic test (stubbed API) + optional --live run.

  python3 engine/scripts/score_docs_native.py           # offline: request shapes, ranges, cell order
  python3 engine/scripts/score_docs_native.py --live   # live: create -> write -> read back -> trash (needs Google connected)
"""
import sys

sys.path.insert(0, ".")
from agent.google import Google  # noqa: E402


def P(idx, end=None):
    d = {"paragraph": {"elements": [{"textRun": {"content": "\n"}}]}, "startIndex": idx}
    if end:
        d["endIndex"] = end
    return d


def offline():
    calls = []
    state = {"tabled": False}

    def fake_req(url, method="GET", data=None, headers=None, raw=False, timeout=60):
        import json as _json
        body = _json.loads(data) if data else None
        calls.append(body)
        if "fields=body.content" in url:
            if not state["tabled"]:
                return {"body": {"content": [P(1, 2)]}}
            return {"body": {"content": [
                {"table": {"tableRows": [
                    {"tableCells": [{"content": [P(10)]}, {"content": [P(12)]}]},
                    {"tableCells": [{"content": [P(14)]}, {"content": [P(16)]}]}]},
                 "startIndex": 8, "endIndex": 18},
                P(18, 20)]}}
        if body and any("insertTable" in r for r in body.get("requests", [])):
            state["tabled"] = True
        return {}

    g = Google.__new__(Google)
    g._req = fake_req
    g.docs_write_blocks("D", [("h1", "Hi"), ("p", "body"),
                              ("table", [["a", "b"], ["c", "d"]]), ("bullet", "x")])
    reqs = [r for b in calls if b for r in b.get("requests", [])]
    checks = []
    ins = [(r["insertText"]["location"]["index"], r["insertText"]["text"]) for r in reqs if "insertText" in r]
    u = [r["updateParagraphStyle"] for r in reqs if "updateParagraphStyle" in r]
    b = [r["createParagraphBullets"] for r in reqs if "createParagraphBullets" in r]
    t = [r["insertTable"] for r in reqs if "insertTable" in r]
    checks.append(("first text at index 1", ins[0] == (1, "Hi\n")))
    checks.append(("HEADING_1 style", bool(u) and u[0]["paragraphStyle"]["namedStyleType"] == "HEADING_1"))
    checks.append(("heading range covers paragraph", bool(u) and u[0]["range"] == {"startIndex": 1, "endIndex": 4}))
    checks.append(("2x2 table inserted", len(t) == 1 and t[0]["rows"] == 2 and t[0]["columns"] == 2))
    cells = [i for i, x in ins if x in ("a", "b", "c", "d")]
    checks.append(("cells filled last-first (no index shift)", cells == [16, 14, 12, 10]))
    checks.append(("post-table text after table", [i for i, x in ins if x == "x\n"] == [19]))
    checks.append(("bullet preset set", bool(b) and bool(b[0].get("bulletPreset"))))
    bad = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(("OK   " if ok else "MISS ") + name)
    print(f"NATIVE-DOCS SCORE: {len(checks) - len(bad)}/{len(checks)} (offline)")
    return not bad


def live():
    g = Google()
    if not g.connected():
        print("LIVE SKIP: Google not connected")
        return True
    d = g.docs_create("TEST native writer (safe to delete)")
    try:
        g.docs_write_blocks(d["id"], [("h1", "Live test"), ("p", "unicode: àèéìòù € 39."),
                                      ("table", [["Item", "Price"], ["Lamp", "35"]]),
                                      ("bullet", "point"), ("h2", "Tail"), ("p", "after table.")])
        back = g.docs_get(d["id"])["body"]["content"]
        texts = []

        def walk(el):
            if "paragraph" in el:
                t = "".join(e.get("textRun", {}).get("content", "") for e in el["paragraph"].get("elements", []))
                if t.strip():
                    texts.append(t.strip())
            if "table" in el:
                for r in el["table"]["tableRows"]:
                    for c in r["tableCells"]:
                        for sub in c["content"]:
                            walk(sub)
        for el in back:
            walk(el)
        need = ["Live test", "unicode", "Lamp", "point", "after table"]
        ok = all(any(n.lower() in t.lower() for t in texts) for n in need)
        ok = ok and sum(1 for el in back if "table" in el) == 1
        print("LIVE DOCS API:", "PASS" if ok else "FAIL", f"({len(texts)} texts)")
        return ok
    finally:
        g._req(f"https://www.googleapis.com/drive/v3/files/{d['id']}", method="PATCH",
               data=b'{"trashed": true}', headers={"Content-Type": "application/json"})


if __name__ == "__main__":
    ok = live() if "--live" in sys.argv else offline()
    sys.exit(0 if ok else 1)
