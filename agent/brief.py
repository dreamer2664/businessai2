"""Understanding a request before doing it (milestone 13).

The owner writes in plain words. Before any work starts, the agent turns the message into a *brief*:
  goal        — what the owner wants, in one line
  pace        — how fast: "quick" (a few minutes), "normal", "slow" (use the time), plus an explicit deadline / budget
                ("in 10 minutes" → 10 min deadline; "I'm away 5 hours, take it slow" → 5 h budget)
  deliverable — what to hand back: an answer, a list, a document (with pictures/links), a file, a website …
  steps       — the to-do list the agent will follow (shown to the owner first, editable)
  kind        — which tool family does the work (research / seller_check / compare / visit / watch / trending / build_site / chat / ask)

Pace words are parsed by rules (they must be reliable even without the thinking model); the goal, deliverable and steps
come from the thinking model when it is available, otherwise from rules. A brief is a dict; `text()` renders it for
Telegram. Deadlines are *reminders*, never a stop: the operator keeps the clock in front of it and reports when late.
"""
import json
import re
import urllib.parse
import time

PACE_PROMPT = """You turn the owner's message into a short work plan for a business assistant. Reply with one JSON object only:
{"goal": one line, what the owner wants;
 "deliverable": one of "answer" | "list" | "document" | "file" | "website" | "post" | "reply";
 "kind": one of "research" | "seller_check" | "compare" | "summarize" | "visit" | "watch" | "build_site" | "post" | "ask" | "chat";
 "steps": [3 to 7 short steps, each starting with a verb, concrete: which sites, what to check, what to write],
 "questions": [0 to 2 questions ONLY if something essential is missing (budget, country, size); else []]}
Rules: "reps"/"replicas"/"fakes" of brands are counterfeit — plan the research on the genuine or unbranded product instead
and say so in the goal. "seller_check" is for judging sellers/shops/listings (reviews, social pages, complaints, shipping,
origin, materials). "document" when the owner wants links, pictures or a walk-through. Never add a step that spends money,
logs in or posts publicly. Owner's message: """

# pace words → (pace, minutes)
# "subito" is Italian for "right away" AND the name of a marketplace: only the adverb counts (never subito.it / on subito / subito, vinted)
_QUICK = r"\b(real quick|quick(ly)?|asap|right away|fast|hurry|in a hurry|(?<![\w.])subito(?!\.it|\.com|\s*(?:,|and|e|or|o|/)\s*(?:vinted|ebay|wallapop|amazon|etsy|facebook|depop|temu|shein)|\s+(?:e|and)\b)|veloce|rapido)\b"
_SITE_WORDS = r"\b(?:on|su|in|from|da|look in|search|cerca su)\s+subito\b|\bsubito\.(?:it|com)\b|\bsubito\s*(?:,|and|e|or|o|/)\s*(?:vinted|ebay|wallapop|amazon|etsy|facebook|depop|temu|shein)\b|\b(?:vinted|ebay|wallapop|amazon|etsy|facebook marketplace|depop)\s*(?:,|and|e|or|o|/)\s*subito\b"
_RANGE = r"(\d+)\s*(?:-|–|—|to|a|or|/)\s*(\d+)\s*(min(?:ute)?s?|h(?:ou)?rs?|or[ae]|minuti)"
_SLOW = r"\b(take (it|your time) (real |really |very )?slow(ly)?|take it easy|take your time|slow down|slower|not (so|that|too) fast|no rush|no hurry|slowly|whenever|con calma|piano|rallenta|più lento|non correre)\b"
_DEADLINE = r"\b(?:in|within|entro|tra|fra)\s+(?:(mezz[’']?ora)|(\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|thirty|forty|fifty|half an|half|un[’']?|una|due|tre|quattro|cinque|sei|sette|otto|nove|dieci|undici|dodici)\s*(min(?:ute)?s?|h(?:ou)?rs?|or[ae]|minuti|day|days|giorni))\b"
_AWAY = r"\b(?:(?:i(?:'m| am| will be| ll be)|gonna be|going to (?:be|work)|at work|out|away|busy|sleeping|asleep|sono (?:fuori|via|al lavoro|occupat[oa])|torno|dormo)\D{0,40}?)(?:(mezz[’']?ora)|(\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|half an|half|un[’']?|una|due|tre|quattro|cinque|sei|sette|otto|nove|dieci|undici|dodici)\s*(h(?:ou)?rs?|or[ae]|min(?:ute)?s?|minuti))\b"
_FLOOR = r"\b(?:at least|atleast|minimum(?: of)?|min(?:imum)?\.?|no less than|not less than|spend(?: at least)?|take(?: at least)?(?: (?:around|about|roughly|some|approximately|circa|~))?|use(?: around| about)?|(?:you have|you've got|you get)(?: around| about)?|almeno|minimo|non meno di|prenditi(?: circa)?|usa(?: circa)?)\s+(?:(mezz[’']?ora)|(\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|thirty|forty|fifty|half an|half|un[’']?|una|due|tre|quattro|cinque|sei|sette|otto|nove|dieci|undici|dodici)\s*(min(?:ute)?s?|h(?:ou)?rs?|or[ae]|minuti))\b"
_CEILING = r"\b(?:at most|no more than|not more than|max(?:imum)?(?: of)?\.?|up to|al massimo|massimo|non più di|non piu di)\s+(?:(mezz[’']?ora)|(\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|thirty|forty|fifty|half an|half|un[’']?|una|due|tre|quattro|cinque|sei|sette|otto|nove|dieci|undici|dodici)\s*(min(?:ute)?s?|h(?:ou)?rs?|or[ae]|minuti))\b"
_NUM = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
        "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
        "half an": 0.5, "half": 0.5, "un": 1, "una": 1, "due": 2, "tre": 3, "quattro": 4, "cinque": 5, "sei": 6,
        "sette": 7, "otto": 8, "nove": 9, "dieci": 10, "undici": 11, "dodici": 12}


def _minutes(n, unit):
    n = str(n).replace("’", "'").strip().rstrip("'")
    if "mezz" in n:
        return 30
    n = _NUM.get(n, None) if not n.isdigit() else int(n)
    if n is None:
        return None
    u = (unit or "min").lower()
    if u.startswith(("h", "ore", "ora")):
        return int(n * 60)
    if u.startswith(("day", "giorn")):
        return int(n * 60 * 24)
    return int(n)


_PACE_CLAUSES = [_QUICK, _SLOW, _DEADLINE, _AWAY, _FLOOR, _CEILING,
                 r"\b(make it quick|i need it|i want it|i'?m (going to|gonna) (work|be out|be away|sleep)[^,.:;]*|take it (real |really )?slow|no rush)\b",
                 r"\b(for|in) (the next )?(\d+|a|an|one|two|three|four|five|six|eight|ten) ?(h(?:ou)?rs?|min(?:ute)?s?)\b"]
_LEAD = r"^(?:(?:hey|hi|hello|ciao|ok|okay|so|please|per favore|also|and|then|now|real quick|quick(?:ly)?|can you|could you|would you|will you|i want you to|i need you to|i'?d like you to|i want|i need|i'?d like|find me|find|get me|look for|search for|search|show me|tell me|give me|make me|compare|write me|trovami|cercami|trova|cerca)[ ,:]+)+"


def topic_of(text):
    """The thing the request is about, without pace words, politeness and filler: 'hey, real quick find me some good
    cheap reps for nike slippers, i'm out for 3 hours' → 'reps for nike slippers'."""
    urls = re.findall(r"https?://\S+|\b[a-z0-9.-]+\.(?:com|it|de|fr|es|net|org|co|io|be|tv|me)(?:/\S*)?", text, re.I)
    text = re.sub(r"\s*\([^()]{8,160}\)", "", text)                        # bracketed conditions are kept separately
    _site = r"(?:vinted|subito|ebay|amazon|etsy|wallapop|depop|aliexpress|temu|facebook marketplace|zalando|kleinanzeigen|leboncoin)(?:\.(?:it|com|de|fr|es|co\.uk))?"
    text = re.sub(r"\s+\b(?:on|su|from|da)\s+" + _site + r"(?:\s*(?:,|and|e|or|o)\s*" + _site + r")*\b", " ", text, flags=re.I)
    text = re.sub(r"\b(and )?(report|get) back to me\b.*$|\band (write|make|send|hand) me\b.*$|\bi want (links|images|pictures|photos)\b.*$", "", text, flags=re.I)
    low = " " + text.lower().strip() + " "
    for i, u in enumerate(urls):                                          # protect links from the punctuation split
        low = low.replace(u.lower(), f" URL{i} ")
    for pat in _PACE_CLAUSES:
        low = re.sub(pat, " ", low)
    low = re.sub(r"[.!?;:]+", ",", low)
    parts = [p.strip(" ,") for p in low.split(",") if p.strip(" ,")]
    parts = [p for p in parts if not re.fullmatch(r"(thanks?( you)?|please|asap|now|ok|okay|good luck|and|so)", p)]
    best = ""
    for p in parts:
        q = re.sub(_LEAD, "", p + " ").strip()
        q = re.sub(r"^(look up|look for|search for|search|find|cerca|trova|trovami|cercami)\s+(me\s+)?(the\s+)?", "", q)
        q = re.sub(r"\s+(on|su)\s+(vinted|subito(?:\.it)?|ebay(?:\.it)?|amazon(?:\.it)?|etsy|wallapop|depop|aliexpress|temu|facebook marketplace|zalando|kleinanzeigen|leboncoin)(\s*(,|and|e|or|o)\s*(vinted|subito(?:\.it)?|ebay(?:\.it)?|amazon(?:\.it)?|etsy|wallapop|depop|aliexpress|temu|facebook marketplace|zalando|kleinanzeigen|leboncoin))*\b", " ", q)
        q = re.sub(r"\b(some|a few|a couple of|good|cheap|reliable|trustworthy|best|nice|great|decent|quality|really|very|please|me|us)\b", " ", q)
        q = re.sub(r"\b(i'?m|i am|i will|i'?ll)\b.*$", "", q)
        q = re.sub(r"\s{2,}", " ", q).strip(" ,.-—")
        if len(q) > len(best):
            best = q
    for i, u in enumerate(urls):
        best = re.sub(f"url{i}", u, best, flags=re.I)
    return best or text.strip()


def _dur(m):
    """Minutes from a _DEADLINE/_AWAY match (group 1 = bare mezz'ora, else group 2 + 3)."""
    return 30 if m.group(1) else _minutes(m.group(2), m.group(3))


def parse_duration(text):
    """First explicit duration in text → minutes (English + Italian), or None."""
    low = " " + text.lower() + " "
    m = re.search(_DEADLINE, low)
    if m:
        mins = _dur(m)
        if mins:
            return mins
    m = re.search(r"\b(mezz[’']?ora|un[’']ora)\b", low)
    if m:
        return 30 if m.group(1).startswith("mezz") else 60
    m = re.search(r"\b(\d+)\s*(min(?:ute)?s?|h(?:ou)?rs?|or[ae]|minuti)\b", low)
    if m:
        return _minutes(m.group(1), m.group(2))
    return None


def _strip_sites(low):
    """Site names out of the way of the pace words ('look in subito.it' is a place, not 'right away')."""
    return re.sub(_SITE_WORDS, " SITE ", low)


def parse_pace(text):
    """Rules only. Returns {"pace": quick|normal|slow, "deadline_min": int|None, "budget_min": int|None, "why": str}."""
    low = _strip_sites(" " + text.lower() + " ")
    out = {"pace": "normal", "deadline_min": None, "budget_min": None, "floor_min": None, "why": ""}
    mr = re.search(r"\b(?:take|spend|use|around|about|roughly|circa|prenditi|for|in)\s+(?:around |about |roughly |circa |some )?" + _RANGE + r"\b", low)
    if mr:                                                              # "take around 5-6 hours": the low end is the floor, the high end the budget
        lo, hi = _minutes(mr.group(1), mr.group(3)), _minutes(mr.group(2), mr.group(3))
        if lo and hi and hi >= lo and lo >= 5:
            out.update(pace="slow", floor_min=lo, budget_min=hi, why=f"you said {_span(lo)} to {_span(hi)} — I use at least {_span(lo)} and stop by {_span(hi)}")
    m = re.search(_FLOOR, low)
    if m and not out["floor_min"]:
        mins = _dur(m)
        if mins and mins >= 5:
            out.update(pace="slow", floor_min=mins, why=f"you asked for at least {_span(mins)} — a floor, not a deadline")
    m = re.search(_CEILING, low)
    if m:
        mins = _dur(m)
        if mins and mins != out["floor_min"]:
            out.update(deadline_min=mins, why=(out["why"] + "; " if out["why"] else "") + f"at most {_span(mins)} — a ceiling")
            if mins <= 15 and not out["floor_min"]:
                out["pace"] = "quick"
    m = re.search(_AWAY, low)
    if m:
        mins = _dur(m)
        if mins and mins >= 30:
            out.update(pace="slow", budget_min=mins, why=f"you said you are away for about {mins // 60 if mins >= 60 else mins} {'hours' if mins >= 120 else 'hour' if mins >= 60 else 'minutes'}")
    m = re.search(_DEADLINE, low)
    if m and not out["deadline_min"]:
        mins = _dur(m)
        if mins:
            if out["budget_min"] and mins == out["budget_min"]:
                pass                                                    # "in 5 hours" already read as the away-time
            else:
                out.update(deadline_min=mins, why=f"you want it in {mins} minutes" if mins < 120 else f"you want it in {mins // 60} hours")
                out["pace"] = "quick" if mins <= 15 else out["pace"]
    unquoted = re.sub(r"[\"“”'‘’]([^\"“”'‘’]{1,40})[\"“”'‘’]", " ", low)           # 'you put "quick" as timing' is about the word, not a wish
    if re.search(_QUICK, unquoted) and out["pace"] != "slow" and not out["floor_min"] and not re.search(_SLOW, low):
        out["pace"] = "quick"
        out["why"] = out["why"] or "you said quick"
        if out["deadline_min"] is None and re.search(r"\b(in 10|10 min|ten min|real quick|make it quick)\b", low):
            out["deadline_min"] = 10                                # a timer only when the owner gave (or clearly implied) minutes
    if re.search(_SLOW, low):
        out["pace"] = "slow"
        out["why"] = out["why"] or "you said to take it slow"
    return out


def _span(mins):
    mins = int(mins)
    if mins < 60:
        return f"{mins} minutes"
    if mins % 60 == 0:
        return f"{mins // 60} hour" + ("s" if mins > 60 else "")
    return f"{mins // 60} h {mins % 60} min"


# what a job usually takes when the owner gives no time — said in the plan, so "unspecified" is a choice, not a guess
USUAL_MIN = {"seller_check": "5–10", "research": "2–5", "compare": "3–6", "trending": "1–3", "build_site": "5–10",
             "watch": "1–3", "summarize": "1", "visit": "1–2", "post": "1", "ask": "1"}


PACE_ONLY = re.compile(r"^\W*(?:no|yes|ok|okay|hey|please|but|and|i said|ho detto|ti ho detto)?\W*(?:(?:take (?:it|your time) (?:real |really |very )?slow(?:ly)?|slow down|slower|slowly|take it easy|take your time|no rush|no hurry|hurry( up)?|faster|quick(?:er|ly)?|speed (?:it )?up|"
                       r"con calma|piano|rallenta|più lento|sbrigati|fai presto|veloce|i said (?:slow|quick|fast)[^.!?,]*|(?:take|use|spend) (?:around |about )?\d+(?:\s*(?:-|–|to)\s*\d+)? ?(?:min(?:ute)?s?|h(?:ou)?rs?|ore))[\s,.!]*)+\W*$", re.I)
LIST_COMING = re.compile(r"\b(?:(?:this|the|a|my) list (?:that |which )?(?:i(?:'m| am| will| ?'ll)? (?:about to |going to |gonna )?(?:send|paste|write|give|attach)|i send (?:you )?(?:next|after|below|later))|"
                         r"(?:i(?:'m| am| will| ?'ll) (?:about to |going to |gonna )?(?:send|paste|give)(?: you)? (?:the|a|my) list)|(?:list (?:coming|follows|below|to follow|in the next message))|"
                         r"(?:la lista che (?:ti )?(?:mando|invio|sto per mandare))|(?:ti mando la lista))\b", re.I)


def pace_only(text):
    """'No, I said slow down!!' / 'take it very slowly' / 'take 5-6 hours' — a pace change, never a job of its own."""
    return bool(PACE_ONLY.match(text.strip())) and not re.search(r"https?://|\b(find|search|check|compare|research|cerca|trova|buy|list of)\b", text, re.I)


def list_coming(text):
    """The owner says the items come in a later message → the plan must wait for them."""
    return bool(LIST_COMING.search(text))


def _rule_brief(text, pace):
    """No thinking model: a sensible brief from patterns."""
    low = text.lower()
    counterfeit = bool(re.search(r"\b(reps?|replicas?|fakes?|knock-?offs?|dupes?)\b", low)) and bool(re.search(r"\b(nike|adidas|gucci|louis|prada|rolex|jordan|yeezy|balenciaga|supreme|dior|chanel|apple)\b", low))
    goal = text.strip().rstrip(".!?")
    kind, deliverable = "ask", "answer"
    url = re.search(r"https?://\S+", text)
    url = url or re.search(r"\b[a-z0-9.-]+\.(?:com|it|de|fr|es|net|org|co|io)(?:/\S*)?", low)
    if url and re.search(r"youtube\.com/watch|youtu\.be/|youtube\.com/shorts", url.group(0)):
        steps = ["Open the video and read the captions", "Note the concrete ideas and figures", "Send you the list"]
        return {"goal": goal, "deliverable": "list", "kind": "watch", "steps": steps, "questions": [], "counterfeit": False, "topic": url.group(0)}
    if url and len(re.sub(r"https?://\S+", "", low).split()) <= 3 or (url and re.search(r"\b(summari[sz]e|read|riassumi|tl;?dr|what does it say)\b", low)):
        steps = ["Open the page and read it fully", "Keep the key points with figures", "Write the summary"]
        return {"goal": goal, "deliverable": "answer", "kind": "summarize", "steps": steps, "questions": [], "counterfeit": False, "topic": url.group(0)}
    if re.search(r"\b(find|look for|search|cerca|trova|trovami|cercami)\b.*\b(seller|sellers|shop|shops|store|stores|supplier|suppliers|listing|listings|options?|deals?|cheap|good|venditor[ei]|fornitor[ei]|negoz[io])\b", low) \
            or re.search(r"\b(reliable|trustworthy|legit|reviews?|complaints?|affidabil[ei]|recensioni)\b", low) \
            or (url and re.search(r"\b(seller|shop|store|venditore|negozio|listing|member|profile|user)\b", low) and re.search(r"\b(ok|okay|good|legit|safe|trust|fine|serious|serio|affidabile|real|scam|fake)\b", low)):
        kind, deliverable = "seller_check", "document"
    elif re.search(r"\b(compare|comparison|vs\.?|versus|which is (better|cheaper))\b", low):
        kind, deliverable = "compare", "document"
    elif re.search(r"\b(build|make|create)\b.*\b(website|web site|landing page|site)\b", low):
        kind, deliverable = "build_site", "website"
    elif re.search(r"\b(make|write|draft|create|prepare|post|publish|scrivi|prepara|fai)\b.{0,30}\b(post|caption|tweet|reel|story|stories|carousel|pin|didascalia)\b", low) \
            or (re.search(r"\b(post|caption|tweet|reel|story|carousel)\b", low) and re.search(r"\b(on|for|about|su|per)\s+(instagram|insta|ig|facebook|fb|tiktok|x|twitter|linkedin|pinterest)\b", low)):
        kind, deliverable = "post", "post"                                   # "make a tiktok post about our mugs" is a post, not a video to watch
    elif re.search(r"\b(youtube|yt)\b", low) and re.search(r"\b(trending|trends?|trend|hot|popular|viral|most[- ](watched|viewed)|top \d+ videos?|top videos?|what'?s hot|di tendenza|tendenze|più visti)\b", low):
        kind, deliverable = "trending", "document" if re.search(r"\b(doc|document|google docs?|links?|comments?|report|sheet)\b", low) else "list"
    elif re.search(r"\b(watch|video|youtube|youtu\.be)\b", low) or (re.search(r"\btiktok\b", low) and not re.search(r"\b(trending|trends?|popular|viral|what'?s hot|selling)\b", low)):
        kind, deliverable = "watch", "list"
    elif re.search(r"\b(trending|trends?|popular right now|viral|what'?s hot|best[- ]sellers?)\b", low):
        kind, deliverable = "research", "document" if re.search(r"\b(list|options?|links?|doc|document)\b", low) else "answer"
    elif re.search(r"https?://\S+", low) and re.search(r"\b(summari[sz]e|read|riassumi|tl;?dr)\b", low):
        kind, deliverable = "summarize", "answer"
    elif re.search(r"\b(open|go to|visit|check)\b.*\b(youtube|amazon|etsy|ebay|vinted|instagram|tiktok|google maps|\.com|\.it)\b", low):
        kind, deliverable = "visit", "answer"
    elif re.search(r"\b(look up|look for|find( me)?|search( for)?|cerca|trova|trovami|cercami)\b.{0,80}\b(cheapest|cheap|best price|lowest|deals?|under \d|below \d|listings?|for sale|second[- ]hand|used|usat[oi]|econom\w+|meno car[oi]|prezzo più basso|offerte?)\b", low) \
            or re.search(r"\b(cheapest|best price|lowest price)\b.{0,60}\b(on|su)\s+(vinted|subito|ebay|amazon|etsy|wallapop|depop|aliexpress|temu|facebook marketplace|marketplace)\b", low):
        kind, deliverable = "research", "document" if re.search(r"\b(options?|list|links?|pictures?|images?|photos?|doc|document|report|walk me through|drive)\b", low) else "answer"
    elif re.search(r"\b(research|find out|look into|learn about|how does|how do|what is the best way)\b", low):
        kind, deliverable = "research", "document" if re.search(r"\b(options?|list|links?|pictures?|images?|photos?|doc|document|walk me through)\b", low) else "answer"
    elif re.search(r"\b(post|caption|tweet|reel|story for|stories for)\b", low):
        kind, deliverable = "post", "post"
    elif re.search(r"\b(hi|hello|hey|thanks|thank you|good (morning|evening|night)|ciao|grazie)\b", low) and len(low.split()) <= 6:
        kind, deliverable = "chat", "answer"
    if re.search(r"\b(doc|document|google docs?|walk me through|with (links|pictures|images))\b", low) and kind not in ("chat", "post", "build_site"):
        deliverable = "document"
    product = topic_of(text)
    product = re.sub(r"^(compare|comparison of|confronta|research|find out|look into|watch|summari[sz]e)\s+", "", product).strip() or product
    n_items = re.search(r"\btop\s+(\d{1,2})\b|\b(\d{1,2})\s+(?:trending |hot |popular |viral )?(?:videos?|clips?)\b", low)
    n_items = int(n_items.group(1) or n_items.group(2)) if n_items else None
    if kind == "trending":
        m_ = re.search(r"\b(?:about|on|around|regarding|riguardo a?|su|sul|sulla|sui|sugli)\s+(?!youtube\b|yt\b|each\b|every\b|the (?:top|first|list)\b)([a-zà-ú0-9][a-zà-ú0-9 '&-]{2,60}?)(?=\s*(?:[,.;?!]|\band\b|\bwith\b|\bin a\b|\bright now\b|\btoday\b|\bthis week\b|\boggi\b|$))", low)
        product = (m_.group(1).strip() if m_ else "")
        if product in ("each", "every", "them", "all"):
            product = ""
        product = re.sub(r"\b(youtube|yt|videos?|the|right now|today|this week)\b", " ", product)
        product = re.sub(r"\s{2,}", " ", product).strip(" ,.-")
    conds = [c.strip(" .;,") for c in re.findall(r"\(([^()]{8,160})\)", text)]
    conds += [m.strip(" .;,") for m in re.findall(r"(?:^|[.;,]\s*)((?:it |they |[a-z.]+ )?(?:has to|have to|must|needs? to|should|only if|no |not just|without|excluding|deve|devono|solo se|senza)\b[^.;()]{4,120})", text, flags=re.I)]
    conds += [m.strip(" .;,") for m in re.findall(r"(?:^|[.;]\s*)((?:[A-Za-z][\w' ]{2,40}?)\s+(?:is|are|sono|è)\s+(?:only |solo )?(?:ok|okay|fine|allowed|accepted|good|valid|bene)\s+(?:only |solo )?(?:if|when|se|quando)\b[^.;()]{4,120})", text, flags=re.I)]   # "Facebook marketplace is only ok if they're in Barletta"
    conds += [m.strip(" .;,") for m in re.findall(r"\b(i want (?!you to |u to |it |a |an |the |some |to )[^.;()]{4,80})", text, flags=re.I)]   # "I want only new items" — not "I want you to find…"
    conds += [m.strip(" .;,") for m in re.findall(r"\b((?:solo|soltanto|only)\s+(?:con|with|if|se)\s+[^.;()]{3,60})", text, flags=re.I)]
    seen, conditions = set(), []
    for c in conds:
        k = c.lower()
        if k not in seen and not any(k in o.lower() and k != o.lower() for o in conds):
            seen.add(k); conditions.append(c)
    sites = re.findall(r"\b(vinted|subito(?:\.it)?|ebay(?:\.it)?|amazon(?:\.it)?|etsy|wallapop|depop|aliexpress|temu|facebook marketplace|marketplace di facebook|zalando|leroy merlin|ikea|alibaba|shein|dhgate|banggood|kleinanzeigen|leboncoin)\b", low)
    sites = ["facebook marketplace" if s_ == "marketplace di facebook" else s_ for s_ in sites]
    sites = list(dict.fromkeys(s_.replace(".it", "") for s_ in sites))
    if counterfeit:
        goal = f"{goal} — note: branded replicas are counterfeit, so I research genuine/unbranded options instead"
        product = re.sub(r"\b(reps?|replicas?|fakes?|knock-?offs?|dupes?)( of| for)?\b", "", product).strip()
        product = re.sub(r"\b(nike|adidas|gucci|louis vuitton|prada|rolex|jordan|yeezy|balenciaga|supreme|dior|chanel)\b", "", product).strip(" ,")
        product = re.sub(r"\s{2,}", " ", product).strip() or "the product"
        product = f"genuine or unbranded {product}"
    link = re.search(r"(?:https?|file)://\S+", text)
    if kind == "seller_check" and link:
        u = urllib.parse.urlparse(link.group(0))
        host = re.sub(r"^www\.", "", u.netloc) or (u.path.rsplit("/", 1)[-1].rsplit(".", 1)[0] or "the page")
        product = f"{host} — {link.group(0)}"
        goal = f"Check whether {host} is a trustworthy shop/seller (the link you sent) — listing, reviews, social media, shipping, red flags"
    steps = {
        "seller_check": ([f"Open the link you gave me ({host}) and read the listing: price, condition, photos, shipping cost/time, where it ships from, materials"] if link else
                         [f"Search for {product or 'the product'} on marketplaces and independent shops (3–6 candidates)",
                         "Open each listing: price, condition, photos, shipping cost/time, where it ships from, materials"]) +
                        ["Read the seller's reviews and complaints; look up their social media page and its comments",
                         "Judge reliability" + ("" if link else " per seller") + " (account age, ratings, response to complaints, red flags)",
                         "Write the document: " + ("the shop's card with picture, link, verdict and the red/green flags" if link else "one section per option with picture, link, verdict; a short ranking on top"),
                         "If the store is open, offer to add " + ("it" if link else "the good ones") + " to the shop with price and shipping"],
        "compare": [f"Find 3–5 sources for {product or 'the options'}", "Extract price, shipping, terms, ratings from each",
                    "Put them side by side and pick a winner with the reason", "Write the comparison with links"],
        "research": ([f"Search {' and '.join(sites)} for {product or 'the topic'} — listings with shipping, cheapest first" if sites else f"Read 3–5 solid pages about {product or 'the topic'}"]
                     + (["Open the best listings: price, shipping, condition, seller rating, photos"] if sites else [])
                     + ["Keep the facts and figures with their sources"]) + [
                     "Write a short report" + (" with links and pictures" if deliverable == "document" else "")],
        "build_site": ["Collect the brief: name, place, what they do, opening hours, contact", "Write the copy for home / about / services / contact",
                       "Build the pages (mobile-friendly, contact form, map link)", "Check every page in the browser and fix what looks wrong",
                       "Save the site to my library and send you the link"],
        "trending": [f"Read YouTube's public search results sorted by views for this week{(' about ' + product) if product else ' (broad terms: trending, viral, news, trailers, music)'} — the trending feed itself is hidden from visitors",
                     f"Keep the top {n_items or 5}: title, channel, views, upload time, link",
                     "Open each video's comment feed and keep the most-liked comment",
                     "Write the list" + (" as a document with the links and the top comment for each, and put it in my Drive" if deliverable == "document" else " with links and the top comment for each")],
        "watch": ["Open the video(s) and read the captions", "Note the concrete ideas and figures", "Send you the list with timestamps"],
        "summarize": ["Open the page and read it fully", "Keep the key points with figures", "Write the summary"],
        "visit": ["Open the site", "Find the part the request is about", "Report what is there in plain words"],
        "post": ["Read the store's facts about the product", "Draft the post within the platform's limits", "Send it to you to approve"],
        "ask": ["Answer from my own knowledge", "If I don't know it well enough, look it up first"],
        "chat": [],
    }[kind]
    out = {"goal": goal, "deliverable": deliverable, "kind": kind, "steps": steps, "questions": [], "counterfeit": counterfeit, "topic": product or goal, "constraints": conditions[:4], "sites": sites[:5]}
    deal_words = re.search(r"\b(best deals?|cheapest|best price|lowest price|good deals?|bargains?|occasion[ei]|affar[ei]|prezzo più basso|meno car[oi])\b", low)
    if deal_words and sites and kind in ("research", "seller_check", "ask") and not list_coming(text) and product and len(product.split()) <= 12:
        names = [x.strip() for x in re.split(r"\s*(?:,|;|\band\b|\be\b|/)\s*", re.sub(r"\b(the |some |a few )?(best |good |great )?(deals?|bargains?|prices?|offers?|occasion[ei]|affar[ei])\b|\b(cheapest|best price|lowest price|for|on|per|su)\b", " ", product, flags=re.I)) if x.strip()]
        names = [re.sub(r"\s{2,}", " ", n).strip(" .-") for n in names]
        names = [n for n in names if 2 <= len(n) <= 60 and not re.fullmatch(r"(a|an|the|some|used|new|cheap|good|me)", n)]
        if names:
            out["items"] = [{"name": n, "max": None} for n in names[:10]]
            out["kind"] = "research"
            out["deliverable"] = "document"
            out["goal"] = f"Find the best deals for {', '.join(names)} on {', '.join(sites)}"
            out["topic"] = "; ".join(names)
            out["steps"] = [f"Search {' and '.join(sites)} for each item — cheapest sound listings first (no accessories, no broken units)",
                            "Open the best listing per item for the seller's feedback and shipping",
                            "Write the document: one section per item with links, pictures and prices"]
    if list_coming(text) and kind in ("research", "seller_check", "compare", "ask"):
        out["kind"] = "research"                                                   # deals for many items = research per item, not one seller check
        out["deliverable"] = "document"
        out["topic"] = "the items on your list"
        out["needs_list"] = True
        out["goal"] = "Find the best deals for each item on the list you send" + (f" (on {', '.join(sites)})" if sites else "")
        out["steps"] = ["Wait for your list (one item per line)",
                        f"Search {' and '.join(sites) if sites else 'the marketplaces'} for each item — used listings with shipping, cheapest first",
                        "Open the best listings per item: price, condition, seller rating, shipping, where it is" + (" (Facebook only if the seller is in the city you named)" if any("facebook" in c.lower() for c in out["constraints"]) else ""),
                        "Write the document: one section per item, best deal first, with links, pictures and the seller's rating"]
        out["constraints"] = [c for c in out["constraints"] if not re.search(r"\babout to send\b|\bi want you to\b", c, re.I)]
    if kind == "trending":
        out["topic"] = product                                                  # "" = global; never the whole sentence
        out["n"] = n_items or 5
    return out


class Brief:
    def __init__(self, planner=None, log=None):
        self.planner = planner
        self.log = log or (lambda kind, **f: None)

    def make(self, text):
        pace = parse_pace(text)
        if pace_only(text):                                                        # "slow down!!" is not a job
            return {"goal": text.strip(), "deliverable": "answer", "kind": "chat", "steps": [], "questions": [], "counterfeit": False,
                    "topic": "", "constraints": [], "sites": [], "pace": pace, "pace_only": True, "t": time.time()}
        b = _rule_brief(text, pace)
        if self.planner is not None and self.planner.installed() and b["kind"] not in ("chat",) and len(text.split()) >= 3:
            try:
                raw = self.planner.chat("You plan work for a business assistant. Output JSON only.", PACE_PROMPT + json.dumps(text), max_tokens=320, timeout=120)
                m = re.search(r"\{.*\}", raw, re.S)
                j = json.loads(m.group(0)) if m else {}
                if isinstance(j.get("steps"), list) and 2 <= len(j["steps"]) <= 8 and all(isinstance(s, str) and 3 < len(s) < 160 for s in j["steps"]):
                    b["steps"] = [s.strip().rstrip(".") for s in j["steps"]]
                if j.get("kind") in ("research", "seller_check", "compare", "summarize", "visit", "watch", "build_site", "post", "ask", "chat"):
                    if not (b["kind"] == "seller_check" and j["kind"] == "research") and b["kind"] != "trending" and not b.get("needs_list"):        # rules see sellers and trending better than the small model
                        b["kind"] = j["kind"]
                if j.get("deliverable") in ("answer", "list", "document", "file", "website", "post", "reply"):
                    b["deliverable"] = j["deliverable"] if not (b["deliverable"] == "document" and j["deliverable"] == "answer") else "document"
                if isinstance(j.get("goal"), str) and 5 < len(j["goal"]) < 200 and not b.get("needs_list"):
                    b["goal"] = j["goal"].strip()
                if b.get("needs_list") and b["steps"] and not b["steps"][0].lower().startswith("wait for your list"):
                    b["steps"] = ["Wait for your list (one item per line)"] + b["steps"][:6]
                if isinstance(j.get("questions"), list):
                    b["questions"] = [q for q in j["questions"] if isinstance(q, str) and 5 < len(q) < 160][:2]
            except Exception as e:
                self.log("brief_model_error", error=str(e)[:120])
        b["pace"] = pace
        b["t"] = time.time()
        self.log("brief", task=b["kind"], deliverable=b["deliverable"], pace=pace["pace"], deadline=pace["deadline_min"], budget=pace["budget_min"], steps=len(b["steps"]))
        return b

    @staticmethod
    def list_items(text):
        """The owner's list → [{'name', 'max'}]. Lines, numbered lines, bullets or a comma list of ≥ 2 short things; else []."""
        raw = [l.strip(" \t-•*·–—") for l in text.strip().splitlines() if l.strip(" \t-•*·–—")]
        raw = [re.sub(r"^\(?\d{1,2}[.)]\s*", "", l) for l in raw]
        if len(raw) == 1 and raw[0].count(",") >= 1 and len(raw[0]) < 300 and not re.search(r"\b(find|search|look|check|cerca|trova)\b", raw[0], re.I):
            raw = [x.strip() for x in raw[0].split(",") if x.strip()]
        if not raw or (len(raw) == 1 and (len(raw[0].split()) > 8 or re.search(r"\b(find|search|look|check|cerca|trova|please|can you)\b", raw[0], re.I))):
            return []
        items = []
        for l in raw[:25]:
            m = re.search(r"\s*(?:—|–|-|:|\(|,)?\s*(?:max(?:imum)?|under|below|fino a|massimo|entro|budget)?\s*(?:€|eur)?\s*(\d{1,5})\s*(?:€|eur|euro)?\)?\s*$", l, re.I)
            mx = int(m.group(1)) if m and re.search(r"max|under|below|fino|massimo|entro|budget|€|eur", l, re.I) else None
            name = re.sub(r"\s*(?:—|–|-|:|\(|,)?\s*(?:max(?:imum)?|under|below|fino a|massimo|entro|budget)?\s*(?:€|eur)?\s*\d{1,5}\s*(?:€|eur|euro)?\)?\s*$", "", l, flags=re.I).strip(" -—–:(") if mx else l
            if 2 <= len(name) <= 80:
                items.append({"name": name, "max": mx})
        if len(items) == 1 and (len(items[0]["name"].split()) < 2 or re.fullmatch(r"(ok(ay)?|yes|no|go|thanks?|grazie|ciao|hi|hello|stop|cancel|why|what|status)\W*", items[0]["name"], re.I)):
            return []                                                              # "ok" / "go" is not a one-item list
        return items

    @staticmethod
    def with_items(b, items):
        """The waiting plan + the list → a runnable research brief (topic = the items, one section each)."""
        b = dict(b); b.pop("needs_list", None)
        b["items"] = items
        names = [i["name"] + (f" (max € {i['max']})" if i.get("max") else "") for i in items]
        b["topic"] = "; ".join(names)
        b["goal"] = re.sub(r"the list you send", f"your list ({len(items)} items)", b["goal"])
        b["steps"] = [st for st in b["steps"] if not st.lower().startswith("wait for your list")]
        b["kind"] = "research"
        b["deliverable"] = "document"
        return b

    def amend(self, b, change):
        """Apply an owner's change request to a pending plan (constraints, pace, dropped steps)."""
        low = change.lower().strip(" .!")
        b = dict(b); b["steps"] = list(b["steps"]); b["constraints"] = list(b.get("constraints") or [])
        before = len(b["constraints"])
        pace = parse_pace(change)
        if pace["pace"] != "normal" or pace["deadline_min"] or pace["budget_min"]:
            b["pace"] = pace
        m = re.search(r"\b(?:max|under|below|less than|massimo|sotto|entro)\s*(?:€|eur)?\s*(\d+)\s*(?:€|eur|euro)?", low)
        if m:
            b["constraints"] = [c for c in b["constraints"] if not c.startswith("max")] + [f"max € {m.group(1)}"]
        m = re.search(r"\b(?:only|solo|just)\s+([a-z]+(?: [a-z]+)?)\s+(sellers?|shops?|stores?|suppliers?|venditori)\b", low)
        if m:
            b["constraints"].append(f"only {m.group(1)} {m.group(2)}")
        m = re.search(r"\b(?:from|in|da|ship(?:ping|s)? from)\s+(italy|italia|europe|europa|eu|germany|spain|france|uk|usa|china)\b", low)
        if m:
            b["constraints"].append(f"ships from {m.group(1)}")
        if re.search(r"\b(skip|no|without|senza)\b.*\b(social|instagram|facebook)", low):
            b["steps"] = [st for st in b["steps"] if not re.search(r"social", st, re.I)]
            b["constraints"].append("no social media check")
        if re.search(r"\b(skip|no|without|senza)\b.*\b(reviews?|recensioni)", low):
            b["steps"] = [st for st in b["steps"] if not re.search(r"review", st, re.I)]
        m = re.search(r"\b(?:drop|remove|skip|togli|salta)\s+(?:step\s+)?(\d)\b", low)
        if m and 1 <= int(m.group(1)) <= len(b["steps"]):
            b["steps"].pop(int(m.group(1)) - 1)
        m = re.search(r"\b(\d)\s+(?:options?|sellers?|results?|candidates?)\b", low)
        if m:
            b["n"] = max(1, min(8, int(m.group(1))))
            b["constraints"].append(f"{b['n']} options")
        if not (m or len(b["constraints"]) > before or pace["pace"] != "normal" or pace["deadline_min"] or pace["budget_min"]) and len(low.split()) >= 2:
            b["constraints"].append(change.strip())                       # keep the owner's words as a constraint anyway
        if len(b["constraints"]) > before:
            b["topic"] = re.sub(r" \(.*\)$", "", b["topic"]) + " (" + "; ".join(dict.fromkeys(b["constraints"])) + ")"
            b["goal"] = re.sub(r" — .*$", "", b["goal"]) + " — " + "; ".join(dict.fromkeys(b["constraints"]))
        self.log("brief_amended", constraints=len(b["constraints"]))
        return b

    @staticmethod
    def text(b):
        """Render for Telegram: what I understood, the pace, the plan."""
        p = b["pace"]
        pace_line = {"quick": "⏱ quick", "slow": "🐢 slow — I'll use the time", "normal": "⏳ normal pace"}[p["pace"]]
        if p.get("floor_min"):
            pace_line += (f" · ⏬ at least {_span(p['floor_min'])}, as you asked: I hand you the first pass as soon as it's ready, then keep going "
                          f"(deeper reading on the topic, steps on our projects) until the time is used — say 'that's enough' to stop earlier")
        if p.get("deadline_min"):
            pace_line += f" · ⏰ {'at most ' if p.get('floor_min') or 'ceiling' in (p.get('why') or '') else 'you want it in '}{p['deadline_min']} min — I'll keep a timer on my screen and tell you if I run late"
        if p.get("budget_min"):
            pace_line += f" · up to {p['budget_min'] // 60} h available — when I finish early I'll go on studying"
        if p["pace"] == "normal" and not p.get("deadline_min") and not p.get("budget_min") and not p.get("floor_min"):
            pace_line += f" — you gave no time, so I pick: about {USUAL_MIN.get(b.get('kind'), '2–5')} min is what a {b.get('kind', 'job').replace('_', ' ')} usually needs; tell me a floor or a ceiling if you want otherwise"
        out = [f"📋 What I understood: {b['goal']}", f"{pace_line}", f"📦 I'll hand you: {dict(answer='an answer', list='a list', document='a document with links and pictures', file='a file', website='a website', post='a post to approve', reply='a reply to approve')[b['deliverable']]}"]
        if b["steps"]:
            out.append("My plan:\n" + "\n".join(f"{i + 1}. {s}" for i, s in enumerate(b["steps"])))
        if b.get("constraints"):
            out.append("Your conditions: " + "; ".join(dict.fromkeys(b["constraints"])))
        if b.get("questions"):
            out.append("Before I start: " + " ".join(b["questions"]))
        if b.get("counterfeit"):
            out.append("⚠️ Branded replicas are counterfeit (illegal to sell, fines even for buying in Italy) — I research genuine or unbranded options instead.")
        return "\n\n".join(out)
