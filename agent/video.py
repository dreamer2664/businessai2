"""'Watching' videos the frugal way: read their captions.

YouTube publishes captions (human or auto-generated) for most videos. We fetch the caption text through
YouTube's own public player endpoint — no API key, no login, no video download — and hand the transcript
to the thinking model for a summary. A 20-minute talk is ~120 KB of XML → ~20 KB of text.

    search(query, n)      -> [{"id", "title"}]
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
    u = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
    page = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=20).read().decode("utf-8", "replace")
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
    """Top videos for a topic ranked by views. Pure search-page scraping: works anywhere."""
    u = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
    page = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=20).read().decode("utf-8", "replace")
    out, seen = [], set()
    for m in re.finditer(r'"videoRenderer":\{"videoId":"([A-Za-z0-9_-]{11})"', page):
        vid = m.group(1)
        if vid in seen:
            continue
        seen.add(vid)
        blob = page[m.start():m.start() + 6000]       # metadata sits after the byline
        t = re.search(r'"title":\{"runs":\[\{"text":"(.*?)"\}', blob)
        try:
            title = json.loads(f'"{t.group(1)}"') if t else vid
        except Exception:
            title = t.group(1) if t else vid
        vm = re.search(r'"viewCountText":\{"simpleText":"([^"]+)"\}', blob)
        out.append({"id": vid, "title": title, "views": parse_views(vm.group(1)) if vm else 0})
    out.sort(key=lambda v: -v["views"])
    return out[:n]
