"""'Watching' videos the frugal way: read their captions.

YouTube publishes captions (human or auto-generated) for most videos. We fetch the caption text through
YouTube's own public player endpoint — no API key, no login, no video download — and hand the transcript
to the thinking model for a summary. A 20-minute talk is ~120 KB of XML → ~20 KB of text.

    search(query, n)      -> [{"id", "title"}]
    search_videos(q, n, sort, period) -> full cards from ytInitialData (id, title, channel, views, published, length)
    hot_now(topic, n)     -> (videos, note): most-watched uploads of the week — the honest stand-in for the hidden trending feed
    top_comments(id, n)   -> (comments, meta) without a browser: the comments JSON the watch page itself loads
    top_for_topic(q, n)   -> [{"id", "title", "views"}] ranked by views (works anywhere: search page)
    extract_trending(page)-> [{"id", "title", "channel", "views"}] from a rendered /feed/trending page (PC browser)
    extract_comments(page)-> [{"author", "text", "likes"}] from a rendered watch page (PC browser), most-liked first
    transcript(video_id)  -> (plain text or "", meta{title, channel, seconds, language, auto})
    url_id(url_or_id)     -> 11-char video id or None
"""
import html
import json
import re
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9"}
_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def url_id(s):
    s = s.strip()
    if _ID.match(s):
        return s
    m = re.search(r"(?:v=|youtu\.be/|/shorts/|/embed/)([A-Za-z0-9_-]{11})", s)
    return m.group(1) if m else None


def search(query, n=8):
    """[{"id","title"}] for a query (ytInitialData reader; the old regex is the fallback)."""
    u = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
    page = _get(u, timeout=20)
    vids = videos_from(page, limit=n)
    if vids:
        return [{"id": v["id"], "title": v["title"], "url": v["url"], "views": v["views"], "channel": v["channel"]} for v in vids]
    out, seen = [], set()
    for m in re.finditer(r'"videoRenderer":\{"videoId":"([A-Za-z0-9_-]{11})"(.*?)"longBylineText"', page):
        vid, blob = m.group(1), m.group(2)
        if vid in seen:
            continue
        seen.add(vid)
        t = re.search(r'"title":\{"runs":\[\{"text":"(.*?)"\}', blob)
        try:
            title = json.loads(f'"{t.group(1)}"') if t else vid
        except Exception:
            title = t.group(1) if t else vid
        out.append({"id": vid, "title": title})
        if len(out) >= n:
            break
    return out


# ---- the modern reader: ytInitialData (what the page itself renders from) ----------------------------------
# The search page embeds `var ytInitialData = {...};` — a JSON tree with one "videoRenderer" per result. Reading it is
# far more robust than regexes over the 1.5 MB page. Filters ("sp") are YouTube's own: sort by view count, upload period.
_SP = {("relevance", None): "", ("views", None): "CAM%3D", ("date", None): "CAI%3D",
       ("views", "hour"): "CAMSAggB", ("views", "today"): "CAMSAggC", ("views", "week"): "CAMSAggD", ("views", "month"): "CAMSAggE", ("views", "year"): "CAMSAggF",
       ("relevance", "hour"): "EgIIAQ%3D%3D", ("relevance", "today"): "EgIIAg%3D%3D", ("relevance", "week"): "EgIIAw%3D%3D", ("relevance", "month"): "EgIIBA%3D%3D", ("relevance", "year"): "EgIIBQ%3D%3D"}


def _get(url, timeout=25):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read().decode("utf-8", "replace")


def initial_data(page):
    """The ytInitialData JSON object embedded in a YouTube page (search, watch, feed), or {}."""
    m = re.search(r"var ytInitialData\s*=\s*(\{.*?\});\s*</script>", page, re.S) or re.search(r'window\["ytInitialData"\]\s*=\s*(\{.*?\});\s*</script>', page, re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except Exception:
        return {}


def _text(x):
    """A YouTube text object ({"simpleText"} or {"runs": [...]}) → str."""
    if not isinstance(x, dict):
        return ""
    if x.get("simpleText"):
        return str(x["simpleText"])
    return "".join(str(r.get("text", "")) for r in x.get("runs", []) if isinstance(r, dict))


def _renderers(o, key):
    if isinstance(o, dict):
        if key in o and isinstance(o[key], dict):
            yield o[key]
        for v in o.values():
            yield from _renderers(v, key)
    elif isinstance(o, list):
        for v in o:
            yield from _renderers(v, key)


def _seconds(length_text):
    parts = [p for p in re.split(r"[:.]", length_text or "") if p.strip().isdigit()]
    if not parts:
        return 0
    s = 0
    for p in parts:
        s = s * 60 + int(p)
    return s


def videos_from(page_or_data, limit=20):
    """Video cards from a search page (html or its ytInitialData): id, title, channel, views, published, length, seconds, url."""
    d = initial_data(page_or_data) if isinstance(page_or_data, str) else (page_or_data or {})
    out, seen = [], set()
    for v in _renderers(d, "videoRenderer"):
        vid = v.get("videoId")
        if not vid or not _ID.match(str(vid)) or vid in seen:
            continue
        title = _text(v.get("title"))
        if not title:
            continue
        seen.add(vid)
        length = _text(v.get("lengthText"))
        out.append({"id": vid, "title": title[:160], "channel": _text(v.get("ownerText")) or _text(v.get("longBylineText")),
                    "views": parse_views(_text(v.get("viewCountText")) or _text(v.get("shortViewCountText"))),
                    "published": _text(v.get("publishedTimeText")), "length": length, "seconds": _seconds(length),
                    "url": f"https://www.youtube.com/watch?v={vid}"})
        if len(out) >= limit:
            break
    return out


def search_videos(query, n=10, sort="relevance", period=None):
    """Search YouTube like a visitor. sort: relevance | views | date; period: hour | today | week | month | year | None.
    Returns [{"id","title","channel","views","published","length","seconds","url"}]. Raises on network trouble."""
    sp = _SP.get((sort, period))
    if sp is None:
        sp = _SP.get(("relevance", period), "")
    u = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query) + ("&sp=" + sp if sp else "")
    page = _get(u)
    vids = videos_from(page, limit=max(n * 2, 10))
    if sort == "views":
        vids.sort(key=lambda v: -v["views"])
    elif sort == "date":
        vids.sort(key=lambda v: _age_minutes(v["published"]))
    return vids[:n]


_AGE = {"second": 1 / 60, "minute": 1, "hour": 60, "day": 1440, "week": 10080, "month": 43200, "year": 525600}


def _age_minutes(published):
    m = re.search(r"(\d+)\s*(second|minute|hour|day|week|month|year)", published or "")
    if not m:
        m2 = re.search(r"(\d+)\s*([smhdwy])\b", published or "")            # "3w ago" (compact form)
        if not m2:
            return 10 ** 9
        return int(m2.group(1)) * {"s": 1 / 60, "m": 1, "h": 60, "d": 1440, "w": 10080, "y": 525600}[m2.group(2)]
    return int(m.group(1)) * _AGE[m.group(2)]


def hot_now(query, n=5, period="week"):
    """'Trending' the honest way: YouTube hides /feed/trending from visitors, so this is the most-watched videos
    uploaded in the last `period` for the topic (or for broad terms when no topic). Returns (videos, note)."""
    q = query.strip() if query and query.strip().lower() not in ("", "global", "youtube", "all") else ""
    note = ("YouTube's own trending page is hidden from visitors (it redirects to the home page), so this is the closest "
            f"public view: the most-watched videos uploaded this {period}" + (f" about “{q}”" if q else "") + ".")
    if q:
        vids = search_videos(q, n=n, sort="views", period=period)
        if len(vids) < n and period in ("today", "week"):
            more = search_videos(q, n=n, sort="views", period="month")
            ids = {v["id"] for v in vids}
            vids += [v for v in more if v["id"] not in ids][: n - len(vids)]
    else:
        vids, ids = [], set()
        for term in ("trending", "viral", "news", "official trailer", "music video"):
            for v in search_videos(term, n=n, sort="views", period=period):
                if v["id"] not in ids:
                    ids.add(v["id"]); vids.append(v)
        vids.sort(key=lambda v: -v["views"])
        vids = vids[:n]
    return vids, note


def _client_version(page):
    m = re.search(r'"INNERTUBE_CLIENT_VERSION":"([^"]+)"', page)
    return m.group(1) if m else "2.20250101.00.00"


def comment_token(page_or_data):
    """The continuation token that loads the comments of a watch page (the browser asks for the same one)."""
    d = initial_data(page_or_data) if isinstance(page_or_data, str) else (page_or_data or {})
    for isr in _renderers(d, "itemSectionRenderer"):
        if isr.get("sectionIdentifier") == "comment-item-section":
            for c in isr.get("contents", []):
                t = (c.get("continuationItemRenderer", {}).get("continuationEndpoint", {}).get("continuationCommand", {}).get("token"))
                if t:
                    return t
    return None


def comments_from(next_json, limit=10):
    """Comments from a /youtubei/v1/next response (commentEntityPayload mutations), most-liked first."""
    if isinstance(next_json, str):
        try:
            next_json = json.loads(next_json)
        except Exception:
            return []
    out = []
    for m in (next_json.get("frameworkUpdates", {}).get("entityBatchUpdate", {}).get("mutations", []) or []):
        c = (m.get("payload") or {}).get("commentEntityPayload")
        if not c:
            continue
        text = ((c.get("properties") or {}).get("content") or {}).get("content") or ""
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        tb = c.get("toolbar") or {}
        out.append({"author": (c.get("author") or {}).get("displayName") or "?", "text": text[:500],
                    "likes": parse_views(tb.get("likeCountNotliked") or tb.get("likeCountLiked") or "0"),
                    "replies": parse_views(tb.get("replyCount") or "0"), "when": (c.get("properties") or {}).get("publishedTime") or ""})
    out.sort(key=lambda c: -c["likes"])
    return out[:limit]


def top_comments(video_id, n=5):
    """Top comments of a video without a browser: watch page → comments token → the same JSON the page loads.
    Returns (comments, meta{title, channel}); comments == [] when they are off or the layout changed."""
    page = _get(f"https://www.youtube.com/watch?v={video_id}&hl=en")
    d = initial_data(page)
    meta = {"title": "", "channel": ""}
    for vp in _renderers(d, "videoPrimaryInfoRenderer"):
        meta["title"] = _text(vp.get("title")); break
    for vo in _renderers(d, "videoOwnerRenderer"):
        meta["channel"] = _text(vo.get("title")); break
    tok = comment_token(d)
    if not tok:
        return [], meta
    body = json.dumps({"context": {"client": {"clientName": "WEB", "clientVersion": _client_version(page), "hl": "en", "gl": "US"}},
                       "continuation": tok}).encode()
    req = urllib.request.Request("https://www.youtube.com/youtubei/v1/next?prettyPrint=false", data=body,
                                 headers={"Content-Type": "application/json", "User-Agent": UA["User-Agent"]})
    raw = urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "replace")
    return comments_from(raw, n), meta


def _tracks(video_id):
    """Caption tracks via the Android player client (the web client often returns empty caption files)."""
    body = json.dumps({"context": {"client": {"clientName": "ANDROID", "clientVersion": "20.10.38", "androidSdkVersion": 30, "hl": "en"}},
                       "videoId": video_id}).encode()
    req = urllib.request.Request("https://www.youtube.com/youtubei/v1/player?prettyPrint=false", data=body,
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "com.google.android.youtube/20.10.38 (Linux; U; Android 11) gzip"})
    d = json.loads(urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "replace"))
    vd = d.get("videoDetails", {})
    tracks = d.get("captions", {}).get("playerCaptionsTracklistRenderer", {}).get("captionTracks", [])
    return tracks, {"title": vd.get("title", ""), "channel": vd.get("author", ""), "seconds": int(vd.get("lengthSeconds", 0) or 0)}


def _fetch_caption(url):
    """Caption XML with 429 backoff (YouTube throttles caption fetches per IP)."""
    import time
    last = None
    for wait in (0, 6, 25):
        if wait:
            time.sleep(wait)
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            last = e
            if e.code != 429:
                raise
    raise last


def transcript(video_id, prefer=("en", "en-US", "en-GB")):
    tracks, meta = _tracks(video_id)
    if not tracks:
        return "", meta
    ordered = [t for p in prefer for t in tracks if t.get("languageCode") == p and t.get("kind") != "asr"] + \
        [t for p in prefer for t in tracks if t.get("languageCode") == p] + tracks
    seen_urls, deduped = set(), []
    for t in ordered:
        if t.get("baseUrl") not in seen_urls:
            seen_urls.add(t.get("baseUrl"))
            deduped.append(t)
    ordered = deduped[:4]
    xml, track, err = None, ordered[0], None
    for track in ordered:                                    # a throttled track falls through to the next
        try:
            xml = _fetch_caption(track["baseUrl"])
            break
        except urllib.error.HTTPError as e:
            err = e
            continue
    if xml is None:
        raise err
    parts = []
    for p in re.findall(r"<p[^>]*>(.*?)</p>", xml, re.S):
        txt = html.unescape(re.sub(r"<[^>]+>", "", p)).replace("\n", " ").strip()
        if txt:
            parts.append(txt)
    text = re.sub(r"\s+", " ", " ".join(parts)).strip()
    meta["language"] = track.get("languageCode")
    meta["auto"] = track.get("kind") == "asr"
    return text, meta


# ---- trending + comments (item 4): browser-first, no API key ------------------------------

def parse_views(s):
    """'1.2M views' / '45K' / '3,456' / '12 watching' -> int. Anything odd -> 0."""
    if not s:
        return 0
    m = re.search(r"([\d.,]+)\s*([KMB])?\b", str(s).replace(",", ""))
    if not m:
        return 0
    try:
        v = float(m.group(1))
    except ValueError:
        return 0
    return int(v * {"K": 1e3, "M": 1e6, "B": 1e9}.get(m.group(2) or "", 1))


def extract_trending(page, limit=10):
    """Entries from a rendered /feed/trending page. DOM first, embedded JSON as fallback."""
    out, seen = [], set()

    def add(vid, title, blob):
        if not vid or vid in seen or not title:
            return
        seen.add(vid)
        title = html.unescape(re.sub(r"\s+", " ", title)).strip()
        vm = re.search(r"([\d.,]+\s*[KMB]?)\s+views?\b", blob)
        cm = re.search(r'href="/@[^"]*"[^>]*>([^<]{2,60})<', blob)
        out.append({"id": vid, "title": title[:120],
                    "channel": html.unescape(cm.group(1)).strip() if cm else "",
                    "views": parse_views(vm.group(1)) if vm else 0})

    for m in re.finditer(r'href="/watch\?v=([A-Za-z0-9_-]{11})"[^>]{0,400}?title="([^"]{3,160})"', page):
        add(m.group(1), m.group(2), page[m.end():m.end() + 800])
        if len(out) >= limit:
            return out
    if len(out) < 3:                                        # embedded JSON fallback (same shape as search)
        for m in re.finditer(r'"videoRenderer":\{"videoId":"([A-Za-z0-9_-]{11})"', page):
            blob = page[m.start():m.start() + 6000]       # metadata sits after the byline
            t = re.search(r'"title":\{"runs":\[\{"text":"(.*?)"\}', blob)
            title = t.group(1) if t else ""
            try:
                title = json.loads(f'"{title}"')
            except Exception:
                pass
            if m.group(1) not in seen and title:
                seen.add(m.group(1))
                vm = re.search(r'"viewCountText":\{"simpleText":"([^"]+)"\}', blob)
                out.append({"id": m.group(1), "title": title[:120], "channel": "",
                            "views": parse_views(vm.group(1)) if vm else 0})
            if len(out) >= limit:
                break
    return out


def extract_comments(page, limit=10):
    """Top comments from a rendered watch page (most-liked first)."""
    out = []
    for m in re.finditer(r"<ytd-comment-thread-renderer\b.*?</ytd-comment-thread-renderer>", page, re.S):
        b = m.group(0)
        am = re.search(r'id="author-text"[^>]*>.*?>([^<]{1,60})<', b, re.S)
        tm = re.search(r'id="content-text"[^>]*>(.*?)</[a-z-]+content-text>', b, re.S) or \
            re.search(r'id="content-text"[^>]*>(.*?)</span>', b, re.S)
        lm = re.search(r'id="vote-count-middle"[^>]*>([^<]*)<', b)
        text = html.unescape(re.sub(r"<[^>]+>", "", tm.group(1))).replace("\n", " ").strip() if tm else ""
        text = re.sub(r"\s+", " ", text)
        if not text:
            continue
        out.append({"author": html.unescape(am.group(1)).strip() if am else "?",
                    "text": text[:500], "likes": parse_views(lm.group(1)) if lm else 0})
    out.sort(key=lambda c: -c["likes"])
    return out[:limit]


def top_for_topic(query, n=5):
    """Top videos for a topic ranked by views. Search-page reader: works anywhere."""
    vids = search_videos(query, n=n, sort="views")
    return [{"id": v["id"], "title": v["title"], "views": v["views"], "channel": v["channel"], "published": v["published"]} for v in vids]
