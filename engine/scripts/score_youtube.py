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


@check("youtube_trending when YouTube is unreachable: one clear sentence, no traceback, no browser needed")
def _():
    real_hot = video.hot_now
    video.hot_now = lambda topic, n, period="week": (_ for _ in ()).throw(OSError("network down"))
    try:
        out = Tasks(log=lambda k, **f: None).youtube_trending(limit=3)
    finally:
        video.hot_now = real_hot
    assert out.startswith("I couldn't read YouTube right now") and "/trending <topic>" in out, out


FX = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "tests", "fixtures")


def _fx(name):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return f.read()


@check("ytInitialData search reader: 6 real cards with id/title/channel/views/published/length (fixture from the live page)")
def _():
    vs = video.videos_from(_fx("yt_search_2026-09.html"))
    assert [v["id"] for v in vs][:2] == ["EBj5aaiXQ68", "_KmXbRiJVyg"] and len(vs) == 6, vs
    v = vs[1]
    assert v["channel"] == "Jordan Welch" and v["views"] == 513787 and v["published"] == "7 months ago" and v["length"] == "19:47" and v["seconds"] == 1187, v
    assert "NOTAVIDEO12" not in {x["id"] for x in vs}, "picked a videoRenderer outside ytInitialData"
    assert video.videos_from("<html>no data</html>") == [] and video.initial_data("garbage") == {}


@check("search() keeps its old shape (id, title) and adds url/views/channel")
def _():
    real = video._get
    video._get = lambda u, timeout=25: _fx("yt_search_2026-09.html")
    try:
        r = video.search("x", 3)
    finally:
        video._get = real
    assert len(r) == 3 and r[0]["id"] == "EBj5aaiXQ68" and r[0]["url"].endswith("EBj5aaiXQ68") and "title" in r[0], r


@check("search_videos sorts by views / by date and builds YouTube's own filter codes")
def _():
    real = video._get
    seen = []
    video._get = lambda u, timeout=25: (seen.append(u), _fx("yt_search_2026-09.html"))[1]
    try:
        by_views = video.search_videos("dropshipping", n=3, sort="views", period="week")
        by_date = video.search_videos("dropshipping", n=3, sort="date")
    finally:
        video._get = real
    assert "sp=CAMSAggD" in seen[0] and "sp=CAI%3D" in seen[1], seen
    assert by_views[0]["views"] >= by_views[1]["views"] >= by_views[2]["views"], by_views
    assert video._age_minutes("3 days ago") < video._age_minutes("2 months ago") < video._age_minutes("") and video._age_minutes("3w ago") == 30240
    assert by_date[0]["published"] == "3 hours ago" and by_date[1]["published"] == "3 days ago", by_date


@check("comments: the watch page's continuation token + the /next JSON → most-liked first")
def _():
    assert video.comment_token(_fx("yt_watch_2026-09.html")) == "FAKE_COMMENT_TOKEN_123"
    assert video.comment_token("<html></html>") is None
    cs = video.comments_from(_fx("yt_comments_2026-09.json"), 3)
    assert [c["author"] for c in cs] == ["@amo_morenitas", "@George71726", "@JordanWelch"] and cs[0]["likes"] == 192, cs
    assert video.comments_from("not json") == [] and video.comments_from({}) == []


@check("hot_now: honest note, topic → one search; global → several broad terms merged and ranked")
def _():
    real = video.search_videos
    calls = []
    def fake(q, n=10, sort="relevance", period=None):
        calls.append((q, sort, period))
        return [{"id": f"{abs(hash(q)) % 10**11:011d}", "title": f"{q} video", "channel": "c", "views": len(q) * 1000, "published": "2 days ago", "length": "1:00", "seconds": 60, "url": "u"}]
    video.search_videos = fake
    try:
        vids, note = video.hot_now("dropshipping", 5)
        gvids, gnote = video.hot_now("", 3)
    finally:
        video.search_videos = real
    assert calls[0] == ("dropshipping", "views", "week") and "hidden from visitors" in note and "dropshipping" in note, (calls, note)
    assert len(gvids) == 3 and gvids[0]["views"] >= gvids[1]["views"] and len({c[0] for c in calls[2:]}) >= 4, (gvids, calls)


@check("Tasks.youtube_trending: list + top comment per video, document with the table when asked, no browser needed")
def _():
    real_hot, real_tc = video.hot_now, video.top_comments
    video.hot_now = lambda topic, n, period="week": ([{"id": "AAA111BBB22", "title": "Best Pasta", "channel": "Chef", "views": 5000, "published": "2 days ago", "length": "10:00", "seconds": 600, "url": "https://www.youtube.com/watch?v=AAA111BBB22"},
                                                      {"id": "CCC333DDD44", "title": "Ok Pasta", "channel": "Cook", "views": 100, "published": "1 day ago", "length": "3:00", "seconds": 180, "url": "https://www.youtube.com/watch?v=CCC333DDD44"}][:n], "note: trending is hidden")
    video.top_comments = lambda vid, n=5: ([{"author": "Luigi", "text": "Second here, great video.", "likes": 45, "replies": 0, "when": "1 day ago"}] if vid == "AAA111BBB22" else [], {})
    t = Tasks(log=lambda k, **f: None)
    try:
        out = t.youtube_trending(limit=2, topic="pasta", want_doc=True)
    finally:
        video.hot_now, video.top_comments = real_hot, real_tc
    assert "Hot on YouTube this week — pasta" in out and "1. Best Pasta" in out and "5,000 views" in out and "watch?v=AAA111BBB22" in out, out
    assert "💬 Luigi (45 ♥): Second here" in out and "note: trending is hidden" in out, out
    assert t.last_doc and os.path.exists(t.last_doc), t.last_doc
    html_ = open(t.last_doc, encoding="utf-8").read()
    assert "Best Pasta" in html_ and "Second here, great video." in html_ and "<table>" in html_ and "comments off" in html_, "doc misses the table / comment / honest empty"


@check("Tasks.video_comments reads the JSON (no browser) and names the video")
def _():
    real_tc = video.top_comments
    video.top_comments = lambda vid, n=5: ([{"author": "Mario", "text": "This changed my kitchen.", "likes": 1200, "replies": 2, "when": ""}], {"title": "Pasta & Love", "channel": "Chef"})
    try:
        out = Tasks(log=lambda k, **f: None).video_comments("https://youtu.be/AAA111BBB22")
    finally:
        video.top_comments = real_tc
    assert out.startswith("💬 Top comments — Pasta & Love") and "Mario (1,200 ♥)" in out, out


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
