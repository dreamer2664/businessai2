"""Score item 8 (pack #3 seed): URL list + question set + grounding + feed logic. Offline. 10 checks.

The full knowledge score (score_pack.py) needs the C engine, so it runs on the PC after the build.
"""
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

sys.path.insert(0, os.path.join(ROOT, "packs"))
import feed_add

STOP = set("the and for with from that this your you are was were have has had will would can not but they their them then than into over under about after before between through while where which when what more most other such only also very our its his her she him out off any all each every both few many much same too just don should now into onto per via cos sin".split())

CHECKS = []


def check(name):
    def deco(fn):
        CHECKS.append((name, fn))
        return fn
    return deco


def terms():
    return {l.strip() for l in open(os.path.join(ROOT, "packs/sources/dropship_terms.txt"), encoding="utf-8")
            if l.strip() and not l.startswith("#")}


def questions():
    out, block = [], ""
    for line in open(os.path.join(ROOT, "tests/dropship.txt"), encoding="utf-8"):
        line = line.rstrip("\n")
        if line.startswith("## "):
            block = line[3:]
        elif line and not line.startswith("#") and "\t" in line:
            q, acc = line.split("\t", 1)
            out.append((block, q, acc))
    return out


def content_words(s):
    return [w for w in re.findall(r"[a-z0-9]{3,}", s.lower()) if w not in STOP]


@check("url list: 30+ verified http urls, no dupes")
def _():
    rows = [l.rstrip("\n").split("\t") for l in open(os.path.join(ROOT, "packs/sources/web_urls_dropship.tsv"), encoding="utf-8") if "\t" in l]
    assert len(rows) >= 30, len(rows)
    urls = [r[1] for r in rows]
    assert all(u.startswith("http") for u in urls)
    assert len(set(urls)) == len(urls), "dupes"


@check("question set: 30+ questions in 4+ blocks")
def _():
    qs = questions()
    assert len(qs) >= 30, len(qs)
    assert len({b for b, _, _ in qs}) >= 4
    assert all(q and acc for _, q, acc in qs)


@check("grounding: every question has an alternative covered by the term index")
def _():
    t = terms()
    bad = []
    for b, q, acc in questions():
        ok = any((cw := content_words(a)) and all(w in t for w in cw) for a in acc.split("|"))
        if not ok:
            bad.append(q)
    assert not bad, bad


@check("term index: header + thousands of terms")
def _():
    head = [l for l in open(os.path.join(ROOT, "packs/sources/dropship_terms.txt"), encoding="utf-8") if l.startswith("#")]
    assert any("passages" in l for l in head) and len(terms()) > 2000, len(terms())


@check("feed: appends renumber aids, links intact")
def _():
    d = tempfile.mkdtemp(prefix="feed_")
    ext, stg = os.path.join(d, "ext"), os.path.join(d, "stg")
    os.makedirs(ext)
    os.makedirs(stg)
    open(os.path.join(ext, "articles.tsv"), "w").write("0\tp0\tt0\n")
    open(os.path.join(ext, "passages.tsv"), "w").write("0\told passage\n")
    open(os.path.join(stg, "articles.tsv"), "w").write("0\tp1\tt1\n1\tp2\tt2\n")
    open(os.path.join(stg, "passages.tsv"), "w").write("0\tnew one\n1\tnew two\n7\torphan (stale aid)\n")
    na, np_ = feed_add.append_ext(ext, stg)
    assert (na, np_) == (2, 2), (na, np_)
    arts = feed_add.read_tsv(os.path.join(ext, "articles.tsv"))
    passe = feed_add.read_tsv(os.path.join(ext, "passages.tsv"))
    assert [r[0] for r in arts] == ["0", "1", "2"], arts
    assert {r[0] for r in passe} == {"0", "1", "2"}, passe
    assert passe[0][1] == "old passage" and "orphan" not in open(os.path.join(ext, "passages.tsv")).read()


@check("feed: already-listed urls are skipped")
def _():
    d = tempfile.mkdtemp(prefix="feed_")
    tsv = os.path.join(d, "u.tsv")
    open(tsv, "w").write("suppliers\thttps://have.it/x\n")
    rc = feed_add.main([tsv, os.path.join(d, "ext"), "https://have.it/x"])
    assert rc == 0 and len(open(tsv).readlines()) == 1


@check("feed: garbage args rejected")
def _():
    d = tempfile.mkdtemp(prefix="feed_")
    assert feed_add.main([os.path.join(d, "u.tsv"), os.path.join(d, "ext"), "not-a-url"]) == 1
    assert feed_add.main([os.path.join(d, "u.tsv")]) == 1


@check("feed: usage line sane")
def _():
    assert "feed_add.py" in feed_add.__doc__ and "--topic" in feed_add.__doc__


@check("PACKS.md documents the seed + build + feed")
def _():
    doc = open(os.path.join(ROOT, "docs/PACKS.md"), encoding="utf-8").read()
    for s in ("dropship.kdw", "web_urls_dropship.tsv", "build_pack.py", "feed_add.py", "score_dropship.py"):
        assert s in doc, s


@check("question alternatives look like answer spans, not single letters")
def _():
    for b, q, acc in questions():
        for a in acc.split("|"):
            assert len(a.strip()) >= 2, (q, a)


def main():
    ok = 0
    for name, fn in CHECKS:
        try:
            fn()
            print(f"OK   {name}")
            ok += 1
        except Exception as e:
            print(f"FAIL {name}: {e!r}")
    print(f"DROPSHIP SEED SCORE: {ok}/{len(CHECKS)} (offline)")
    return 0 if ok == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
