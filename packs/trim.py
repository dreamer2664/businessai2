"""Trim bulk text into dense knowledge passages for the brain.

Input:  TSVs from openstax_fetch.py (title, chapter, text) and the web fetcher
        (title, topic, url, text); text has paragraphs joined by literal "\\n".
Output: <out>/articles.tsv  aid \\t path \\t title
        <out>/passages.tsv  aid \\t text          (same format wiki_prepare.py expects)

What is thrown away (the "filler"):
 - paragraphs that are stories/anecdotes rather than teaching (first-person, quotes, named
   people doing things), chapter pep-talk ("in this chapter you will learn"), link lists,
   calls to action / product plugs, source and credit lines, image descriptions,
 - very short fragments, duplicates (same normalised text seen before),
 - paragraphs with a low share of "informative" words (numbers, defined terms, verbs like
   is/means/refers/includes) — measured by a simple density score.
What is kept: definitions, mechanisms, lists of factors, numbers, how-to steps.
"""
import hashlib
import os
import re
import sys

MAX_CHARS, MIN_CHARS = 600, 80
RE_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")

FILLER = re.compile(
    r"^(in this (chapter|section|module)|by the end of this|this chapter|this section|as you (read|learned|will)|"
    r"we (will|'ll) (discuss|explore|look|examine|see|cover|explain)|let's (look|take|examine|explore|start|begin)|"
    r"now that you|you (will|'ll) (learn|discover|find|see|read)|before (we|you) (begin|start|dive)|"
    r"imagine (you|that|a)|think about|consider (the|a|this) (following|case|example|story)|"
    r"for example, (imagine|suppose|consider)|as (we|you) (saw|discussed|noted|mentioned)|"
    r"in the (next|previous|following) (chapter|section)|later in this|earlier in this|"
    r"click|visit|watch|listen|read more|learn more|check out|sign up|start (your )?free trial|"
    r"try shopify|shopify (offers|makes|lets|has|is|provides|helps)|with shopify|shopify's|on shopify,|"
    r"source:|credit:|\(credit|photo|image|figure \d|exhibit \d|table \d|"
    r"the following (video|link|resources)|see (the )?(video|link)|"
    r"as (the |a )?(ceo|founder|owner|president|manager|vp) of|says? [A-Z][a-z]+ [A-Z]|"
    r"“|\"|according to [A-Z][a-z]+ [A-Z][a-z]+,|i (was|am|have|had|think|remember|started)|my (first|own|business|store)|"
    r"we (started|launched|founded|grew|built) our|our (company|store|team|customers)|"
    r"(he|she) (was|is|had|has|started|founded|launched|says|said|explains|explained|recalls|adds|told)|"
    r"[A-Z][a-z]+ [A-Z][a-z]+ (is|was) (the |a |an )?(founder|ceo|owner|president|entrepreneur|professor|author)|"
    r"(faq|frequently asked questions)|key takeaways?|conclusion|final thoughts|in summary|to sum up|"
    r"want to|ready to|whether you|no matter|if you're (looking|ready|new)|good luck|happy selling|"
    r"disclaimer|this (post|article|guide) (was|is|will|covers)|(originally )?published|updated|"
    r"here'?s how|learn (how|why|what)|find out|discover how|in this guide|this guide|keep reading|read on|"
    r"we'?ll (show|walk|cover)|below,? (we|you)|let'?s (dive|get))",
    re.I)
INFO = re.compile(r"\b(is|are|means|refers|defin\w*|includ\w*|consist\w*|typical\w*|usual\w*|average|percent\w*|%|"
                  r"formula|calculat\w*|cost\w*|pric\w*|margin\w*|rate\w*|ratio|revenue|profit\w*|customer\w*|supplier\w*|"
                  r"seller\w*|product\w*|order\w*|ship\w*|market\w*|sale\w*|brand\w*|ad|ads|strateg\w*|process\w*|step\w*|"
                  r"factor\w*|type\w*|kind|method\w*|because|therefore|result\w*|increas\w*|decreas\w*|"
                  r"should|must|need\w*|requir\w*|allow\w*|help\w*|reduc\w*|improv\w*|measur\w*|track\w*|test\w*|compar\w*|"
                  r"choos\w*|avoid\w*|check\w*|look for|at least|minimum|maximum|percentage|feedback|rating\w*|review\w*)\b", re.I)
STORY = re.compile(r"\b(he|she|his|her|him|they|their|I|my|we|our|us)\b", re.I)
# Italian + marketplace vocabulary (TRIM_LANG=it-en): help centres, guides and video walkthroughs are how-to text in the second
# person ("puoi", "devi", "you can") — informative for a shopper, not a story. Counted as INFO, and "you/tu" is not a story word.
INFO_IT = re.compile(r"\b(è|sono|significa|indica|comprende|include|consiste|di solito|in genere|solitamente|media|percentuale|costa|costano|prezz\w*|"
                     r"commission\w*|spedizion\w*|spedir\w*|consegn\w*|rimbors\w*|res[oi]|restituz\w*|protezion\w*|acquist\w*|vend\w*|venditor\w*|"
                     r"compr\w*|acquirent\w*|ordin\w*|annunci\w*|articol\w*|prodott\w*|pagament\w*|pag\w*|carta|bonifico|contanti|postepay|paypal|"
                     r"tracci\w*|pacco|corriere|punto di ritiro|locker|inpost|dogan\w*|iva|dazi\w*|tagli\w*|recension\w*|valutazion\w*|feedback|"
                     r"truff\w*|frod\w*|segnal\w*|blocc\w*|verific\w*|account|profilo|password|codice|email|e-mail|"
                     r"pu[oò]i|potete|devi|dovete|bisogna|occorre|consigli\w*|evit\w*|controll\w*|scegli\w*|imposta\w*|clicc\w*|selezion\w*|"
                     r"entro|prima|dopo|giorni|ore|settimane|minuti|euro|€|almeno|massimo|minimo|gratis|gratuit\w*|"
                     r"you can|you should|you must|you need|make sure|tip|tips|option|options|step|steps|button|tap|click|select|choose|"
                     r"seller|buyer|listing|shipping|delivery|refund|return|protection|fee|scam|fraud|verify|dispute|tracking|parcel|"
                     r"courier|customs|duty|size|review|rating|account|offer|bundle|discount|coupon|wallet|payment|days|hours|weeks)\b", re.I)
STORY_IT = re.compile(r"\b(he|she|his|her|him|they|their|I|my|we|our|us|io|mio|mia|miei|mie|noi|nostro|nostra|lui|lei|loro)\b", re.I)
LANG = os.environ.get("TRIM_LANG", "en")


def norm(t):
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def density(t):
    words = re.findall(r"[A-Za-zÀ-ÿ0-9%$€]+", t)
    if not words:
        return 0
    if LANG == "it-en":
        info = len(INFO.findall(t)) + len(INFO_IT.findall(t)) + 2 * len(re.findall(r"\d", t)) / max(1, len(t) / 40)
        story = len(STORY_IT.findall(t))
        return (info - 0.5 * story) / len(words) * 100
    info = len(INFO.findall(t)) + 2 * len(re.findall(r"\d", t)) / max(1, len(t) / 40)
    story = len(STORY.findall(t))
    return (info - 0.8 * story) / len(words) * 100


FILLER_SOFT = re.compile(r"^(here'?s how|learn (how|why|what)|find out|in this guide|this guide|keep reading|read on|"
                         r"want to|ready to|whether you|no matter|if you're (looking|ready|new)|updated|(faq|frequently asked questions))", re.I)


def keep(p, title):
    if p.startswith("## "):
        return len(p) <= 100
    if len(p) < MIN_CHARS:
        return False
    if FILLER.search(p):
        if not (LANG == "it-en" and FILLER_SOFT.search(p) and len(p) > 160 and not re.search(r"subscribe|click|visit|sign up|free trial", p, re.I)):
            return False
    if re.search(r"https?://|www\.", p) and not (LANG == "it-en" and title.startswith("handbook:")):   # the handbook's search URLs are the knowledge
        return False
    if p.count("?") >= 2 and len(p) < 300:          # question lists
        return False
    if density(p) < 5.5:
        return False
    return True


def split_long(t):
    if len(t) <= MAX_CHARS:
        return [t]
    out, cur = [], ""
    for s in RE_SENT.split(t):
        if cur and len(cur) + 1 + len(s) > MAX_CHARS:
            out.append(cur); cur = s
        else:
            cur = (cur + " " + s) if cur else s
    if cur:
        out.append(cur)
    return out


def passages(text, title):
    paras = [p.strip().replace("\u2019", "'").replace("\u2018", "'") for p in text.split("\\n")]
    out, seen, heading = [], set(), ""
    buf = ""
    for p in paras:
        if not p:
            continue
        if p.startswith("## "):
            if buf:
                out.append(buf); buf = ""
            heading = p[3:].strip()
            continue
        if len(p) < MIN_CHARS and len(p) >= 30 and buf and not FILLER.search(p) and density(p) >= 4.5 \
                and (not re.search(r"https?://|www\.", p) or title.startswith("handbook:")):
            buf = buf + " " + p            # short fact ("Try to work with suppliers who have at least 95%…") rides along
            continue
        if not keep(p, title):
            continue
        h = hashlib.md5(norm(p)[:200].encode()).hexdigest()
        if h in seen:
            continue
        seen.add(h)
        # prefix the local heading once so passages carry their context ("Pricing strategy: ...")
        if heading and heading.lower() not in title.lower() and not buf:
            p = f"{heading}: {p}"
        if buf and len(buf) < MIN_CHARS * 2:
            buf = buf + " " + p
        else:
            if buf:
                out.append(buf)
            buf = p
    if buf:
        out.append(buf)
    final = []
    for p in out:
        final.extend(split_long(p))
    return [p for p in final if len(p) >= MIN_CHARS]


def main():
    out_dir = sys.argv[-1]
    os.makedirs(out_dir, exist_ok=True)
    fa = open(os.path.join(out_dir, "articles.tsv"), "w", encoding="utf-8")
    fp = open(os.path.join(out_dir, "passages.tsv"), "w", encoding="utf-8")
    aid = 0
    stats = {}
    gseen = set()
    for src in sys.argv[1:-1]:
        n_in = n_out = c_in = c_out = 0
        for line in open(src, encoding="utf-8"):
            cols = line.rstrip("\n").split("\t")
            if len(cols) == 3:
                title, topic, text = cols; path = os.path.basename(src)[:-4] + "/" + re.sub(r"\W+", "_", title)[:60]
            elif len(cols) >= 4:
                title, topic, url, text = cols[:4]; path = url
                title = re.sub(r"\s*[-|–]\s*Shopify.*$", "", title).strip()
            else:
                continue
            title = re.sub(r"^\d+(\.\d+)?\s+", "", title)
            title = re.sub(r"\s*\(\d{4}\)\s*$", "", title)
            if topic == "glossary":
                ps = [d.strip() for d in text.split("\\n") if len(d.strip()) >= 30]
            else:
                ps = passages(text, title)
            ps2 = []
            for p in ps:
                h = hashlib.md5(norm(p)[:160].encode()).hexdigest()
                if h in gseen:
                    continue
                gseen.add(h); ps2.append(p)
            n_in += 1; c_in += len(text)
            if len(ps2) < 2:
                continue
            fa.write(f"{aid}\t{path}\t{title}\n")
            for p in ps2:
                fp.write(f"{aid}\t{p}\n")
                c_out += len(p)
            n_out += len(ps2); aid += 1
        stats[os.path.basename(src)] = (n_in, n_out, c_in, c_out)
        print(f"{os.path.basename(src):30s} {n_in:4d} docs -> {n_out:5d} passages, {c_in/1e6:.2f} -> {c_out/1e6:.2f} M chars ({100*c_out/max(1,c_in):.0f}% kept)", flush=True)
    fa.close(); fp.close()
    tot_out = sum(s[3] for s in stats.values()); tot_in = sum(s[2] for s in stats.values())
    print(f"TOTAL {aid} articles, {sum(s[1] for s in stats.values())} passages, {tot_in/1e6:.2f} -> {tot_out/1e6:.2f} M chars")


if __name__ == "__main__":
    main()
