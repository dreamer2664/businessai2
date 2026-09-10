"""Video transcripts → dense knowledge paragraphs (no vlog talk), in the (title, topic, url, text) TSV the trimmer eats.
   python3 packs/distill_video.py <topic> <transcript.txt> [...] <out.tsv>

A transcript is speech: "hello my loves", "like and subscribe", "so basically", repeated words. What we keep is the
teaching: sentences that name a marketplace thing (fee, shipping, refund, seller, listing, size, scam, protection …) AND
say something concrete (a number, a how-to verb, a rule word). Sentences are cleaned, grouped into ~500-char paragraphs.
Rule-based on purpose: the pack must be small; the thinking model is not needed for this."""
import os, re, sys

TOPIC_WORDS = re.compile(r"\b(vinted|temu|shein|subito|wallapop|aliexpress|dhgate|banggood|ebay|marketplace|seller|buyer|listing|item|order|"
                         r"ship(ping|ped|s)?|deliver(y|ed)|refund|return(s|ed)?|protection|fee|price|pric(ing|ed)|offer|bundle|discount|coupon|"
                         r"tracking|parcel|package|label|locker|inpost|courier|customs|vat|duty|size|sizing|review|rating|feedback|scam|fraud|"
                         r"fake|counterfeit|verify|verification|dispute|report|block|payment|pay|card|paypal|wallet|credit|account|profile|"
                         r"photo|picture|description|title|search|filter|category|brand|condition|tag|quality|cheap|expensive|budget|"
                         r"venditore|acquirente|annuncio|spedizione|spedire|rimborso|reso|resi|protezione|commissione|prezzo|offerta|"
                         r"tracciamento|pacco|corriere|dogana|iva|taglia|recensione|recensioni|truffa|truffe|pagamento|carta|foto|descrizione|"
                         r"ricerca|filtro|categoria|marca|condizioni|qualità|economico|costoso|tuttosubito|postepay|bonifico|contanti|ritiro)\b", re.I)
CONCRETE = re.compile(r"\d|\b(always|never|only|must|should|don'?t|do not|make sure|avoid|check|use|click|tap|choose|select|set|add|write|take|upload|"
                      r"ask|send|wait|pay|open|go to|means|is called|works|happens|costs?|takes?|within|before|after|per cent|percent|%|€|£|\$|"
                      r"sempre|mai|solo|devi|dovete|bisogna|evita|controlla|usa|clicca|scegli|imposta|scrivi|carica|chiedi|invia|aspetta|paga|apri|"
                      r"significa|funziona|costa|costano|entro|prima|dopo|giorni|settimane|ore|minuti|euro)\b", re.I)
VLOG = re.compile(r"\b(subscribe|like (and|&)|my channel|welcome back|hello my|hey guys|hi guys|hey everyone|today'?s video|this video|in the description|"
                  r"comment(s)? (below|down)|let me know|thank you for watching|thanks for watching|see you|bye|links? (below|in)|sponsor|discount code|"
                  r"iscrivetevi|iscriviti|canale|lasciate un like|mettete like|commentate|link in descrizione|nel video di oggi|oggi vi|ciao a tutti|"
                  r"ciao ragazzi|alla prossima|benvenuti)\b", re.I)
FILLER = re.compile(r"\b(um+|uh+|er+|ehm|cioè|tipo|like,|you know,|basically|actually|literally|obviously|honestly|kind of|sort of|so yeah|okay so|so so|"
                    r"right\?|insomma|allora|diciamo|praticamente|sostanzialmente|comunque|ecco|niente,)\b[,\s]*", re.I)


def sentences(text):
    t = re.sub(r"\[[^\]]{1,40}\]", " ", text)                 # [music], [clears throat]
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"(?<=[a-zà-ú,])\s+(?=(so|and|but|because|now|then|okay|ok|well|e|ma|però|quindi|poi|allora)\s)", " ", t)
    parts = re.split(r"(?<=[.!?])\s+", t)
    if len(parts) < 8:                                         # auto-captions have no punctuation: cut on discourse markers
        parts = re.split(r"\s+(?=(?:so|and then|but|because|now|okay|ok|the next|another|also|if you|when you|quindi|poi|inoltre|se |quando |un'?altra cosa)\b)", t, flags=re.I)
    out = []
    for p in parts:
        p = FILLER.sub("", p).strip(" ,;-–")
        p = re.sub(r"\b(\w+)( \1\b)+", r"\1", p, flags=re.I)  # "the the", "I I"
        p = re.sub(r"\s+([,.;:!?])", r"\1", p)
        if p:
            p = p[0].upper() + p[1:]
            if not p.endswith((".", "!", "?")):
                p += "."
            out.append(p)
    return out


def keep(s):
    w = len(s.split())
    if w < 7 or w > 60 or VLOG.search(s):
        return False
    if not TOPIC_WORDS.search(s) or not CONCRETE.search(s):
        return False
    if re.search(r"\b(I|I'm|I've|my|me|io|mio|mia|miei)\b", s) and not re.search(r"\b(recommend|tip|advice|suggest|always|never|consiglio|consiglia|sempre|mai)\b", s, re.I):
        return len(re.findall(r"\d", s)) >= 1 and w >= 12      # first-person allowed only when it carries a number
    return True


def distill(text):
    kept, seen = [], set()
    for s in sentences(text):
        if keep(s):
            k = re.sub(r"\W+", " ", s.lower())[:120]
            if k not in seen:
                seen.add(k); kept.append(s)
    paras, cur = [], ""
    for s in kept:
        if len(cur) + len(s) > 520 and cur:
            paras.append(cur.strip()); cur = ""
        cur += " " + s
    if cur.strip():
        paras.append(cur.strip())
    return paras


def main():
    topic, out = sys.argv[1], sys.argv[-1]
    fo = open(out, "a", encoding="utf-8")
    tot_in = tot_out = 0
    for path in sys.argv[2:-1]:
        raw = open(path, encoding="utf-8").read()
        title, _, body = raw.partition("\n")
        vid = re.sub(r"^video_|\.txt$", "", os.path.basename(path))
        paras = distill(body)
        tot_in += len(body); tot_out += sum(len(p) for p in paras)
        if len(paras) < 2:
            print("thin", title[:50], len(paras)); continue
        fo.write(f"{title.strip()}\t{topic}\thttps://youtu.be/{vid}\t" + "\\n".join(p.replace("\t", " ") for p in paras) + "\n")
        print(f"{title[:55]:57} {len(body):>6} → {sum(len(p) for p in paras):>5} chars, {len(paras)} paragraphs")
    print(f"total {tot_in} → {tot_out} chars ({100 * tot_out / max(1, tot_in):.0f} % kept)")


if __name__ == "__main__":
    main()
