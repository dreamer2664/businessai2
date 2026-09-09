"""Customer messages & social posts — drafted by the AI, approved by the owner (milestone 5).

Nothing here sends anything by itself. The flow is:
   message arrives (state/inbox.jsonl)  →  classify (intent, urgency, facts needed)
   →  draft a reply from the store policy + knowledge  →  owner taps Approve / Edit / Reject on the phone
   →  approved text is handed to the channel adapter (for now: written to state/outbox.jsonl and shown)
Every decision is remembered (state/inbox_decisions.jsonl) and the score set tests/inbox.txt measures the drafts:
   correct intent, policy respected, right tone, no invented facts (order numbers, dates, refunds never promised).

Store policy lives in state/policy.json — the owner sets it once (/policy) and every draft obeys it.

Channels: "practice" (sample messages loaded with /inbox practice, replies go to state/outbox.jsonl only), "owner" (a message the owner
pasted or forwarded — the approved text is handed back to paste), and since milestone 10 the real ones in agent/channels.py:
"email" (IMAP/SMTP), "facebook" and "instagram" (Meta Graph API) — approved replies are actually sent there.
"""
import datetime as _dt
import json
import re

from . import config

INBOX = config.STATE_DIR / "inbox.jsonl"
OUTBOX = config.STATE_DIR / "outbox.jsonl"
DECISIONS = config.STATE_DIR / "inbox_decisions.jsonl"
POLICY = config.STATE_DIR / "policy.json"
STYLE = config.STATE_DIR / "style.json"          # learned from the owner's edits: greeting, length, closing — never his text

GREET_RE = re.compile(r"^\s*(hi|hello|hey|ciao|dear|hallo|salve|buongiorno|good (morning|afternoon|evening))\b([^\n,!.:]{0,40})([,!.:]|\n|$)", re.I)
STOP_CLOSINGS = {"thanks", "thank you", "thanks again", "cheers", "best", "regards", "best regards", "kind regards", "take care",
                 "have a nice day", "talk soon", "bye", "ciao", "many thanks", "all the best", "sincerely"}

DEFAULT_POLICY = {
    "store_name": "our store",
    "owner_name": "",
    "tone": "friendly, short, honest; no exclamation marks in a row; never blame the customer",
    "shipping": "standard delivery 7-15 business days; tracking number sent by email when the parcel ships",
    "returns": "30 days from delivery for unused items; customer pays return shipping unless the item is faulty or wrong",
    "refunds": "refund issued within 5 business days after the returned item arrives; faulty/wrong items refunded or replaced at once, no return needed for items under 10 EUR",
    "ships_to": "",
    "products": "",
    "greeting": "",
    "discounts": "no discount codes given out in chat; newsletter subscribers get 10% on the first order",
    "escalate": "legal threats, chargeback mentions, injuries or safety complaints, press/influencer requests, anything about personal data",
    "sign_off": "Best regards,\nCustomer care",
}

COUNTRY_WORDS = (("switzerland", "CH", "Switzerland"), ("svizzera", "CH", "Switzerland"), ("schweiz", "CH", "Switzerland"), ("suisse", "CH", "Switzerland"), ("united kingdom", "GB", "the UK"), ("uk", "GB", "the UK"), ("england", "GB", "the UK"), ("scotland", "GB", "the UK"), ("london", "GB", "the UK"),
                 ("united states", "US", "the USA"), ("usa", "US", "the USA"), ("america", "US", "the USA"), ("canada", "CA", "Canada"), ("australia", "AU", "Australia"), ("norway", "NO", "Norway"), ("norvegia", "NO", "Norway"), ("japan", "JP", "Japan"), ("turkey", "TR", "Turkey"), ("brazil", "BR", "Brazil"), ("india", "IN", "India"), ("china", "CN", "China"), ("serbia", "RS", "Serbia"), ("ukraine", "UA", "Ukraine"), ("russia", "RU", "Russia"), ("israel", "IL", "Israel"), ("mexico", "MX", "Mexico"), ("dubai", "AE", "the UAE"), ("emirates", "AE", "the UAE"), ("new zealand", "NZ", "New Zealand"), ("south africa", "ZA", "South Africa"), ("iceland", "IS", "Iceland"), ("san marino", "SM", "San Marino"), ("vatican", "VA", "the Vatican"), ("andorra", "AD", "Andorra"), ("monaco", "MC", "Monaco"),
                 ("germany", "DE", "Germany"), ("germania", "DE", "Germany"), ("deutschland", "DE", "Germany"), ("berlin", "DE", "Germany"), ("munich", "DE", "Germany"), ("france", "FR", "France"), ("francia", "FR", "France"), ("paris", "FR", "France"), ("spain", "ES", "Spain"), ("spagna", "ES", "Spain"), ("españa", "ES", "Spain"), ("madrid", "ES", "Spain"), ("barcelona", "ES", "Spain"), ("italy", "IT", "Italy"), ("italia", "IT", "Italy"), ("sicily", "IT", "Italy"), ("sardinia", "IT", "Italy"), ("sicilia", "IT", "Italy"), ("sardegna", "IT", "Italy"),
                 ("austria", "AT", "Austria"), ("vienna", "AT", "Austria"), ("netherlands", "NL", "the Netherlands"), ("holland", "NL", "the Netherlands"), ("olanda", "NL", "the Netherlands"), ("amsterdam", "NL", "the Netherlands"), ("belgium", "BE", "Belgium"), ("belgio", "BE", "Belgium"), ("brussels", "BE", "Belgium"), ("portugal", "PT", "Portugal"), ("portogallo", "PT", "Portugal"), ("lisbon", "PT", "Portugal"), ("poland", "PL", "Poland"), ("polonia", "PL", "Poland"), ("ireland", "IE", "Ireland"), ("irlanda", "IE", "Ireland"), ("dublin", "IE", "Ireland"), ("greece", "GR", "Greece"), ("grecia", "GR", "Greece"), ("sweden", "SE", "Sweden"), ("svezia", "SE", "Sweden"), ("denmark", "DK", "Denmark"), ("danimarca", "DK", "Denmark"), ("finland", "FI", "Finland"), ("czech", "CZ", "Czechia"), ("prague", "CZ", "Czechia"), ("croatia", "HR", "Croatia"), ("croazia", "HR", "Croatia"), ("hungary", "HU", "Hungary"), ("ungheria", "HU", "Hungary"), ("romania", "RO", "Romania"), ("slovenia", "SI", "Slovenia"), ("slovakia", "SK", "Slovakia"), ("luxembourg", "LU", "Luxembourg"), ("lussemburgo", "LU", "Luxembourg"), ("malta", "MT", "Malta"), ("cyprus", "CY", "Cyprus"), ("cipro", "CY", "Cyprus"), ("bulgaria", "BG", "Bulgaria"), ("lithuania", "LT", "Lithuania"), ("latvia", "LV", "Latvia"), ("estonia", "EE", "Estonia"))
SHIP_DAYS = {"IT": "2–3", "DE": "4–6", "FR": "4–6", "ES": "4–6"}


def country_in(text):
    """(code, display name) for the first country/city named in a customer message, else (None, None)."""
    low = (text or "").lower()
    for w, code, name in COUNTRY_WORDS:
        if re.search(r"\b" + re.escape(w) + r"\b", low):
            return code, name
    return None, None


KINDS = ["where_is_my_order", "return_or_refund", "damaged_or_wrong", "product_question", "cancel_or_change",
         "discount_request", "complaint", "compliment", "spam_or_scam", "partnership_or_press", "other"]

CLASSIFY_PROMPT = """Classify a customer message for an online store. Reply with one JSON object only:
{"kind": KIND, "urgency": "low|normal|high", "needs": [facts the reply needs but the message doesn't give, e.g. "order number"], "escalate": true|false}
KIND is one of: %s
escalate=true when the message mentions lawyers, chargebacks, injury/safety, press/influencers, personal-data requests, or is abusive.
Message: """ % ", ".join(KINDS)

DRAFT_PROMPT = """You write replies to customers of a small online store on behalf of the owner.
STORE POLICY (obey exactly; never promise anything not covered here):
%s

RULES: plain, warm, 3-6 sentences, no bullet lists, no numbered steps. If the customer gave an order number, repeat it once
(e.g. "order 51410") so they know you have it; never mention any other number. You do NOT have access to orders, so you never know if a
parcel has shipped, where it is, or whether a cancellation is still possible: say what you will do ("I will check order 48213
and send you the tracking / options within one business day"). Never write placeholders like [tracking link] or [name]. Never
invent order numbers, dates, tracking numbers, prices or stock levels — if the reply needs a fact you don't have, ask the customer
for it. Never offer a refund, replacement or discount unless the policy above allows it for this exact situation. Apologise at
most once. Do not write a sign-off; it is added automatically.

CUSTOMER MESSAGE (%s, from %s):
%s

Write only the reply text. This is a new, unrelated conversation."""


def now():
    return _dt.datetime.now().isoformat(timespec="seconds")


def _append(path, rec):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _load(path):
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


class Inbox:
    def __init__(self, planner=None, brain=None, memory=None, log=None, shopfacts=None, store=None):
        self.shopfacts = shopfacts          # ShopFacts: exact sentences from the owner's own shop pages (may be None)
        self.store = store                  # practice Store: real order facts for channel "store" messages (may be None)
        self.planner = planner
        self.brain = brain
        self.memory = memory
        self.log = log or (lambda kind, **f: None)
        config.ensure_dirs()
        self.policy = self.load_policy()
        try:
            self.style = json.loads(STYLE.read_text(encoding="utf-8"))
        except Exception:
            self.style = {}

    # ---- policy ------------------------------------------------------------
    def load_policy(self):
        try:
            p = json.loads(POLICY.read_text(encoding="utf-8"))
            return {**DEFAULT_POLICY, **p}
        except Exception:
            return dict(DEFAULT_POLICY)

    def set_policy(self, key, value):
        if key not in DEFAULT_POLICY:
            return f"Unknown policy field '{key}'. Fields: {', '.join(DEFAULT_POLICY)}"
        self.policy[key] = value
        POLICY.write_text(json.dumps(self.policy, ensure_ascii=False, indent=1), encoding="utf-8")
        return f"Policy updated: {key} = {value}"

    POLICY_HELP = {"greeting": "how replies open, e.g. 'Ciao {name}!' — {name} becomes the customer's first name when I know it (empty = learned from your edits, else 'Hi {name},')",
                   "sign_off": "how replies end, e.g. 'Carlo' (learned automatically when you sign an edited reply)",
                   "ships_to": "countries you deliver to, e.g. 'EU countries, UK, Switzerland' (empty = I'll say the owner will confirm)",
                   "products": "facts about your products the AI may quote, e.g. 'LED lamp: 8 h battery, 3 brightness levels' (empty = I defer product questions to you)"}

    def style_text(self):
        st = self.style
        if not st.get("samples"):
            return ""
        bits = []
        if st.get("greeting"): bits.append(f"opens with '{st['greeting']}'")
        if st.get("sentences"): bits.append(f"about {st['sentences']} sentences")
        if st.get("closing"): bits.append(f"signs '{st['closing']}'")
        return f"learned from {st['samples']} of your edits: " + ", ".join(bits) if bits else ""

    # ---- what the owner's edits teach (style only — his words are never copied into another customer's reply)
    @staticmethod
    def first_name(rec):
        who = (rec or {}).get("from", "") or ""
        who = who.split("<")[0].strip()                                   # "Anna K. <anna@x>" → "Anna K."
        if not who or "@" in who or who.lower() in ("a customer", "customer"):
            return ""
        w = who.split()[0].strip(",.")
        return w if w[:1].isupper() and w.isalpha() and len(w) >= 2 else ""

    def learn_style(self, text, rec=None):
        st = self.style
        name = self.first_name(rec)
        m = GREET_RE.match(text)
        if m:
            g = m.group(0).strip()
            if name and name.lower() in g.lower():
                g = re.sub(re.escape(name), "{name}", g, flags=re.I)
            st["greeting"] = g
        body = text[m.end():] if m else text
        body = body.strip()
        tail = body.splitlines()[-1].strip() if body else ""
        if len(tail.split()) > 3:                                          # closing glued to the last sentence: "... latest. Carlo"
            tail = re.split(r"[.!?]\s+", tail)[-1].strip()
        tail = tail.strip(" .!-—,")
        words = tail.split()
        changed_signoff = None
        if 1 <= len(words) <= 3 and all(w[:1].isupper() for w in words) and tail.lower() not in STOP_CLOSINGS \
                and not re.search(r"\d", tail) and tail.lower() != name.lower():
            st["closing"] = tail
            if self.policy["sign_off"] != tail:
                self.set_policy("sign_off", tail)
                changed_signoff = tail
        n = len(re.findall(r"[.!?](\s|$)", body)) or 1
        st["sentences"] = max(1, round((st["sentences"] + n) / 2)) if st.get("sentences") else n
        st["samples"] = st.get("samples", 0) + 1
        STYLE.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
        return changed_signoff

    def greeting_for(self, rec):
        g = (self.policy.get("greeting") or self.style.get("greeting") or "Hi {name},").strip()
        name = self.first_name(rec)
        if name:
            return g.replace("{name}", name) if "{name}" in g else g
        g = re.sub(r"\s*\{name\}", "", g)                                # "Ciao {name}!" → "Ciao!"
        return g if re.search(r"[,!.:]$", g) else g + ","

    def policy_text(self, product=False):
        """The store policy as the reply writer sees it. Where the shop's own pages cover a topic (shipping, returns,
        where we ship) they take precedence over the generic defaults, so the writer is not given two different figures."""
        out = []
        sf = self.shopfacts
        for k, v in self.policy.items():
            if k in ("sign_off", "greeting"):
                continue
            if k == "ships_to" and not v:
                if sf and sf.covers("where we ship"):
                    out.append("ships_to: only what the FACTS FROM THE SHOP'S OWN WEBSITE below say")
                else:
                    out.append("ships_to: UNKNOWN — never state which countries we ship to; say the owner will confirm")
            elif k == "products" and not v:
                if product:
                    out.append("products: only what THE PRODUCT PAGE below says — nothing else")
                else:
                    out.append("products: NO PRODUCT FACTS AVAILABLE — never state specifications, materials, sizes or battery life")
            elif k == "shipping" and v == DEFAULT_POLICY["shipping"] and sf and (sf.covers("delivery time") or sf.covers("shipping cost")):
                out.append("shipping: exactly as the FACTS FROM THE SHOP'S OWN WEBSITE below say (times and costs per destination); tracking number sent by email when the parcel ships")
            elif k == "returns" and v == DEFAULT_POLICY["returns"] and sf and sf.covers("returns & refunds"):
                out.append("returns: exactly as the FACTS FROM THE SHOP'S OWN WEBSITE below say")
            else:
                out.append(f"{k}: {v}")
        return "\n".join(out)

    # ---- messages ------------------------------------------------------------
    def add(self, channel, sender, text, subject="", ref=None, extra=None):
        existing = {r["id"] for r in _load(INBOX)}
        base = int(_dt.datetime.now().timestamp() * 1000) % 10 ** 8
        mid = ref or str(base)
        while mid in existing:
            base += 1
            mid = str(base)
        rec = {"id": mid, "t": now(), "channel": channel,
               "from": sender, "subject": subject, "text": text.strip(), "status": "new"}
        if extra:                                   # channel details needed to reply (address, message-id, conversation) — never shown to the model
            rec.update({k: v for k, v in extra.items() if k not in rec})
        _append(INBOX, rec)
        return rec

    def items(self, status=None):
        rows = _load(INBOX)
        st = {}
        for d in _load(DECISIONS):
            st[d["id"]] = d["decision"]
        out = []
        for r in rows:
            r["status"] = st.get(r["id"], "new")
            if status is None or r["status"] == status:
                out.append(r)
        return out

    def get(self, mid):
        return next((r for r in self.items() if r["id"] == mid), None)

    # ---- understanding + drafting ----------------------------------------------
    def classify(self, text):
        low = text.lower()
        quick = None
        if re.search(r"\b(where is|where's|track|tracking|hasn't arrived|not arrived|still waiting|when will .* arrive|delivery status)\b", low):
            quick = "where_is_my_order"
        elif re.search(r"\b(broken|damaged|crack(ed|s)?|chip(ped|s)?|dent(ed|s)?|scratch(ed|es)?|torn|leak(ing|s)?|shattered|smashed|arrived with a|arrived (broken|damaged)|wrong (item|size|colou?r|product|model)|missing (part|item|piece)|(piece|part|item) (is )?missing|is missing|doesn't work|does not work|not working|defective|faulty|came empty|box was open|package (was )?empty|nothing inside)\b", low):
            quick = "damaged_or_wrong"
        elif re.search(r"\b(return|refund|money back|send it back)\b", low):
            quick = "return_or_refund"
        elif re.search(r"\b(cancel|change (my|the) (order|address|colou?r|size|model|delivery address|shipping address)|change (the )?(colou?r|size|model|address) (on|of|for) (my |the )?order|update .* address|(different|another|wrong) (address|colou?r|size)( on| for| in)? (my |the )?order|before it ships)\b", low):
            quick = "cancel_or_change"
        elif re.search(r"\b(discount|coupon|promo code|voucher|cheaper|\d+ ?% off|price match|bulk price)\b", low):
            quick = "discount_request"
        elif re.search(r"\b(physical (shop|store)|showroom|visit (your|the) (shop|store)|opening hours|where are you (based|located)|which country are you)\b", low):
            quick = "other"
        elif re.search(r"\b(collab\w*|influencer|sponsor\w*|followers|press|journalist|partnership|wholesale (inquiry|enquiry|order))\b", low):
            quick = "partnership_or_press"
        elif re.search(r"\b(seo services|guaranteed ranking|first page of google|crypto|bitcoin|earn \$|click here|verify your account|suspended)\b", low):
            quick = "spam_or_scam"
        elif re.search(r"\b(do you ship|ship to|shipping to|how long does|is it|does it|can it|what (size|material|colou?rs?)|how (big|heavy|many)|battery|compatible|waterproof|dimensions|in stock|available)\b", low) and "?" in text:
            quick = "product_question"
        elif re.search(r"\b(love|great|amazing|best purchase|thank you so much|thanks!)\b", low) and not re.search(r"\b(but|however|unfortunately|broken|late)\b", low):
            quick = "compliment"
        if quick == "damaged_or_wrong" and re.search(r"\bcancel", low) and not re.search(r"\b(broken|damaged|crack|chip|dent|scratch|torn|leak|shatter|smash|defective|faulty|missing|doesn't work|does not work|not working|empty|nothing inside)", low):
            quick = "cancel_or_change"                                    # "cancel it, I ordered the wrong model" is a cancellation, not a damage report
        escalate = bool(re.search(r"\b(lawyer|attorney|legal action|sue|chargeback|dispute with my bank|injur|hurt|burn|fire|rash|allerg|gdpr|delete my data|personal data)\b", low))
        needs = []
        if quick in ("where_is_my_order", "return_or_refund", "damaged_or_wrong", "cancel_or_change") and not re.search(r"#?\b\d{4,}\b", text):
            needs.append("order number")
        if quick == "damaged_or_wrong" and not re.search(r"\b(photo|picture|attached|image)\b", low):
            needs.append("photo of the damage")
        mo = re.search(r"(?:order|#|no\.?|number)\s*#?\s*(\d{4,})|\b(\d{5,})\b", text, re.I)
        order_no = (mo.group(1) or mo.group(2)) if mo else ""
        result = {"kind": quick or "other", "urgency": "high" if escalate or quick == "damaged_or_wrong" else "normal", "needs": needs, "escalate": escalate, "order_no": order_no}
        if quick is None and self.planner and self.planner.installed():
            try:
                raw = self.planner.chat("You classify customer messages. Output JSON only.", CLASSIFY_PROMPT + json.dumps(text[:1200]), max_tokens=80, stop=["\n\n"])
                j = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
                if j.get("kind") in KINDS:
                    result["kind"] = j["kind"]
                result["urgency"] = j.get("urgency", result["urgency"]) if j.get("urgency") in ("low", "normal", "high") else result["urgency"]
                result["needs"] = list(dict.fromkeys(result["needs"] + [str(n) for n in j.get("needs", [])][:3]))
                if j.get("escalate") and re.search(r"\b(lawyer|legal|chargeback|bank|injur|hurt|rash|allerg|data|police|report|fraud|scam)\b", low):
                    result["escalate"] = True
            except Exception as e:
                self.log("classify_fallback", error=str(e)[:80])
        return result

    def draft(self, rec):
        """Draft a reply for one inbox record → dict(kind, urgency, escalate, needs, text, checks)."""
        c = self.classify(rec["text"])
        c["text"] = rec["text"]
        if c["kind"] == "spam_or_scam":
            return {**c, "text": "", "checks": [], "note": "no reply (spam)"}
        if c["escalate"] or c["kind"] == "partnership_or_press":
            hold = self._sanitize("Thank you for your message. I am passing it to the owner personally, who will get back to you within one business day.", rec)
            return {**c, "text": hold, "checks": [], "note": "holding reply only — owner must handle this one"}
        facts = ""
        order = None
        if self.store is not None and rec.get("channel") == "store" and not c.get("order_no") and c["kind"] in ("where_is_my_order", "cancel_or_change", "return_or_refund", "damaged_or_wrong"):
            mine = self.store.orders_for(rec.get("from"))                  # no number given, but the address is a customer's: use their open order
            live = [o for o in mine if o["status"] in ("paid", "shipped", "delivered")]
            if len(live) == 1 or (live and c["kind"] == "where_is_my_order" and len([o for o in live if o["status"] != "delivered"]) == 1):
                pick = live[0] if len(live) == 1 else next(o for o in live if o["status"] != "delivered")
                c["order_no"] = str(pick["n"]); c["order_by_email"] = True
            elif len(live) > 1:
                c["order_choices"] = [f"#{o['n']} ({', '.join(l['name'] for l in o['lines'])}, {o['status']})" for o in live[:4]]
                c["needs"] = [n for n in c["needs"] if "order" not in n.lower()]
            elif not mine:
                c["order_none"] = True                                          # nobody with this address ever ordered here
        if self.store is not None and rec.get("channel") == "store" and c.get("order_no"):
            order = self.store.order_facts(c["order_no"], email=rec.get("from"))
            if order is None:
                c["order_missing"] = True
            if order:
                c["order"] = {k: v for k, v in order.items() if k != "order"}
                c["needs"] = [n for n in c["needs"] if "order" not in n.lower()]
                if order.get("late") and c["kind"] == "where_is_my_order":
                    self.store.proposal_for_message("where_is_my_order", c["order_no"])   # the owner gets a 'ship it today' proposal
        shop = self.shopfacts.prompt_block(rec["text"]) if self.shopfacts else ""
        prod = self.shopfacts.product_block(rec["text"]) if (self.shopfacts and c["kind"] in ("product_question", "other", "compliment")) else ""
        if prod:
            c["product"] = self.shopfacts.match_products(rec["text"])[0]["name"]
            c["needs"] = [n for n in c["needs"] if not re.search(r"product|item|model|which", n.lower())]
            c["contradiction"] = self.shopfacts.contradiction(rec["text"], self.shopfacts.match_products(rec["text"])[0])
            c["unmentioned"] = self.shopfacts.unmentioned(rec["text"], self.shopfacts.match_products(rec["text"])[0]) if c["kind"] != "compliment" else []
            if self.store is not None and rec.get("channel") == "store" and re.search(r"\b(in stock|stock|availability|sold out|restock|back in|still available|available (again|now|to order)|is it available|are they available)\b", rec["text"].lower()) \
                    and not re.search(r"\b(available|come|comes) in (other|different|more|which|what|any)\b", rec["text"].lower()):
                sp = self.store.find_product(c["product"])                 # our own shop: the live stock figure is known
                if sp and sp["name"] == c["product"]:
                    c["stock"] = int(sp["stock"])
                    c["unmentioned"] = [w for w in c["unmentioned"] if w not in ("stock", "restock", "availability", "available")]
                    prod += (f"\nLIVE STOCK (from the shop's own system, more current than the page): {sp['name']}: "
                             + (f"{sp['stock']} unit(s) in stock — orders leave within 1 business day." if sp["stock"] > 0 else "SOLD OUT right now — do not promise a date; say you will ask the owner when it is back."))
        ship_check = ""
        if self.store is not None and rec.get("channel") == "store" and c["kind"] in ("product_question", "other") and \
                re.search(r"\b(ship|ships|shipping|deliver|delivery|deliveries|send|sending|post|spedi\w*|consegn\w*|livr\w*|liefer\w*|verzend\w*)\b|\b(live|living|based|i'?m|i am|located) in\b.{0,30}\b(order|buy|purchase|get)\b|\b(order|buy|purchase) (?:from|to|in) [A-Z]", rec["text"], re.I):
            code, cname = country_in(rec["text"])                          # "do you ship to Switzerland?" → the shipping table decides, not the model
            if code:
                try:
                    cost = self.store.shipping_for(code, 0)
                except Exception:
                    cost = None
                rule = next((r for r in self.store.ship_rules() if r[0] == code), None) or (next((r for r in self.store.ship_rules() if r[0] == "EU"), None) if cost is not None else None)
                c["ship_to"] = {"code": code, "name": cname, "offered": cost is not None, "cost": cost, "free_over": (rule[2] if rule else None),
                                "days": SHIP_DAYS.get(code, "5–7")}
                if cost is None:
                    ship_check = f"\nSHIPPING CHECK (from the shop's own shipping table): we do NOT deliver to {cname} — only to EU countries. Say so plainly; do not promise a date or a workaround."
                else:
                    ship_check = (f"\nSHIPPING CHECK (from the shop's own shipping table): we DO deliver to {cname}: € {cost:.2f}".replace(".", ",") +
                                  (f" (free over € {rule[2]:.2f})".replace(".", ",") if rule and rule[2] else "") + f", {SHIP_DAYS.get(code, '5–7')} business days after dispatch; orders leave within 1 business day.")
                other_q = rec["text"].count("?") > 1 or bool(re.search(r"\b(also|and (?:is|does|do|can|how|what|which)|another question|second question)\b", rec["text"].lower()))
                if not other_q and not c.get("stock") and not c.get("contradiction"):
                    text = self._sanitize(self._template(c), rec)       # a plain 'do you ship to X?' → the table's answer, word for word
                    c["note"] = "answered from the shipping table"
                    return {**c, "text": self._with_notice(text, rec), "checks": []}
        if c["kind"] == "product_question":
            about_shipping = bool(re.search(r"\b(ship|deliver|delivery|shipping)\b", rec["text"].lower()))
            have = (self.policy.get("ships_to") if about_shipping else self.policy.get("products")) or ""
            if not have.strip() and about_shipping and (shop or ship_check):   # the shop's own shipping page / table answers it
                have = "see the facts from the shop's website below"
            if not have.strip() and prod:                                  # the product's own page answers it
                have = "see the product page from the shop's website below"
            if not have.strip():                                            # nothing to answer from → defer, never guess
                text = self._sanitize(self._template(c), rec)
                c["note"] = ("no product/shipping facts in the policy — deferring to the owner (set them with /policy" +
                             (" or let me read your shop's pages with /shop <address>)" if not (self.shopfacts and self.shopfacts.url) else ")"))
                return {**c, "text": self._with_notice(text, rec), "checks": []}
            facts = have
        if shop:
            c["shop_facts"] = shop.count("\n- ")
            if not re.search(r"\b(my order|ordered|i bought|purchase[d]?|parcel|package|my package|order \d|ordine|pacco|comprato|acquist|commande|bestell|colis|pakket)\b", rec["text"].lower()):
                c["needs"] = [n for n in c["needs"] if "order" not in n.lower()]    # a general question: no order to ask about
        needs = ("\nMISSING FACTS you must ask the customer for: " + ", ".join(c["needs"])) if c["needs"] else ""
        if c["kind"] == "discount_request":
            live = self._live_code()
            if live:
                c["live_code"] = live["code"]
                needs += f"\nTHIS IS A DISCOUNT REQUEST: the shop has a public code right now — tell the customer to enter the code {live['code']} at checkout ({self._code_words(live)}). Do not invent any other discount. Do not ask for an order number."
            else:
                needs += "\nTHIS IS A DISCOUNT REQUEST: state the discount policy plainly (no codes in chat; newsletter subscribers get 10% on the first order). Do not ask for an order number. Do not say 'sure' or 'I can help with that'."
        if c["kind"] == "return_or_refund" and re.search(r"\bafter \d+ (days?|weeks?|months?)|\d+ (days?|weeks?) ago|too late|still return|ancora (restituire|rendere)\b", rec["text"].lower()):
            c["asks_window"] = True
            needs += ("\nTHE CUSTOMER ASKS ABOUT THE RETURN WINDOW: first state the window explicitly, with the number of days from the returns policy / shop facts "
                      "(and who pays the return shipping if asked), then what happens next. Do not say 'of course' and do not repeat the customer's question.")
        if shop and "?" in rec["text"]:
            needs += "\nTHE CUSTOMER ASKS A QUESTION THAT THE SHOP FACTS BELOW ANSWER: answer it first, plainly, with the exact figures (cost, days, who pays, where); only after that ask for anything else."
        if order and not order.get("mismatch"):
            needs += ("\nYOU DO HAVE THIS ORDER IN FRONT OF YOU (from the shop's own order system) — ignore the rule about not having access to orders "
                      "for THIS order only. Tell the customer its real status in plain words, with the tracking number if there is one. "
                      "Never invent a delivery date. If it is not shipped yet, say it is still in the warehouse and leaves within 1 business day; "
                      "if the customer wants to cancel and it is not shipped, say it will be cancelled and refunded in full (the owner confirms); "
                      "if the customer wants to CHANGE something (colour, size, model, address) and it is not shipped, say the change is possible and ask exactly what it should be — do not mention cancelling; "
                      "if it is shipped, say it cannot be cancelled or changed any more but can be returned within 30 days of delivery.\nORDER FACTS:\n- " + "\n- ".join(order["lines"]))
        elif order and order.get("mismatch"):
            needs += "\nORDER CHECK: " + order["lines"][0] + " Do not reveal anything about the order."
        elif c.get("order_missing"):
            needs += f"\nORDER CHECK: there is NO order {c['order_no']} in the shop's order system — the number is probably mistyped. Ask the customer to check it on the order confirmation e-mail; do not guess about the parcel."
        elif c.get("order_choices"):
            needs += "\nORDER CHECK: this customer has several orders (" + "; ".join(c["order_choices"]) + ") — ask which one they mean."
        elif c.get("order_none"):
            needs += "\nORDER CHECK: the order system has NO order under this e-mail address — ask for the order number (it starts with 51) or to write from the address used at checkout; do not guess about any parcel."
        if prod and c["kind"] != "product_question":
            needs += f"\nThe product is known: {c['product']} (its page is below). Never ask which product the customer means."
        if prod and "?" in rec["text"]:
            needs += ("\nTHE CUSTOMER ASKS ABOUT A PRODUCT WHOSE PAGE IS BELOW: answer each part of the question from the page, with its exact words and figures. "
                      "If the page lists what is included, not included, or which models/options exist, state that plainly (a 'no' is a fine answer). "
                      "If the page does not mention the thing asked, say that you will check it with the owner.")
            needs += f"\nThe product is known: {c['product']}. Never ask which product the customer means."
            if c.get("contradiction"):
                needs += f"\nTHE PAGE SAYS NO to part of this question — its exact words: \"{c['contradiction']}\". The answer to that part is no; say so and do not offer it."
            if c.get("unmentioned"):
                needs += (f"\nTHE PAGE DOES NOT MENTION: {', '.join(c['unmentioned'][:4])}. Do not say yes or no about " +
                          ("that" if len(c["unmentioned"]) == 1 else "those") + " — write that you will check it with the owner and answer within one business day.")
        extra = (f"\nBACKGROUND FACTS you may use (do not quote sources): \n{facts}" if facts else "") + shop + prod + ship_check
        if self.style.get("sentences"):
            extra += f"\nLENGTH: the owner prefers about {self.style['sentences']} sentence(s)."
        text = None
        if self.planner and self.planner.installed():
            try:
                text = self.planner.chat("You are the customer-care writer of a small online store.",
                                         DRAFT_PROMPT % (self.policy_text(product=bool(prod)) + needs + extra, c["kind"].replace("_", " "), rec.get("from", "customer"), rec["text"][:1500]),
                                         max_tokens=260, temperature=0.2, timeout=240)
            except Exception as e:
                self.log("draft_failed", error=str(e)[:100])
        if not text:
            text = self._template(c)
        text = self._sanitize(text, rec)
        if not self._is_reply(text, rec):                                  # chatter, an echo of the question, or nothing → template
            text = self._sanitize(self._template(c), rec)
        checks = self._check(text, c, rec["text"])
        if checks and self.planner and self.planner.installed():
            try:                                                           # one repair round with the problems spelled out
                fixed = self.planner.chat("You are the customer-care writer of a small online store.",
                                          DRAFT_PROMPT % (self.policy_text(product=bool(prod)) + needs + extra, c["kind"].replace("_", " "), rec.get("from", "customer"), rec["text"][:1500])
                                          + f"\n\nYour previous draft was rejected because it: {'; '.join(checks)}. Write a corrected reply.",
                                          max_tokens=260, temperature=0.2, timeout=240)
                fixed = self._sanitize(fixed, rec)
                if self._is_reply(fixed, rec) and len(self._check(fixed, c, rec["text"])) < len(checks):
                    text, checks = fixed, self._check(fixed, c, rec["text"])
            except Exception:
                pass
        if checks:                                                          # still unsafe → the plain template (always policy-true)
            tmpl = self._sanitize(self._template(c), rec)
            if not self._check(tmpl, c, rec["text"]):
                c["rejected"] = {"text": text, "checks": checks}
                text, checks = tmpl, []
                c["note"] = "model draft failed the checks; using the safe template"
        return {**c, "text": self._with_notice(text, rec), "checks": checks}

    def _with_notice(self, text, rec):
        """A shop notice (holiday pause etc.) is repeated just above the sign-off of every store reply while it is up."""
        try:
            nt = self.store.notice() if (self.store is not None and (rec or {}).get("channel") == "store") else {}
            if not text or not nt.get("text") or nt["text"].lower()[:30] in text.lower():
                return text
            note = f"Please note: {nt['text'].rstrip('.')}."
            if re.match(r"^(Grazie|Buongiorno|Salve|Gentile)", text.split("\n\n", 1)[-1]):
                note = f"Nota: {nt['text'].rstrip('.')}."
            parts = text.rstrip().rsplit("\n\n", 1)
            return (parts[0] + "\n\n" + note + "\n\n" + parts[1]) if len(parts) == 2 else text.rstrip() + "\n\n" + note
        except Exception:
            return text

    def _live_code(self):
        """The public discount code customers may be told about (active, not exhausted), or None."""
        try:
            if self.store is None:
                return None
            for x in self.store.codes():
                if x.get("active") and not (x.get("max_uses") and x.get("uses", 0) >= x["max_uses"]):
                    return x
        except Exception:
            pass
        return None

    @staticmethod
    def _code_words(x):
        if not x:
            return ""
        pct, fixed, mn = float(x.get("pct", 0) or 0), float(x.get("fixed", 0) or 0), float(x.get("min", 0) or 0)
        w = f"{pct:g}% off" if pct else f"€{fixed:.2f} off"
        return w + (f" on orders over €{mn:.2f}" if mn else "")

    def _template(self, c):
        p = self.policy
        if c.get("ship_to"):
            st = c["ship_to"]
            if re.search(r"\b(spedite|spedizion\w*|consegn\w*|quanto costa|in italia|arriva)\b", c.get("text", "").lower()):
                it_names = {"Switzerland": "Svizzera", "the UK": "Regno Unito", "the USA": "Stati Uniti", "Germany": "Germania", "France": "Francia", "Spain": "Spagna", "Italy": "Italia", "Austria": "Austria", "the Netherlands": "Paesi Bassi", "Belgium": "Belgio", "Portugal": "Portogallo"}
                nm = it_names.get(st["name"], st["name"])
                if not st["offered"]:
                    return (f"Grazie per la domanda. Al momento spediamo solo all'interno dell'Unione Europea, quindi purtroppo non possiamo ancora spedire in {nm}. "
                            "Segnalo il suo interesse al titolare: se cambierà, lo annunceremo nella pagina Spedizioni. Mi dispiace non avere notizie migliori.")
                cost = ("gratuita" if st["cost"] == 0 else f"€ {st['cost']:.2f}".replace(".", ","))
                return (f"Grazie per la domanda. Sì, spediamo in {nm}: la spedizione costa {cost}" +
                        (f" (gratuita per ordini sopra € {st['free_over']:.2f})".replace(".", ",") if st.get("free_over") else "") +
                        f" e la consegna richiede {st['days']} giorni lavorativi dalla partenza — gli ordini partono dal nostro magazzino entro 1 giorno lavorativo. Resto a disposizione per qualsiasi altra domanda.")
            if not st["offered"]:
                return (f"Thank you for your question. At the moment we deliver only within the EU, so unfortunately we cannot ship to {st['name']} yet. "
                        "I will pass your interest on to the owner — if that changes, it will be announced on our shipping page. Sorry not to have better news.")
            cost = ("free" if st["cost"] == 0 else f"€ {st['cost']:.2f}".replace(".", ","))
            return (f"Thank you for your question. Yes, we deliver to {st['name']}: shipping is {cost}" +
                    (f" (free for orders over € {st['free_over']:.2f})".replace(".", ",") if st.get("free_over") else "") +
                    f", and delivery takes {st['days']} business days after dispatch — orders leave our warehouse within 1 business day. Just write back if you need anything else.")
        if c.get("stock") is not None and c.get("product"):
            if c["stock"] > 0:
                return (f"Thank you for your question. The {c['product']} is in stock right now — {c['stock']} unit{'s' if c['stock'] != 1 else ''} available — "
                        "and orders leave our warehouse within 1 business day. Just write back if you need anything else.")
            return (f"Thank you for your question. The {c['product']} is sold out at the moment. I will ask the owner when it will be back "
                    "and let you know within one business day.")
        if c["kind"] in ("product_question", "other") and c.get("product") and self.shopfacts:
            prods = [x for x in self.shopfacts.products if x["name"] == c["product"]]
            if prods and re.search(r"\b(other|different|more|which|what) (colou?rs?|sizes?|models?|versions?|options?|variants?)\b|\b(colou?rs?|sizes?|models?) (available|do you have|does it come)", c.get("text", "").lower()):
                axis = re.search(r"\b(colou?rs?|sizes?|models?|versions?|options?|variants?)\b", c.get("text", "").lower()).group(1)
                axes = {"colour": "colour|color", "color": "colour|color", "colours": "colour|color", "colors": "colour|color", "size": "size", "sizes": "size", "model": "model|for", "models": "model|for"}.get(axis, "")
                opts = [", ".join(o.split(": ", 1)[-1] for o in v) for v in prods[0].get("variants", [])]
                names = [v[0].split(": ", 1)[0].lower() if ": " in v[0] else "options" for v in prods[0].get("variants", [])]
                if opts:
                    same = [o for o, n in zip(opts, names) if axes and re.search(axes, n)]
                    if same:
                        return f"Thank you for your question. The {c['product']} comes in these options: {same[0]}. Just tell me which one you would like."
                    return (f"Thank you for your question. The {c['product']} comes in one {axis.rstrip('s') if axis.endswith('s') else axis} only — the choice on the page is "
                            f"{names[0]}: {opts[0]}. If you would like another {axis.rstrip('s') if axis.endswith('s') else axis}, I will ask the owner whether one is planned.")
                return (f"Thank you for your question. The {c['product']} is currently offered in one version only (no other {axis} on the page). "
                        "If you would like another one, I will ask the owner whether it is planned and let you know within one business day.")
            line = c.get("contradiction") or (self.shopfacts.best_detail(c.get("text", ""), prods[0]) if prods else "")
            if line and not c.get("unmentioned"):
                return (f"Thank you for your question about the {c['product']}. Our product page says: \"{line}\". "
                        "I hope this helps — just write back if you need anything else.")
            if line:
                return (f"Thank you for your question about the {c['product']}. Our product page says: \"{line}\" but does not mention "
                        f"{' or '.join(c['unmentioned'][:2])}, so I will check that with the owner and come back to you within one business day.")
            return (f"Thank you for your question about the {c['product']}. Our product page does not mention "
                    f"{' or '.join(c['unmentioned'][:2]) if c.get('unmentioned') else 'that'}, so I will check it with the owner and come back to you within one business day.")
        o = f" {c['order_no']}" if c.get("order_no") else ""
        od = c.get("order") or {}
        if c.get("order_missing"):
            return (f"Thank you for your message. I cannot find an order{o} in our system — could you check the number on your order confirmation e-mail "
                    "(it starts with 51) and send it to me again? Then I will help straight away.")
        if c.get("order_choices"):
            return ("Thank you for your message. I see several orders under your e-mail address — " + "; ".join(c["order_choices"]) +
                    " — which one do you mean? Then I will help straight away.")
        if c.get("order_none"):
            return ("Thank you for your message. I cannot find any order under this e-mail address — could you send me your order number "
                    "(it starts with 51, on your order confirmation e-mail), or write from the address you used at checkout? Then I will help straight away.")
        if od.get("mismatch"):
            return (f"Thank you for your message. For your security I can only discuss order{o} with the e-mail address it was placed with — "
                    "could you write to me from that address, or forward me the order confirmation? Then I will help straight away.")
        if od and not od.get("mismatch") and c["kind"] in ("where_is_my_order", "cancel_or_change", "return_or_refund", "damaged_or_wrong"):
            st, trk = od.get("status"), od.get("tracking") or ""
            if c["kind"] == "where_is_my_order":
                if st == "paid" and od.get("late"):
                    return (f"I am sorry — your order{o} has not left our warehouse yet, which is later than the 1 business day we promise. The owner has been asked to ship it today; "
                            "you will receive the GLS tracking number by e-mail the moment it leaves. If you would rather not wait, tell me and it will be cancelled and refunded in full.")
                if st == "paid":
                    return f"Thank you for your message. Your order{o} is still in our warehouse and leaves within 1 business day; you will receive the GLS tracking number by e-mail the moment it ships."
                if st == "delivered":
                    return (f"Thank you for your message. According to GLS, order{o} has been delivered (tracking number {trk}). If it has not reached you, please check with neighbours or your building's reception, "
                            "and write back — I will open an enquiry with the carrier straight away.")
                if st == "shipped":
                    return f"Thank you for your message. Your order{o} was shipped with GLS — tracking number {trk}. If the tracking does not move for more than 3 business days, write to me again and I will open an enquiry with the carrier."
                if st in ("cancelled", "refunded"):
                    return f"Order{o} was {st} and the amount refunded; if you do not see the refund on your statement within 5 business days, please tell me."
            if c["kind"] == "damaged_or_wrong" and st in ("shipped", "delivered"):
                photo = "photo of the damage" in c["needs"]
                missing = bool(re.search(r"\bmissing\b|came empty|nothing inside", (c.get("text") or "").lower()))
                return (f"I am so sorry — order{o} should not have arrived like that. " +
                        (("Could you send me a photo of what you received? As soon as I have it, " if missing else "Could you send me a photo of the damage? As soon as I have it, ") if photo else "") +
                        "the owner will confirm a replacement or a full refund for you — there is no need to send the item back until we tell you. "
                        "You will hear from me within one business day.")
            if c["kind"] == "return_or_refund" and st in ("shipped", "delivered"):
                return (f"Thank you for your message. Order{o} can be returned within 30 days of delivery as long as it is unused; return shipping costs € 4,90 "
                        "unless the item was faulty or wrong, and the refund is issued within 5 business days after it arrives. Tell me and I will send you the return instructions.")
            if c["kind"] == "cancel_or_change" and not re.search(r"\bcancel", (c.get("text") or "").lower()):
                what = re.search(r"\b(delivery address|shipping address|colou?r|size|model|address|quantity)\b", (c.get("text") or "").lower())
                what = what.group(1) if what else "order"
                if st == "paid":
                    return (f"Thank you for your message. Order{o} has not left the warehouse yet, so the {what} can still be changed — tell me exactly what it should be "
                            "and the owner will update the order before it ships; you will get a confirmation by e-mail.")
                if st in ("shipped", "delivered"):
                    return (f"Order{o} has already been shipped (tracking {trk}), so the {what} cannot be changed any more. " +
                            ("You can return it within 30 days of delivery and order the one you want — return shipping costs € 4,90 unless the item was faulty or wrong."
                             if "address" not in what else "If the parcel cannot be delivered, GLS returns it to us and I will re-send it to the right address or refund you."))
            if c["kind"] == "cancel_or_change":
                if st == "paid":
                    return f"Thank you for letting me know. Order{o} has not left the warehouse yet, so it can be cancelled and refunded in full — I have passed it to the owner to confirm, and you will receive the confirmation shortly."
                if st in ("shipped", "delivered"):
                    return f"Order{o} has already been shipped (tracking {trk}), so it cannot be cancelled any more; you can return it within 30 days of delivery — return shipping costs € 4,90 unless the item was faulty or wrong — and I will refund it within 5 business days after it arrives."
        body = {
            "where_is_my_order": "Thank you for reaching out, and sorry for the wait. " + (f"{self.shopfacts.best_sentence('how long does delivery take').rstrip('.')}. " if self.shopfacts and self.shopfacts.covers("delivery time") else f"Standard delivery takes {p['shipping'].split(';')[0].replace('standard delivery ', '')}. ") + f"I will check your order{o} and send you the tracking details within one business day" + ("." if not c["needs"] else " — could you send me your order number first?"),
            "return_or_refund": f"Thank you for your message. Our returns policy: {(self.shopfacts.best_sentence('return refund') if self.shopfacts and self.shopfacts.covers('returns & refunds') else p['returns']).rstrip('.')}. {p['refunds'].split(';')[0].capitalize()}. " + (f"I will start the return for order{o} and send you the instructions within one business day." if o else "Please send me your order number and I will start the return for you."),
            "damaged_or_wrong": f"I am sorry your order{o} did not arrive as it should. " + ("Please send me " + " and ".join(("your " + n) if n == "order number" else "a " + n for n in c["needs"]) + ", and I will sort out a replacement or refund straight away." if c["needs"] else "I will sort out a replacement or refund straight away and confirm the details within one business day."),
            "cancel_or_change": f"Thank you for letting me know. I will check whether your order{o} has already left the warehouse: if not, it will be cancelled and refunded; if it has, I will send you the return options. You will hear from me within one business day" + ("." if not c["needs"] else " — please send me your order number first."),
            "discount_request": (f"Thank you for asking. Yes — enter the code {c['live_code']} at checkout and you get {self._code_words(self.store.code(c['live_code']))}." if c.get("live_code") and self.store is not None
                                 else f"Thank you for asking. {p['discounts'].split(';')[-1].strip().capitalize()}."),
            "product_question": "Thank you for your question. I want to give you a precise answer, so I will check this with the owner and come back to you within one business day.",
            "complaint": "I am sorry about your experience. Could you tell me a little more (and your order number, if you have one) so I can put this right?",
            "compliment": "Thank you so much, that made our day. Enjoy your order, and do get in touch any time.",
        }.get(c["kind"], "Thank you for your message. I will check this with the owner and come back to you within one business day.")
        return body

    def _is_reply(self, text, rec):
        """False when the 'reply' is meta-chatter ("here's the corrected reply"), the customer's own words, or empty."""
        body = text.split("\n\n", 1)[1] if "\n\n" in text else text
        body = body.replace(self.policy["sign_off"], "").strip()
        if len(re.sub(r"\s+", " ", body)) < 25 or re.search(r"\b(here's|here is) (the|a|my) (corrected|revised|new|updated) (reply|draft|version)|as an ai\b|i cannot (write|help)\b", body, re.I):
            return False
        q = re.sub(r"\W+", " ", (rec.get("text") or "").lower()).strip() if rec else ""
        b = re.sub(r"\W+", " ", body.lower()).strip()
        if q and (b == q or (len(b) < len(q) + 30 and q in b)):
            return False
        return True

    def _sanitize(self, text, rec=None):
        text = re.sub(r"\[[^\]]{1,40}\]", "", text)                       # placeholders like [tracking link]
        text = re.sub(r"!{2,}", "!", text)
        text = text.strip()
        m = GREET_RE.match(text)
        if m and m.group(4) != "":                                         # drop the model's own greeting line
            text = text[m.end():].strip()
        text = re.sub(r"^\s*(sure|certainly|of course|okay|ok)?[,!.]?\s*(here'?s|here is) (the|a|my|your) (corrected|revised|new|updated|improved)? ?(reply|draft|version|response)[^\n]*\n+", "", text, flags=re.I)
        if rec and rec.get("text"):                                        # drop the customer's question echoed back at them
            for sent in re.split(r"(?<=[.!?])\s+", rec["text"].strip()):
                sent = sent.strip()
                if len(sent) >= 12 and text.lower().startswith(sent.lower()):
                    text = text[len(sent):].lstrip(" \n-—:,")
            # ... also when the model turned "Can I still return…?" into "Can you still return…?" (echo in the second person)
            first_sent = re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=1)
            if first_sent and first_sent[0].endswith("?") and len(first_sent) > 1:
                qa = set(re.findall(r"[a-z]{4,}", first_sent[0].lower())) - {"your", "you", "still", "does", "have", "with", "that", "this", "what", "when", "where", "which"}
                qb = set(re.findall(r"[a-z]{4,}", rec["text"].lower()))
                if qa and len(qa & qb) >= max(2, int(0.6 * len(qa))):
                    text = first_sent[1].lstrip(" \n-—:,")
            if len(text) < 10:
                text = "Thank you for your message. I will check this with the owner and come back to you within one business day."
        lines = [l.rstrip() for l in text.splitlines()]
        first = self.policy["sign_off"].splitlines()[0].strip(" ,").lower()
        cut = len(lines)
        for i, l in enumerate(lines):                                      # drop any sign-off the model wrote
            ll = l.strip(" ,/").lower()
            if ll.startswith(("best regards", "kind regards", "regards", "sincerely", "warm regards", "best,", "cheers")) or ll == first:
                cut = i
                break
        body = "\n".join(lines[:cut]).strip()
        body = re.sub(r"\n{3,}", "\n\n", body)
        if body[:1].islower():
            body = body[0].upper() + body[1:]
        closing = self.style.get("closing", "").lower()
        if closing and body.lower().rstrip(" .!").endswith(" " + closing):   # "... latest. Carlo" → strip the copied closing
            body = body[: -len(closing)].rstrip(" .!,-—") + "."
        greet, sign = self.greeting_for(rec), self.policy["sign_off"]
        if re.match(r"^(Grazie|Buongiorno|Salve|Gentile)\b", body) and not self.policy.get("greeting") and sign == DEFAULT_POLICY["sign_off"]:
            greet = re.sub(r"^Hi\b", "Buongiorno", greet)                    # an Italian body gets Italian bookends (owner-set ones win)
            sign = "Cordiali saluti,\nIl servizio clienti"
        return greet + "\n\n" + body + "\n\n" + sign

    def _check(self, text, c, source=""):
        """Automatic safety checks on a draft — shown to the owner next to the Approve button."""
        low = text.lower()
        flags = []
        shop_nums = self.shopfacts.numbers() if self.shopfacts else set()
        shop_text = " ".join(f["text"] for f in self.shopfacts.facts).lower() if self.shopfacts else ""
        allowed = set(re.findall(r"\d{3,}", source or "")) | set(re.findall(r"\d{3,}", self.policy_text())) | {n for n in shop_nums if len(n) >= 3}
        if c.get("order") and not c["order"].get("mismatch"):
            allowed |= set(re.findall(r"\d{3,}", " ".join(c["order"]["lines"]) + " " + (c["order"].get("tracking") or "")))
        if c.get("order_choices"):
            allowed |= set(re.findall(r"\d{3,}", " ".join(c["order_choices"])))
        foreign = [n for n in set(re.findall(r"\d{3,}", text)) if n not in allowed]
        if foreign:
            flags.append(f"contains a number the customer never gave: {', '.join(foreign)}")
        if re.search(r"\b(i've|i have|we've|we have|i|we) (already |just )?(checked|contacted|spoken|called|looked into|escalated|forwarded|asked)\b", low):
            flags.append("claims to have already done something — nothing has been done yet")
        if c["kind"] == "cancel_or_change" and (c.get("order") or {}).get("status") != "cancelled" and \
                re.search(r"\b(has been|is now|was|has now been|is) cancel+ed\b|\b(i|we) (have |'ve )?(now )?cancel+ed\b|\bcancel+ed (it|your order) for you\b|\b(has been|is now|was) refunded\b", low):
            flags.append("says the order is already cancelled/refunded — only the owner can do that; it 'will be' cancelled once confirmed")
        if re.search(r"\b(full refund|refund(ed)?|replacement)\b", low) and c["kind"] not in ("damaged_or_wrong", "return_or_refund", "cancel_or_change") \
                and not (c.get("order") or {}).get("late") and not ((c.get("order") or {}).get("status") == "paid" and "cancel" in low):
            flags.append("promises a refund/replacement outside the return/damage cases")
        if re.search(r"\b\d{1,2}%\s*(off|discount)|\b(code|coupon)\s+[A-Z0-9]{4,}\b", text) and "newsletter" not in low and not (c.get("live_code") and c["live_code"].lower() in low):
            flags.append("offers a discount not in the policy")
        if re.search(r"\b(within|in) \d+ (hours?|days?)\b", low) and not re.search(r"one business day|5 business days|7-15 business days|30 days", low):
            spans = re.findall(r"\b(?:within|in) (\d+) (hours?|days?)\b", low)
            if not all(re.search(r"\b" + n + r"\s*(business |working )?" + u[:3], shop_text) for n, u in spans):
                flags.append("makes a time promise not in the policy")
        if re.search(r"\b(tomorrow|tonight|this week|next week|by (mon|tues|wednes|thurs|fri|satur|sun)day|refund today)\b", low):
            flags.append("promises a specific day — only the owner can do that")
        if re.search(r"\[[^\]]+\]|\bhere: *$|:\s*\.", text, re.M):
            flags.append("contains a placeholder or a dangling blank")
        if re.search(r"\b(find|here is|attached is) (the|your) tracking\b", low):
            flags.append("pretends to provide a tracking number")
        if c["kind"] == "damaged_or_wrong" and "tracking" in low:
            flags.append("talks about tracking in a damage case — the customer already has the parcel")
        if c["kind"] == "return_or_refund" and re.search(r"\bof course!?\b", low) and "30 days" not in low:
            flags.append("says 'of course' to a return without stating the 30-day window")
        if c.get("asks_window") and not re.search(r"\b\d+ days\b|\b\d+-day\b", low):
            flags.append("the customer asked whether a return is still possible — the reply must state the return window in days")
        if c.get("asks_window") and re.search(r"\b(sure|of course|certainly), i can help\b", low):
            flags.append("says 'sure, I can help' instead of answering the return-window question")
        if not (self.policy.get("ships_to") or "").strip() and re.search(r"\b(we|i) (do|don't|do not|can|cannot|can't)?\s*(ship|deliver) to\b", low) \
                and not (self.shopfacts and self.shopfacts.covers("where we ship")):
            flags.append("states a shipping destination that is not in the policy")
        if not (self.policy.get("products") or "").strip() and not c.get("product") and \
                re.search(r"\b(battery|hours|watt|waterproof|adjustable|made of|material|dimensions|cm\b|kg\b|grams?)\b", low) \
                and not re.search(r"\b(within|in) \d+ hours\b|\bopening hours\b|\bworking hours\b|\bbusiness hours\b|\b(answer|reply|respond)\w* (within|in) ", low):
            flags.append("invents product details")
        if self.shopfacts and self.shopfacts.facts:
            if re.search(r"\b(yes|certainly|absolutely|of course)\b[^.]{0,40}\b(we|i) (do )?(ship|deliver)\b|\bwe (do )?ship to (the )?(uk|united kingdom|switzerland|usa?|united states|canada|australia|norway|outside)", low) \
                    and re.search(r"\b(not yet|do not ship|don't ship|only (within|inside|to) (the )?(eu|europe|italy|italia)|non spediamo|solo in italia|nur innerhalb)\b", " ".join(f["text"] for f in self.shopfacts.facts).lower()) \
                    and re.search(r"\b(uk|united kingdom|england|london|scotland|switzerland|svizzera|usa?|united states|america|canada|australia|norway|outside the eu|non-eu)\b", (source or "").lower()):
                flags.append("says we ship to a country outside the shop's stated area — the shop page says not yet")
            shipping_days = re.findall(r"\b(\d+)\s*[-–]\s*(\d+) (business |working )?days\b", low)
            known = (" ".join(f["text"] for f in self.shopfacts.facts) + " " + self.policy_text()).lower()
            for a, b, _ in shipping_days:
                if not re.search(re.escape(a) + r"\s*[-–]\s*" + re.escape(b), known):
                    flags.append(f"states a delivery time that is on no shop page: {a}-{b} days")
                    break
            if re.search(r"\b7-15 business days\b", low) and "7-15" not in known.replace("–", "-").split("shipping: exactly")[0] and (self.shopfacts.covers("delivery time")):
                flags.append("uses the generic 7-15 days instead of the shop's own delivery times")
        if c.get("product"):
            prods = [x for x in self.shopfacts.products if x["name"] == c["product"]] if self.shopfacts else []
            page = " ".join([prods[0].get("text", "")] + prods[0]["details"] + [prods[0]["price"], prods[0].get("availability", "")] +
                            [v for vs in prods[0].get("variants", []) for v in vs]).lower() if prods else ""
            page_nums = set(re.findall(r"\d+(?:[.,]\d+)?", page)) | set(re.findall(r"\d+(?:[.,]\d+)?", source or "")) | set(re.findall(r"\d+(?:[.,]\d+)?", self.policy_text()))
            page_nums |= self.shopfacts.numbers() if self.shopfacts else set()
            if c.get("stock") is not None:
                page_nums.add(str(c["stock"]))                                  # the live stock figure is a true figure
            bad = [n for n in re.findall(r"\d+(?:[.,]\d+)?", text) if n not in page_nums and n.replace(",", ".") not in {x.replace(",", ".") for x in page_nums}]
            if bad:
                flags.append(f"states a figure that is not on the product page: {', '.join(sorted(set(bad)))}")
            unit = lambda u: {"grams": "g", "gram": "g", "hours": "h", "hour": "h", "watts": "w", "watt": "w", "pieces": "pcs", "piece": "pcs", "pz": "pcs", "litre": "l", "liter": "l"}.get(u, u)
            measures = re.findall(r"(\d+(?:[.,]\d+)?)\s*(grams?|g|kg|cm|mm|ml|l|hours?|h|mah|watts?|w|k|pcs|pieces?|pz|litres?|liters?)\b", low)
            known = page + " " + (" ".join(f["text"] for f in self.shopfacts.facts).lower() if self.shopfacts else "") + " " + self.policy_text().lower()
            page_measures = {(n.replace(",", "."), unit(u)) for n, u in re.findall(r"(\d+(?:[.,]\d+)?)\s*(grams?|g|kg|cm|mm|ml|l|hours?|h|mah|watts?|w|k|pcs|pieces?|pz|litres?|liters?)\b", known)}
            badm = [f"{n} {u}" for n, u in measures if (n.replace(",", "."), unit(u)) not in page_measures]
            if badm:
                flags.append(f"states a measurement that is not on the product page: {', '.join(badm)}")
            if c.get("contradiction") and re.search(r"\b(yes|certainly|absolutely|of course|it is compatible|is compatible|comes with|is included|does come)\b", low) \
                    and not re.search(r"\b(no|not|isn't|doesn't|does not|is not|without|unfortunately)\b", low):
                flags.append(f"says yes although the page says: {c['contradiction'][:80]}")
            if c.get("unmentioned") and not re.search(r"\b(owner|check|confirm|does not say|doesn't say|not mentioned|no information)\b", low):
                for w in c["unmentioned"]:
                    if re.search(r"\b" + re.escape(w[:5]), low):
                        flags.append(f"makes a claim about '{w}' which the product page never mentions — only 'I will check with the owner' is safe")
                        break
        if c.get("product") and self.shopfacts and re.search(r"\b(other|different|more) (colou?rs?)\b", (c.get("text") or "").lower()):
            prods = [x for x in self.shopfacts.products if x["name"] == c["product"]]
            has_colour = bool(prods) and any(re.search(r"colou?r", v[0].lower()) for v in prods[0].get("variants", []))
            if not has_colour and re.search(r"\b(yes|is available in (other|different|several|various) colou?rs|comes in (other|different|several|various) colou?rs)\b", low):
                flags.append("says other colours exist — the product page lists no colour options")
        if c.get("stock") is not None:
            if c["stock"] == 0 and re.search(r"\b(is|are|still|currently) (currently |still |now )?(in stock|available)\b|available for purchase", low):
                flags.append("says it is in stock — the shop's own system says it is sold out")
            if c["stock"] > 0 and re.search(r"\b(out of stock|sold out|not available|unavailable|no longer available)\b", low):
                flags.append(f"says it is sold out — the shop's own system has {c['stock']} in stock")
        if (c.get("order_missing") or c.get("order_none")) and re.search(r"\b(has (been )?shipped|is on its way|in (the|our) warehouse|tracking number is|will arrive)\b", low):
            flags.append("talks about the parcel although no such order exists in the order system")
        od = c.get("order") or {}
        if od.get("mismatch") and re.search(r"\b(shipped|warehouse|tracking|delivered|cancel+ed|refunded|gls)\b", low):
            flags.append("reveals order details to an e-mail address that did not place the order")
        if od and not od.get("mismatch"):
            st = od.get("status", "")
            if st == "paid" and re.search(r"\b(has (been )?shipped|is on its way|has been dispatched|has left|was shipped|delivered)\b", low):
                flags.append("says the order shipped — the order system says it is still in the warehouse")
            if st in ("shipped", "delivered") and re.search(r"\b(not (yet )?(been )?shipped|still in (the|our) warehouse|has not left|will be cancelled|cancelled and refunded)\b", low):
                flags.append(f"contradicts the order system (order is {st})")
            if od.get("tracking") and st in ("shipped", "delivered") and od["tracking"].lower() not in low and c["kind"] in ("where_is_my_order",):
                flags.append("does not give the tracking number that the order system has")
            if re.search(r"\b(arrive|delivered|be there|with you) (on|by) (monday|tuesday|wednesday|thursday|friday|saturday|sunday|tomorrow|\d)", low):
                flags.append("invents a delivery date")
            if re.search(r"\b(i|we) (will|'ll) (check|look into|verify|investigate)( on| the status of| whether| if)? (your |the )?order\b", low):
                flags.append("says it will check the order — its status is already known from the order system")
            if c["kind"] == "where_is_my_order" and st == "paid" and not re.search(r"warehouse|not (yet |been )?shipped|hasn't shipped|has not (yet )?(shipped|left)|not left|being prepared|leaves within|will (ship|leave)", low):
                flags.append("does not tell the customer the order is still in the warehouse")
            if c["kind"] == "cancel_or_change" and st == "paid" and re.search(r"\bcancel", (c.get("text") or "").lower()) and not re.search(r"\b(will be|is being|has been|is now) cancel+ed\b|\bcancel+ed and refunded\b|\bcan (still )?be cancel+ed\b", low):
                flags.append("does not confirm the cancellation — the order system says it has not shipped, so it can be cancelled and refunded in full")
            if c["kind"] == "cancel_or_change" and st == "paid" and not re.search(r"\bcancel", (c.get("text") or "").lower()) and re.search(r"\bcancel+ed and refunded\b|\bwill be cancel+ed\b", low):
                flags.append("offers a cancellation the customer did not ask for — they asked for a change")
            if c["kind"] == "cancel_or_change" and st in ("shipped", "delivered") and not re.search(r"cannot be cancel|can no longer|can't be cancel|not possible to cancel|too late to cancel|already (been )?(shipped|left|dispatched)|has (already )?left|is (currently |already )?(shipped|in transit|on its way|with gls)", low):
                flags.append(f"does not explain that the order is already {st} (no cancellation, only a return)")
            if c["kind"] == "cancel_or_change" and st in ("shipped", "delivered") and not re.search(r"\breturn", low):
                flags.append("does not offer the return (30 days of delivery) — the only option for a shipped order")
        else:
            if re.search(r"\b(has (been )?shipped|is on its way|will arrive (on|by)|arrives? (tomorrow|on)|track it here|has been dispatched|we're working on your order)\b", low):
                flags.append("claims to know the order status — it doesn't")
            if re.search(r"\b(i'll|i will|we'll|we will|have) cancel+ed|(i'll|i will|we will) cancel\b|is (now )?cancel+ed\b", low):
                flags.append("promises a cancellation without checking if it shipped")
        if c["kind"] == "discount_request" and c.get("live_code"):
            if c["live_code"].lower() not in low or re.search(r"\b(order number|check your eligibility)\b", low):
                flags.append(f"discount reply must give the live code {c['live_code']} and nothing else")
        elif c["kind"] == "discount_request" and (re.search(r"\b(check your eligibility|get back to you as soon as possible|order number|sure, i can)\b", low) or "newsletter" not in low):
            flags.append("discount reply must state the policy (newsletter 10%) and nothing else")
        if len(text) > 1200:
            flags.append("too long")
        if c.get("order_no") and c["kind"] in ("where_is_my_order", "return_or_refund", "damaged_or_wrong", "cancel_or_change") and c["order_no"] not in text:
            flags.append(f"does not repeat the customer's order number {c['order_no']}")
        for n in c["needs"]:
            key = {"order number": "order number", "photo of the damage": "photo"}.get(n, n.split()[0])
            if key not in low:
                flags.append(f"does not ask for: {n}")
        if re.search(r"^\s*(\d+\.|-|•)\s", text, re.M):
            flags.append("uses a list — should be plain sentences")
        if c.get("product") and re.search(r"\b(which|what) (product|item|set|model|one)\b.{0,40}\b(mean|refer|talking|asking)|clarify which\b", low):
            flags.append(f"asks which product although it is known ({c['product']})")
        return flags

    # ---- decisions --------------------------------------------------------------
    def decide(self, mid, decision, final_text=None, note="", kind=None, draft=None):
        rec = {"t": now(), "id": mid, "decision": decision, "text": final_text or "", "note": note,
               "kind": kind or "", "draft": (draft or "")[:1500]}
        _append(DECISIONS, rec)
        if decision in ("approved", "edited") and final_text:
            m = self.get(mid) or {}
            _append(OUTBOX, {"t": now(), "id": mid, "channel": m.get("channel", "practice"), "to": m.get("from", ""), "text": final_text})
        if decision == "edited" and final_text:
            rec["signoff_learned"] = self.learn_style(final_text, self.get(mid))
        if self.memory and decision in ("approved", "edited"):
            self.memory.note("reply", f"{decision} reply to {mid}", final_text or "", [])
        return rec

    def status(self):
        st = self.stats()
        return (f"customer messages: {len(self.items('new'))} waiting · {st['decisions']} decided "
                f"({st['approved']} approved, {st['edited']} edited, {st['rejected']} rejected)")

    AUTO_WINDOW, AUTO_RATE = 30, 0.9      # a kind may be sent automatically only after 30 decisions with ≥ 90 % approved as written

    def decisions(self):
        """All reply decisions (approved / edited / rejected / auto), oldest first."""
        return _load(DECISIONS)

    def stats(self):
        d = [x for x in _load(DECISIONS) if x.get("note") != "spam"]
        n = len(d)
        appr = sum(1 for x in d if x["decision"] == "approved")
        edit = sum(1 for x in d if x["decision"] == "edited")
        rej = sum(1 for x in d if x["decision"] == "rejected")
        kinds = {}
        for x in d:
            k = x.get("kind") or "unknown"
            kinds.setdefault(k, []).append(x["decision"])
        per = {}
        for k, decs in kinds.items():
            last = decs[-self.AUTO_WINDOW:]
            rate = sum(1 for z in last if z == "approved") / len(last)
            per[k] = {"decided": len(decs), "rate": rate,
                      "ready": len(last) >= self.AUTO_WINDOW and rate >= self.AUTO_RATE}
        return {"decisions": n, "approved": appr, "edited": edit, "rejected": rej,
                "approval_rate": (appr / n) if n else 0.0, "kinds": per}

    def stats_text(self):
        st = self.stats()
        if not st["decisions"]:
            return "No customer replies decided yet. Forward me a customer message, or /inbox practice."
        lines = [f"Customer replies: {st['decisions']} decided — {st['approved']} approved as written, {st['edited']} edited, {st['rejected']} rejected (approval {st['approval_rate']:.0%})."]
        for k, v in sorted(st["kinds"].items(), key=lambda kv: -kv[1]["decided"]):
            todo = max(0, self.AUTO_WINDOW - min(v["decided"], self.AUTO_WINDOW))
            lines.append(f"• {k.replace('_', ' ')}: {v['decided']} decided, {v['rate']:.0%} approved as written" +
                         (" — would qualify for automatic sending" if v["ready"] else f" — {todo} more needed" if todo else " — rate too low for automatic sending"))
        lines.append("Automatic sending is switched off for every type until a real channel exists and you turn it on.")
        return "\n".join(lines)

    # ---- practice set --------------------------------------------------------------
    PRACTICE = [
        ("Anna K. <anna.k@example.com>", "Order 48213 still not here", "Hi, I ordered a bamboo toothbrush set on the 2nd (order 48213) and it still hasn't arrived. Where is it?"),
        ("Marco <marco@example.com>", "", "The mug arrived broken, the handle is off. What now? Order #51190, photo attached."),
        ("Lisa M. <lisa.m@example.com>", "return", "I want to return the yoga mat, I don't like the colour. Can I get my money back?"),
        ("Tom <tom_b@example.com>", "", "Do you ship to Switzerland and how long does it take?"),
        ("Julia <julia@example.com>", "cancel", "Please cancel my order, I changed my mind. Order 51302."),
        ("dave99@example.com", "", "Is there any discount code? Your competitor is cheaper."),
        ("Sam <sam@example.com>", "", "Love the phone case, best purchase this year, thanks!!"),
        ("influencer.zoe@example.com", "collab", "Hi! I have 80k followers on Instagram, would love to collaborate on a sponsored post. What can you offer?"),
        ("angry.customer@example.com", "", "This is the second time your product arrived late. If I don't get a refund today I'll do a chargeback with my bank."),
        ("seo.pro@example.com", "Rank #1 guaranteed", "We can put your website on the first page of Google in 7 days, guaranteed. Reply for prices."),
        ("Kim <kim@example.com>", "", "The dog leash I got is the wrong size (I ordered L, got S). Order 50877."),
        ("Paul <paul@example.com>", "", "How long does the battery of the LED desk lamp last and is the light adjustable?"),
    ]

    def load_practice(self):
        added = 0
        have = {r["text"] for r in self.items()}
        for sender, subject, text in self.PRACTICE:
            if text not in have:
                self.add("practice", sender, text, subject)
                added += 1
        return added
