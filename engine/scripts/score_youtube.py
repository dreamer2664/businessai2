"""Score item 4: YouTube trending + top comments + topic tops. Offline fixtures; --live hits real YouTube."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent import video
from agent.tasks import Tasks

CHECKS = []


def check(name):
    def deco(fn):
        CHECKS.append((name, fn))
        return fn
    return deco


TRENDING_HTML = """
<ytd-video-renderer><a id="video-title" href="/watch?v=AAA111BBB22" title="Pasta &amp; Love">x</a>
<ytd-channel-name><a href="/@pastalover">Pasta Lover</a></ytd-channel-name><span>1.2M views</span><span>3 days ago</span></ytd-video-renderer>
<ytd-video-renderer><a id="video-title" href="/watch?v=CCC333DDD44" title="I Built A Cabin">x</a>
<ytd-channel-name><a href="/@woods">Woods</a></ytd-channel-name><span>345K views</span><span>1 day ago</span></ytd-video-renderer>
<a href="/shorts/SHO456RTS78" title="short clip">short</a>
<a href="/watch?v=EEE555FFF66">no title here</a>
<ytd-video-renderer><a id="video-title" href="/watch?v=EEE555FFF66" title="News Tonight">x</a>
<ytd-channel-name><a href="/@news">News</a></ytd-channel-name><span>2,876 views</span></ytd-video-renderer>
"""

COMMENTS_HTML = """
<ytd-comment-thread-renderer><span id="author-text"><span>Luigi</span></span>
<span id="content-text"><span>Second here, great video.</span></span><span id="vote-count-middle">45</span></ytd-comment-thread-renderer>
<ytd-comment-thread-renderer><span id="author-text"><span>Mario</span></span>
<span id="content-text"><span>This <b>changed</b> my life &amp; my kitchen.</span></span><span id="vote-count-middle">1.2K</span></ytd-comment-thread-renderer>
<ytd-comment-thread-renderer><span id="author-text"><span>Anon</span></span>
<span id="content-text"><span>ok</span></span><span id="vote-count-middle"></span></ytd-comment-thread-renderer>
"""

JSON_HTML = '"videoRenderer":{"videoId":"ZZZ999YYY88","title":{"runs":[{"text":"JSON Title"}]},"viewCountText":{"simpleText":"45K views"},"longBylineText"'


@check("trending ids in order")
def _():
    v = video.extract_trending(TRENDING_HTML)
    assert [e["id"] for e in v] == ["AAA111BBB22", "CCC333DDD44", "EEE555FFF66"], v


@check("trending titles unescaped")
def _():
    v = video.extract_trending(TRENDING_HTML)
    assert v[0]["title"] == "Pasta & Love", v[0]


@check("trending views parsed")
def _():
    v = video.extract_trending(TRENDING_HTML)
    assert [e["views"] for e in v] == [1200000, 345000, 2876], v


@check("trending channels parsed")
def _():
    v = video.extract_trending(TRENDING_HTML)
    assert [e["channel"] for e in v] == ["Pasta Lover", "Woods", "News"], v


@check("shorts + title-less links skipped")
def _():
    v = video.extract_trending(TRENDING_HTML)
    assert all(len(e["id"]) == 11 and e["title"] for e in v) and len(v) == 3


@check("embedded-JSON fallback works")
def _():
    v = video.extract_trending(JSON_HTML)
    assert v and v[0]["id"] == "ZZZ999YYY88" and v[0]["views"] == 45000, v


@check("comments authors + clean text")
def _():
    c = video.extract_comments(COMMENTS_HTML)
    mario = next(x for x in c if x["author"] == "Mario")
    assert mario["text"] == "This changed my life & my kitchen.", mario


@check("comments likes parsed + sorted")
def _():
    c = video.extract_comments(COMMENTS_HTML)
    assert [(x["author"], x["likes"]) for x in c] == [("Mario", 1200), ("Luigi", 45), ("Anon", 0)], c


@check("parse_views table")
def _():
    cases = {"1.2M views": 1200000, "45K": 45000, "3,456": 3456, "2.5B views": 2500000000,
             "12 watching": 12, "": 0, "no views yet": 0, "7": 7}
    for s, want in cases.items():
        assert video.parse_views(s) == want, (s, video.parse_views(s))


@check("empty html gives empty lists")
def _():
    assert video.extract_trending("<html></html>") == []
    assert video.extract_comments("<html></html>") == []


@check("topic_top formats ranked videos")
def _():
    real = video.top_for_topic
    video.top_for_topic = lambda q, n: [{"id": "AAA111BBB22", "title": "Best Pasta", "views": 5000},
                                        {"id": "CCC333DDD44", "title": "Ok Pasta", "views": 100}]
    try:
        out = Tasks(log=lambda k, **f: None).topic_top("pasta")
    finally:
        video.top_for_topic = real
    assert "Most-watched" in out and "5,000 views" in out and "watch?v=AAA111BBB22" in out, out


@check("trending without a browser says so cleanly")
def _():
    try:
        import playwright  # noqa
        have = True
    except ImportError:
        have = False
    out = Tasks(log=lambda k, **f: None).youtube_trending()
    if have:
        assert "trending" in out.lower()
    else:
        assert "PC" in out, out


LIVE = []


def live(name):
    def deco(fn):
        LIVE.append((name, fn))
        return fn
    return deco


@live("real search ranks videos with views")
def _():
    v = video.top_for_topic("pasta recipe", 6)
    assert len(v) >= 3, v
    assert all(len(e["id"]) == 11 for e in v)
    assert sum(1 for e in v if e["views"] > 0) >= 1, v
    print("   top:", v[0]["title"][:60], f"({v[0]['views']:,} views)")


@live("real transcript still flows")
def _():
    import urllib.error
    v = video.top_for_topic("pasta recipe", 3)
    try:
        text, meta = video.transcript(v[0]["id"])
    except urllib.error.HTTPError as e:
        if e.code == 429:
            print("   SKIP: caption CDN throttles this datacenter IP (player API is fine) — the PC verifies")
            return "skip"
        raise
    print(f"   transcript: {len(text)} chars, lang={meta.get('language')}, auto={meta.get('auto')}")
    assert len(text) > 200 or meta.get("title"), meta


def main(argv):
    if "--live" in argv:
        ok = skip = 0
        for name, fn in LIVE:
            try:
                r = fn()
                if r == "skip":
                    print(f"SKIP {name}")
                    skip += 1
                else:
                    print(f"OK   {name}")
                    ok += 1
            except Exception as e:
                print(f"FAIL {name}: {e!r}")
        print(f"YOUTUBE LIVE: {ok} ok, {skip} skipped, {len(LIVE) - ok - skip} failed")
        return 0 if ok + skip == len(LIVE) else 1
    ok = 0
    for name, fn in CHECKS:
        try:
            fn()
            print(f"OK   {name}")
            ok += 1
        except Exception as e:
            print(f"FAIL {name}: {e!r}")
    print(f"YOUTUBE SCORE: {ok}/{len(CHECKS)} (offline)")
    return 0 if ok == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
