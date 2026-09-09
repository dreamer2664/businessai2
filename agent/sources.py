"""Extra places to look when a research job has time left (owner: "more places to search when time is left, other
websites/engines, navigate sources better").

The main research loop reads the first engine's pages. When the pace says there is time (slow mode, an "at least N
hours" floor, or quiet-time budget) tasks.research() widens with these — each one cheap, each one optional, none of
them fatal when it fails:

  second_opinion   a DIFFERENT search engine for the same question (a different index → different sites)
  deep_links()     links inside a good page that lead to the facts pages (specs, shipping, prices, FAQ, wholesale…)
  wikipedia()      the encyclopedia summary — the neutral definition next to the shops' claims
  youtube()        the most-watched video on the topic + its transcript sentences (what people are told out loud)

Everything here is read-only, needs no key and no login. Failures return [] / None so the caller just moves on.
"""
import json
import re
import urllib.error
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept-Language": "en,it;q=0.8"}

# link labels / paths that usually lead from a shop or maker page to the page with the facts
DEEP = re.compile(r"(spec(ification|s|ifiche)?|tech(nical)?|data ?sheet|shipping|delivery|spedizion|consegn|returns?|res[oi]\b|"
                  r"pric(e|es|ing)|prezz|listino|tariff|wholesale|ingrosso|b2b|trade|bulk|moq|minimum order|faq|domande|"
                  r"reviews?|recension|opinion|catalog|catalogo|products?|prodott|collections?|about|chi siamo|azienda|"
                  r"how it works|come funziona|guide|guida|compare|confront|sizes?|misure|materials?|material[ei])", re.I)
SKIP = re.compile(r"(login|signin|sign-in|register|account|cart|checkout|basket|wishlist|privacy|cookie|terms|legal|"
                  r"javascript:|mailto:|tel:|#|\.(pdf|jpg|jpeg|png|gif|zip|mp4)$|facebook\.com|instagram\.com|twitter\.com|"
                  r"x\.com|linkedin\.com|pinterest\.|tiktok\.com|youtube\.com|whatsapp)", re.I)


def host(url):
    try:
        return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def deep_links(links, page_url, limit=3):
    """From a page's links ([{text, href}]), the few that look like they lead to facts on the SAME site.
    Ranked: shipping/prices/specs/wholesale first, then FAQ/reviews, then the rest. Returns [(label, url)]."""
    h = host(page_url)
    if not h:
        return []
    base = page_url.split("#")[0].rstrip("/")
    out, seen = [], set()
    for l in links or []:
        u = (l.get("href") or "").strip()
        label = re.sub(r"\s+", " ", (l.get("text") or "")).strip()
        if not u.startswith("http") or host(u) != h or SKIP.search(u) or SKIP.search(label) or len(label) > 40:
            continue                                  # long labels are company names / product titles, not menu entries
        u = u.split("#")[0].rstrip("/")
        if u == base or u in seen or len(u) > 200:
            continue
        m = DEEP.search(label) or DEEP.search(urllib.parse.urlparse(u).path)
        if not m or urllib.parse.urlparse(u).path in ("", "/"):
            continue                                  # the home page is not a facts page
        seen.add(u)
        hit = m.group(0).lower()
        rank = 0 if re.match(r"(spec|tech|data|shipping|delivery|spedizion|consegn|pric|prezz|listino|tariff|wholesale|ingrosso|b2b|trade|bulk|moq|minimum)", hit) else \
            1 if re.match(r"(faq|domande|review|recension|opinion|return|res|compare|confront)", hit) else 2
        out.append((rank, label or hit, u))
    out.sort(key=lambda x: (x[0], len(x[2])))
    return [(lbl, u) for _, lbl, u in out[:limit]]


def related(title, topic):
    """Does the article title really belong to the topic? A title word must match a topic word (either a prefix of the
    other, ≥ 4 letters), or the title glued together must sit inside the topic glued together ("Drop shipping" ↔ "dropshipping")."""
    tw = [w for w in re.findall(r"[a-zà-ÿ0-9]+", title.lower()) if len(w) >= 4]
    ow = [w for w in re.findall(r"[a-zà-ÿ0-9]+", topic.lower()) if len(w) >= 4]
    if any((a.startswith(b) or b.startswith(a)) and min(len(a), len(b)) >= 0.6 * max(len(a), len(b)) for a in tw for b in ow):
        return True                                   # lamp/lamps yes; case/casetify no
    glued_t = re.sub(r"[^a-zà-ÿ0-9]", "", title.lower())
    glued_o = re.sub(r"[^a-zà-ÿ0-9]", "", topic.lower())
    if glued_t and len(glued_t) >= 5 and glued_t in glued_o:
        return True
    initials = "".join(w[0] for w in re.findall(r"[a-zà-ÿ0-9]+", title.lower()) if w not in ("of", "the", "and", "for", "in", "a"))
    acronyms = [w.lower() for w in re.findall(r"\b[A-Z][A-Z0-9]{2,}\b", topic)] + \
        [w for w in re.findall(r"[a-z0-9]+", topic.lower()) if 3 <= len(w) <= 4]                   # capitals, or short words (ioss, oss, moq) — not lamps ↔ LAMPS
    return len(initials) >= 3 and initials in acronyms                                             # IOSS ↔ Import One-Stop Shop


QUALIFIERS = re.compile(r"\b(suppliers?|wholesalers?|wholesale|manufacturers?|makers?|vendors?|europe|european|eu|italy|italia|italian|germany|uk|usa|china|"
                        r"best|top|cheap(est)?|good|price|prices|pricing|cost|review|reviews|guide|tips|explained|examples|vs|versus|compare|comparison|"
                        r"buy|order|online|near me|2024|2025|2026|fornitor[ei]|grossist[ai]|ingrosso|miglior[ei]|economic[oiahe]|prezz[oi]|recensioni|guida|confronto|come|fare)\b", re.I)


def _wiki_queries(topic, limit=3):
    """The topic as asked, then stripped of shop words, then its first three words — distinct, longest first, ≤ limit."""
    out = []
    for q in (topic, QUALIFIERS.sub(" ", topic), " ".join(topic.split()[:3])):
        q = re.sub(r"\s+", " ", re.sub(r"[^\w\s-]", " ", q)).strip(" -")
        if len(q) >= 3 and q.lower() not in [x.lower() for x in out]:
            out.append(q)
    return out[:limit]


def _get_json(url, timeout=8):
    req = urllib.request.Request(url, headers={"User-Agent": "BusinessAI-shop-assistant/1.0 (https://github.com/dreamer2664/businessai; one-owner research helper, low volume)", "Accept": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "replace"))


def wikipedia(topic, lang="en", timeout=8):
    """{"title", "url", "text"} for the closest article, or None. Small API calls, no key.
    For the topic as asked, then without shop words ("… suppliers europe"), then its first words: full-text search (5 candidates)
    → keep the titles that really belong to the topic (`related`, no stray words) → the one sharing most words → its summary."""
    t = re.sub(r"\s+", " ", topic).strip()
    if not t:
        return None
    try:
        for q in _wiki_queries(t):
            d = _get_json(f"https://{lang}.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(q)}&srlimit=5&format=json", timeout)
            cands = [x.get("title", "") for x in (d.get("query") or {}).get("search", [])]
            ranked = _rank_titles(cands, q)
            for best in ranked[:2]:                               # the first may be a disambiguation page ("IOSS can refer to…")
                s = _get_json(f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(best.replace(' ', '_'))}", timeout)
                text = (s.get("extract") or "").strip()
                if s.get("type") == "disambiguation" or len(text) < 80:
                    continue
                return {"title": f"Wikipedia: {s.get('title') or best}", "url": (s.get("content_urls") or {}).get("desktop", {}).get("page") or f"https://{lang}.wikipedia.org/wiki/{urllib.parse.quote(best.replace(' ', '_'))}", "text": text}
        return None
    except Exception:
        return None


def _rank_titles(cands, topic):
    """Candidate article titles that belong to the topic, best first: most topic words, fewest stray words, shortest."""
    ow = set(w for w in re.findall(r"[a-zà-ÿ0-9]+", topic.lower()) if len(w) >= 4)
    glued_topic = re.sub(r"[^a-zà-ÿ0-9]", "", topic.lower())

    def score(c):
        cw = re.findall(r"[a-zà-ÿ0-9]+", c.lower())
        hit = sum(1 for w in cw if any((w.startswith(o) or o.startswith(w)) and min(len(w), len(o)) >= 0.6 * max(len(w), len(o)) for o in ow))
        stray = len(cw) - hit
        if hit == 0 or "".join(cw) in glued_topic:
            hit, stray = len(cw), 0                                # matched by initials (IOSS) or glued words (Drop shipping ↔ dropshipping)
        return None if (stray > 0 and hit < 2) else (hit, -stray, -len(c))     # "Neon lamp" for "cheap lamps" is a stray article, not the topic
    good = [c for c in cands if c and related(c, topic) and not re.search(r"\((city|town|criminal|film|album|band|song|surname|name)\)", c, re.I)]
    return sorted((c for c in good if score(c)), key=score, reverse=True)


def youtube(topic, with_transcript=True):
    """The most-watched recent video on the topic: {"title", "url", "text", "views", "channel"} or None.
    text = transcript when one exists (auto captions count), else the title + channel line."""
    try:
        from . import video
        vids = video.search_videos(topic, n=5, sort="views", period="year")
        if not vids or max(v.get("views", 0) for v in vids) < 1000:      # a tiny niche this year → the all-time popular one
            vids = (vids or []) + (video.search_videos(topic, n=5, sort="views") or [])
    except Exception:
        return None
    vids = [v for v in vids if v.get("seconds", 0) == 0 or 60 <= v.get("seconds", 0) <= 40 * 60] or vids
    if not vids:
        return None
    v = max(vids, key=lambda x: x.get("views", 0))
    text = ""
    if with_transcript:
        try:
            text, _meta = video.transcript(v["id"])
        except Exception:
            text = ""
    return {"title": f"YouTube: {v.get('title', '')[:70]} ({v.get('channel', '')} · {views_text(v.get('views', 0))} views)",
            "url": v.get("url") or f"https://www.youtube.com/watch?v={v['id']}", "text": text, "views": v.get("views", 0), "channel": v.get("channel", "")}


def views_text(n):
    """120000 → '120.000' (the owner reads Italian-style thousands)."""
    return f"{int(n or 0):,}".replace(",", ".")


def transcript_sentences(text, topic, limit=3):
    """Transcripts have no punctuation → cut into ~25-word chunks, keep the ones with topic words and a number/definition cue."""
    if not text:
        return []
    words = text.split()
    tw = set(w[:6] for w in re.findall(r"[a-z0-9]+", topic.lower()) if len(w) > 2)
    out = []
    for i in range(0, len(words), 22):
        chunk = " ".join(words[i:i + 25]).strip()
        if len(chunk) < 60:
            continue
        sw = set(w[:6] for w in re.findall(r"[a-z0-9]+", chunk.lower()))
        if len(tw & sw) >= max(1, len(tw) // 2) and re.search(r"\b(\d+|percent|is|are|means|costs?|price|cheap|expensive|best|worst|never|always)\b", chunk, re.I):
            out.append(chunk[0].upper() + chunk[1:] + ("" if chunk.endswith((".", "!", "?")) else " …"))
        if len(out) >= limit:
            break
    return out
