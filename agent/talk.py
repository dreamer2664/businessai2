"""Talk — the everyday questions an owner asks in plain words, answered directly (milestone 20 polish).

Before a message is turned into a job, this layer catches the things that need no browsing at all:

  • "what can you do?"                       → a short menu in plain words
  • "thanks, that's all" / "bye"             → a short goodbye, no menu, no job
  • "what did you do today?"                 → recap from the journal, lessons, notes and library
  • "how much should I charge for X that costs me Y?"  → the pricing maths (2.5× / 3× / 4×, fee, margin)
  • "is € 3.90 shipping too much for Italy?" → a grounded rule of thumb
  • "customer says … what do I answer?"      → treated as a customer message: a draft with Approve/Edit/Reject
  • "where do I start selling X online?"     → the standard first steps, offered as a to-do list
  • "add 'call the accountant' to my list" / "my to-do list" / "done 2" / "I ordered the boxes, tick it off"
  • "what time is it in Shenzhen?"           → local time there, gap to the owner's clock, office-hours hint
  • "shopify vs woocommerce?"                → a grounded opinion from a small table of the usual choices
  • "translate to english: …" / "how do you say X in italian" → {"translate", "to"} for the agent's thinking model
  • "do I need a partita iva?" / "how much tax on € 1,000 in Italy?" / "the customer wants a refund but used it"
                                             → Italian shop basics and EU return rules as rules of thumb (always: confirm with a commercialista)
  These "quick" ones (Talk.quick) are answered even while a job is running; the job is not touched.

Everything here is rules + arithmetic; nothing is invented. Returns None when the message is not one of these,
so the normal understanding (brief → plan → job) takes over.
"""
import datetime as _dt
import json
import re

_MONEY = r"(?:€|eur|euro|euros|\$|usd|£)?\s*(\d+(?:[.,]\d+)?)\s*(?:€|eur|euro|euros|\$|usd|£|k)?"


def _num(s):
    return float(str(s).replace(",", "."))


def _eur(x):
    return f"€ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


class Talk:
    CAN_DO = re.compile(r"^\W*(what (can|could) you do|what do you do|what are you (able|good) (to|at)|how can you help|cosa (sai|puoi) fare|che cosa fai|what else can you do)\b", re.I)
    BYE = re.compile(r"^\W*((ok(ay)?|alright|great|perfect|cool|thanks?|thank you|grazie|ty|thx)[\s,!.]*)*(that'?s all( for now)?|bye|goodbye|see you|talk later|ciao|a dopo|good night|buonanotte|nothing else|no more for now|later)\b", re.I)
    THANKS = re.compile(r"^\W*(thanks?( you)?( a lot| so much)?|grazie( mille)?|ty|thx|perfect|great job|well done|nice work|good job)\W*$", re.I)
    TODAY = re.compile(r"\b(what (did|have) you (do|done|work(ed)? on|been up to)( today| so far| this morning)?|remind me what you did|recap( of)? (today|the day)|what happened today|cosa hai fatto( oggi)?|daily recap|summary of (today|your day))\b", re.I)
    PRICE = re.compile(r"\b(how much (should|can|do) i (charge|sell|price|ask)|what (price|should i charge)|(sell|retail) price for|quanto (dovrei|posso) (chiedere|far pagare)|a che prezzo)\b", re.I)
    COST = re.compile(r"\b(?:costs?(?: me)?|cost price|i pay|buy (?:it )?(?:for|at)|mi costa|pago)\s*" + _MONEY, re.I)
    SHIP_OK = re.compile(r"\b(?:is|are)\s*" + _MONEY + r"\s*(?:for )?(?:shipping|delivery|spedizione)(?: (?:cost|fee))?(?: (?:to|for|in) [a-z ]{2,20}?)?\s*(?:too (?:much|expensive|high)|ok|okay|fine|reasonable|fair|normal|a lot|acceptable|right)"
                         r"|\b(?:è|e'|sono) (?:troppo|troppi|giusto|giusti|ok|normale|normali|tanto|tanti|caro|cara)?\s*" + _MONEY + r"\s*(?:di |per la |per )?spedizione", re.I)
    LAST_DOC_IT = re.compile(r"\b(?:mandami|rimandami|inviami|rimanda|manda|carica)\b.{0,20}\b(?:l'?ultimo|quel|il) (?:documento|report|file|pdf)\b", re.I)
    CUSTOMER_FWD = re.compile(r"^\W*(?:a |the |my |one |another |un |una |il |la )?(?:customer|client|buyer|cliente)s?\s+(?:says?|said|wrote|writes|complain(?:s|ed)?|messaged|emailed|sent|dice|ha scritto|scrive|lamenta)\b(?P<inner>.{8,400})$", re.I | re.S)
    CUSTOMER = re.compile(r"\b(?:a |the |my )?(?:customer|client|buyer|cliente)s?\s+(?:says?|wrote|writes|asks?|is asking|complain(?:s|ed)?|messaged|emailed|sent|dice|scrive|chiede)\b(?P<inner>.{0,400}?)(?:what (?:do|should|can) i (?:answer|reply|say|tell|write|do)|how (?:do|should) i (?:answer|reply|respond|handle)|cosa (?:rispondo|gli dico|le dico|faccio)|what now)\b", re.I | re.S)
    START = re.compile(r"\b(where (do|should) i (start|begin)|how (do|should|can) i (start|begin|get started)|i want to (start|sell|open)|voglio (vendere|aprire|iniziare)|da dove (comincio|inizio|parto))\b", re.I)
    OPINION_IT = re.compile(r"\b(che ne pensi|cosa ne pensi|secondo te)\b", re.I)
    # ---- the practice store in plain words ----
    STORE_NUM = re.compile(r"\b(?:how ?many (?:orders|sales|visitors|visits|customers)|^\W*(?:orders?|sales|profit|revenue|visits|visitors|conversion|best[- ]?sellers?|ordini|vendite|profitto|incasso|fatturato|visite)(?: (?:today|this week|so far|this month|oggi|di oggi|della settimana|questa settimana|del mese|finora))?(?=\W*$)|total (?:sales|revenue|orders|profit)(?: so far)?|(?:what(?:'s| is| are) )?(?:our|my|the) (?:best[- ]?sellers?|top (?:product|seller)s?|conversion(?: rate)?|revenue|turnover|profit|margin|numbers|visitors|visits)|how much (?:profit|money|revenue) (?:did|have) (?:we|i) (?:make|made|earn|earned)|(?:profit|revenue|sales) (?:so far|this week|today|this month)|summary of (?:the|this|my) (?:week|day|month)|(?:weekly|daily) summary|how(?:'s| is| are) (?:business|sales|things) going|quanti ordini|quante visite|quanto (?:abbiamo|ho) (?:guadagnato|venduto|incassato|fatto)|quanto (?:ho|abbiamo) guadagnato|qual ?[èe] il (?:più venduto|best seller|prodotto (?:più|che) vend\w+)|quali? (?:prodott[oi]|articol[oi]|cos[ae]) (?:vend[eo]no?|si vend[eo]no?|va|vanno) (?:meglio|di più|bene)|cosa vende (?:di più|meglio)|(?:quanti soldi|quanto) (?:abbiamo|ho) (?:fatto|guadagnato) (?:oggi|questa settimana|finora)|riepilogo (?:della |di questa )?(?:settimana|giornata)|riassunto (?:della |di questa |del |di )?(?:settimana|giornata|mese)|(?:our|my|the) (?:average (?:order|basket)(?: value| size)?|aov)|scontrino medio|what (?:did|have) (?:we|i) (?:earn|make|made|earned|sell|sold|take|taken)(?: in)?(?: this week| today| this month| so far| yesterday)?|are we (?:profitable|making money|in profit|losing money|in the black|in the red)|is (?:the|our|my|this) (?:shop|store|business) (?:profitable|making money|losing money|in profit)|does (?:the|our|my|this) (?:shop|store|business) make (?:any )?money|do we make (?:any )?money|siamo in (?:utile|perdita|attivo|passivo)|how much (?:did|have|do) (?:we|i) (?:spend|spent|pay|paid) (?:on|for) (?:shipping|postage|goods|stock|fees|payment fees|the goods)|quanto (?:abbiamo speso|spendiamo) (?:in|di|per) spedizioni|how many (?:customers|buyers|clients|clienti) (?:do (?:we|i) have|have we had|so far|in total|have bought)|quanti clienti abbiamo|which (?:product|item|one) (?:makes|earns|brings|gives)(?: us| me)? the most (?:money|profit|margin)|(?:most profitable|highest[- ]margin|biggest earner) (?:product|item)|what(?:'s| is) (?:our|the) (?:most profitable|highest[- ]margin) (?:product|item)|which product (?:earns|makes) (?:the )?most|(?:how are we doing|how did we do|come (?:siamo andati|è andata)) (?:compared to|vs\.?|versus|against|rispetto a(?:lla)?) (?:last|the previous|la scorsa|la settimana scorsa)|compared to last week|rispetto alla settimana scorsa)\b", re.I)
    SHIP_COST_Q = re.compile(r"\b(?:(?:can|could|do|does|will) (?:we|i|you|the shop|it) (?:also )?(?:ship|deliver|send|be shipped|be sent) to [a-zà-ú ]{2,25}\??|(?:spediamo|spedite|spedisci|consegnate) (?:in|a|anche in) [a-zà-ú ]{2,25}|how long (?:does|will|would) (?:it|shipping|delivery|a parcel|an order) take (?:to (?:ship|deliver|arrive|get|reach))?(?: (?:to|in) [a-zà-ú ]{2,25})?|how (?:long|many days) (?:to|for) [a-zà-ú ]{2,25}\??|quanto ci mette (?:a arrivare )?(?:in|a) [a-zà-ú ]{2,25}|how much (?:is|does|do we charge for|costs?) (?:the )?(?:shipping|delivery|postage)|(?:shipping|delivery) (?:cost|price|fee)s?(?: to| for)?|what do we charge (?:for )?(?:shipping|delivery)|quanto (?:costa|chiediamo per) (?:la )?spedizione|quanto costa spedire|what are (?:our|the|my) (?:shipping|delivery) (?:days|times|options|rules|prices|rates)|how long (?:does|is) (?:our |the )?(?:shipping|delivery)(?: take)?|(?:our|my) (?:shipping|delivery) (?:times|days|rules)|(?:tempi|giorni) di (?:spedizione|consegna)|spedizione (?:in|per|verso) [a-zà-ú]+ quanto costa|spedire in [a-zà-ú]+ quanto costa)\b", re.I)
    SELLOUT_Q = re.compile(r"\b(?:how (?:long|many days|many weeks) (?:until|before|till) (?:the |our )?(?P<what>[a-z][a-z \-]{2,40}?) (?:sells? out|runs? out|is gone|is sold out)|when (?:will|does) (?:the |our )?(?P<what2>[a-z][a-z \-]{2,40}?) (?:sell out|run out)|(?:stock|units) (?:left )?(?:of |for )?(?:the )?(?P<what3>[a-z][a-z \-]{2,40}?) (?:last|lasts|will last)|quanto dura(?:no)? (?:le |la |il |lo |gli |i )?(?P<what4>[a-zà-ú][a-zà-ú \-]{2,40}?)\?)", re.I)
    MATHS = re.compile(r"^\W*(?:what(?:'s| is)|quanto (?:fa|è)|calcola|calculate|compute)?\s*(?P<a>\d+(?:[.,]\d+)?)\s*%\s*(?:of|di|del|della)\s*(?P<b>\d+(?:[.,]\d+)?)\W*$"
                       r"|^\W*(?:what(?:'s| is)|quanto fa)?\s*(?P<c>\d+(?:[.,]\d+)?)\s*(?:€|eur|euro)?\s*(?:plus|più|\+)\s*(?P<d>\d+(?:[.,]\d+)?)\s*%\W*$"
                       r"|^\W*(?:what(?:'s| is)|quanto fa)?\s*(?P<e>\d+(?:[.,]\d+)?)\s*(?:€|eur|euro)?\s*(?:minus|meno|less|-)\s*(?P<f>\d+(?:[.,]\d+)?)\s*%\W*$"
                       r"|^\W*(?:what(?:'s| is)|quanto fa|calcola|calculate|compute)?\s*(?P<expr>[\d.,]+(?:\s*[-+*/x×÷:]\s*[\d.,]+)+)\W*$", re.I)
    WHATIF = re.compile(r"\b(?:if|when|se)\s+(?:i|we)\s+(?:sell|sold|vendo|vendiamo)\s+(?P<n>\d+)\s+(?P<what>[a-zà-ú][a-zà-ú \-]{2,40}?)\s+(?:a|per|al|every|each|ogni)\s+(?P<per>month|week|day|mese|settimana|giorno)\b.{0,40}?\b(?:at|a|for|per)\s*" + _MONEY.replace("(\\d", "(?P<price>\\d") + r".{0,30}?\b(?:cost|costs|costing|costo|that cost me|mi costa)\s*" + _MONEY.replace("(\\d", "(?P<cost>\\d") + r"|\b(?:if|when|se)\s+(?:i|we)\s+(?:sell|sold|vendo|vendiamo)\s+(?P<n2>\d+)\s+(?P<what2>[a-zà-ú][a-zà-ú \-]{2,40}?)\s+(?:a|per|al|every|each|ogni)\s+(?P<per2>month|week|day|mese|settimana|giorno)\b", re.I)
    THANK_NOTE = re.compile(r"\b(?:write|draft|make|scrivi|scrivimi|prepara)\b.{0,20}?\b(?:thank[- ]you (?:note|card|message|slip)|thanks card|note (?:to put |for )?(?:in|into) the (?:parcels?|packages?|boxes?|orders?)|biglietto (?:di ringraziamento|per i pacchi)|messaggio di ringraziamento)\b", re.I)
    CANCEL_HOW = re.compile(r"\b(?:how (?:do|should|can) i (?:answer|reply to|respond to|handle|deal with)|what (?:do|should|can) i (?:say|answer|reply|tell|write) to)\b.{0,30}?\b(?:customer|client|buyer|someone)\b.{0,40}?\b(?:cancel|cancellation|refund|return|complain|angry|wants? (?:their|his|her) money back|where (?:is|'s) (?:the|their|his|her|my) order|where (?:the|their|his|her|my) order is|tracking|hasn'?t arrived|late|not arrived)\b|\bcome rispondo a un cliente che (?:vuole annullare|vuole il rimborso|si lamenta|chiede dov'è l'ordine)\b", re.I)
    REMIND_AT = re.compile(r"^\W*(?:remind me|ricordami)\s+(?P<when>(?:tomorrow|domani|today|oggi|tonight|stasera|on \w+day|monday|tuesday|wednesday|thursday|friday|saturday|sunday|lunedì|martedì|mercoledì|giovedì|venerdì|sabato|domenica|in \d+ (?:hours?|minutes?|days?|ore|minuti|giorni))(?:\s+(?:at|alle|alle ore)\s+\d{1,2}(?:[:.]\d{2})?(?:\s*(?:am|pm))?)?|(?:at|alle)\s+\d{1,2}(?:[:.]\d{2})?(?:\s*(?:am|pm))?(?:\s+(?:tomorrow|domani|today|oggi))?)\s+(?:to|di|a)?\s*(?P<what>.+?)\W*$", re.I)
    DOMAIN_Q = re.compile(r"\b(?:is|check(?: if| whether)?|see if|verify|controlla se|vedi se)\b.{0,30}?\b(?:the )?domain\b.{0,30}?\b(?P<dom>[a-z0-9-]+\.(?:com|it|eu|net|org|shop|store|co|io|de|fr|es))\b.{0,20}?\b(?:free|available|taken|libero|disponibile|occupato)\b|\b(?P<dom2>[a-z0-9-]+\.(?:com|it|eu|net|org|shop|store|co|io|de|fr|es))\b.{0,20}?\b(?:free|available|taken|libero|disponibile)\?", re.I)
    COST_CHANGE = re.compile(r"\b(?:the |my |our |il |la )?(?:supplier|fornitore|factory|vendor)\s+(?:raised|increased|upped|lowered|dropped|cut|changed|ha alzato|ha aumentato|ha abbassato)\s+(?:the |il |la )?(?:cost|price|prezzo|costo)\s+(?:of |for |del |della |dei |delle )?(?:the |a |an |il |la |i |le )?(?P<what>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?)\s+(?:to|at|a)\s*" + _MONEY.replace("(\\d", "(?P<v1>\\d")
                             + r"|\b(?:the |my |our |il |la )?(?:supplier|fornitore|factory|vendor)\s+(?:raised|increased|upped|lowered|dropped|cut|changed|ha alzato|ha aumentato|ha abbassato)\s+(?:the |il |la )?(?P<what2>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?)\s+(?:cost|price|prezzo|costo)\s+(?:to|at|a)\s*" + _MONEY.replace("(\\d", "(?P<v2>\\d")
                             + r"|\b(?:the |il |la )?(?:cost|costo)\s+(?:of |del |della |dei )?(?:the |il |la )?(?P<what3>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?)\s+(?:went up|rose|is now|went down|fell|è salito|è sceso|è ora|adesso è)\s+(?:to|a)?\s*" + _MONEY.replace("(\\d", "(?P<v3>\\d")
                             + r"|\b(?:the |il |la )?(?P<what4>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?)\s+(?:now )?(?:costs?|mi costa|ci costa)\s+(?:me |us )?" + _MONEY.replace("(\\d", "(?P<v4>\\d") + r"\s+(?:now|from now on|these days|da oggi|adesso|ora)\b"
                             + r"|\b(?:the |il |la )?(?P<what5>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?)\s+(?:cost|costo|purchase price|buy price)\s+is\s+(?:actually|really|in fact|now|wrong[,:]? it'?s|in realtà|veramente)\s*" + _MONEY.replace("(\\d", "(?P<v5>\\d")
                             + r"|\b(?:actually|in fact|correction[,:]?|in realtà|veramente)\s+(?:the |il |la )?(?P<what6>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?)\s+(?:costs?|cost is|mi costa|ci costa|costa)\s+(?:me |us )?" + _MONEY.replace("(\\d", "(?P<v6>\\d")
                             + r"|\b(?:the )?(?:real|true|correct|actual|right) (?:cost|purchase price) (?:of |for )(?:the |a )?(?P<what7>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?)\s+is\s*" + _MONEY.replace("(\\d", "(?P<v7>\\d"), re.I)
    PUSH_Q = re.compile(r"\b(?:which|what|quale|che)\s+(?:product|item|one|prodotto|articolo)\s+(?:should|do|would|can) (?:i|we)\s+(?:push|promote|advertise|feature|boost|focus on|put money behind|spingere|promuovere)|(?:what|which|cosa|che)\b.{0,20}?\b(?:push|promote|spingere|promuovere)\b.{0,20}?\b(?:this week|today|now|next|questa settimana|oggi|adesso)|(?:che|quale) prodotto conviene (?:spingere|promuovere|pubblicizzare)\b|\bwhat(?:'s| is) worth (?:pushing|promoting|advertising)\b", re.I)
    COMPLAINTS_Q = re.compile(r"\b(?:what (?:did|do|have) (?:customers|people|buyers|clients) (?:complain|complained|moan|say is wrong)|(?:any|what|which) complaints?|customer complaints|complaints? (?:so far|this week|today)|what(?:'s| is) (?:going wrong|the most common (?:problem|issue|complaint))|di cosa si lamentano|lamentele|reclami)\b", re.I)
    REORDER_Q = re.compile(r"\b(?:how (?:much|many)|quant[oi])\b.{0,20}?\b(?:stock|units|pieces|pezzi)?\s*(?:should|do|must|devo|dovrei) (?:i|we)? ?(?:order|reorder|buy|restock|ordinare|riordinare|comprare)\b.{0,20}?\b(?:of |for |del |della |dei |delle )?(?:the |il |la |i |le )?(?P<what>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?)\W*$|\b(?:reorder|restock|riordino)\s+(?:quantity|qty|amount|how many)\b.{0,20}?\b(?:for |of |per )?(?:the )?(?P<what2>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?)\W*$", re.I)
    PRICE_OK = re.compile(r"\b(?:is|are|isn'?t|sono|è)\s+" + _MONEY.replace("(\\d", "(?P<amt>\\d") + r"\s+(?:too (?:much|expensive|high|cheap|low|little)|troppo (?:caro|alto|poco|basso)|ok|okay|fine|fair|reasonable|right|a good price|giusto)\s+(?:for|per)\s+(?:a |an |the |our |my |un |una |il |la )?(?P<what>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?)\W*$", re.I)
    SALE_Q = re.compile(r"\b(?:black friday|cyber monday|christmas sale|saldi|sconti|a sale|the sale|discount(?:s| code| week)?|promo(?:tion)?)\b.{0,40}?\b(?:prices?|prezzi|how much off|what discount|quanto sconto|percent|%)|\b(?:what|which|how much|quanto|quale)\b.{0,30}?\b(?:discount|sconto|prices?|prezzi)\b.{0,30}?\b(?:black friday|cyber monday|christmas|natale|saldi|sale|promo)\b|\bhow (?:much|big) (?:a )?discount (?:can|should) (?:i|we) (?:give|offer|do|afford)\b", re.I)
    FREE_RETURNS = re.compile(r"\b(?:should (?:i|we) (?:offer|do|give|have|accept) free returns?|free returns?\s*(?:\?|or not|worth it|yes or no|good idea)|(?:offer|give) free returns\?|resi gratuiti(?: sì o no| conviene|\?)|conviene (?:il reso gratuito|offrire il reso gratuito)|who (?:should )?pays? (?:for )?(?:the )?returns?)\b", re.I)
    CAPTIONS = re.compile(r"\b(?:give me|write|draft|make|suggest|fammi|scrivi(?:mi)?|dammi)\b.{0,12}?\b(?P<n>\d+|three|four|five|six|tre|cinque)?\s*(?:captions?|didascali[ae]|post captions?|instagram captions?|hooks?)\b.{0,20}?\b(?:for|per|about|su)\s+(?:the |a |an |our |my |il |la |una |un )?(?P<what>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?)\W*$", re.I)
    WRITE_PAGE = re.compile(r"\b(?:write|draft|make|create|prepare|scrivi(?:mi)?|prepara|fammi)\b.{0,20}?\b(?:the |a |an |our |my |la |una |il |le )?(?P<kind>shipping|delivery|returns?|refund|about(?: us)?|faq|privacy|terms|contact|spedizioni?|resi|chi siamo|domande frequenti)\s+(?:policy|page|pagina|text|section|policy page)\b|\b(?:write|draft|make|scrivi|prepara)\b.{0,12}?\b(?:the |le |la )?(?P<kind2>faq|about us|privacy policy|terms and conditions|termini e condizioni|domande frequenti)\b", re.I)
    INBOX_Q = re.compile(r"\b(?:how many (?:e-?mails?|messages?|customer messages?|mails?|tickets?|requests?) (?:are |is )?(?:waiting|pending|unanswered|new|open|in the inbox|to answer|do (?:i|we) have)|how many customers (?:are )?(?:waiting|pending|unanswered|to answer|wrote|have written)|(?:anything|what(?:'s| is)) (?:new )?(?:in|waiting in) the inbox|any (?:new )?(?:messages?|e-?mails?|customer messages?)(?: waiting| to answer| today)?\??|quant[ei] (?:mail|e-?mail|messaggi|richieste) (?:ci sono|abbiamo|aspettano|da rispondere)|c'è qualcosa (?:nella|in) (?:posta|inbox))\b", re.I)
    PLATE = re.compile(r"^\W*(?:what(?:'s| is|’s)?\s*(?:on my plate|on the agenda|on (?:for|the plan) today|the plan (?:for )?today|today'?s plan|left (?:to do|for today)|(?:the )?priority today|urgent today)|what (?:do|should) (?:i|we) (?:do|have to do|need to do|handle) (?:today|now|first|this morning)|where (?:do|should) (?:i|we) start today|cosa (?:devo|dobbiamo) fare oggi|cosa c'è (?:da fare )?oggi|priorità (?:di )?oggi|da dove (?:inizio|comincio) oggi)(?:\s+(?:today|this morning|now|oggi|stamattina))?\W*$", re.I)
    ORDER_ACT = re.compile(r"^\W*(?:please |can you |could you |puoi )?(?P<act>cancel|refund|ship|mark(?: as)? shipped|annulla|rimborsa|spedisci)\s+(?:the )?(?:order|ordine)?\s*#?\s*(?P<n>\d{4,6})\b(?P<why>.*)$", re.I | re.S)
    SHIP_ALL = re.compile(r"^\W*(?:ship|send out|post|spedisci)\s+(?:everything|all|all (?:the )?(?:open |paid |pending )?orders|them all|tutto|tutti gli ordini)\W*$", re.I)
    LATE_Q = re.compile(r"\b(?:which|what|any|quali)\s+orders?\s+(?:are|is)\s+(?:late|overdue|delayed|stuck|waiting too long|in ritardo)|\b(?:late|overdue|delayed|stuck) orders\b|\bordini in ritardo\b|\banything (?:late|overdue|stuck)\b", re.I)
    WHO_BOUGHT = re.compile(r"\b(?:who (?:bought|ordered|purchased)|chi ha (?:comprato|ordinato))\s+(?:the |a |an |il |la |lo |i )?(?P<what>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?)(?:\s+(?:this week|today|yesterday|so far|oggi|ieri))?\W*$", re.I)
    MARGIN_ON = re.compile(r"\b(?:what(?:'s| is) (?:my |our |the )?(?:margin|markup|profit)|how much (?:do (?:i|we) make|margin|profit)|quanto (?:guadagno|ci guadagno|margine))\s+(?:on|per|for|su|sul|sulla|sulle|sui)\s+(?:each |every |a |one |the |our |my |il |la |lo |i |ogni )?(?P<what>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?)\W*$", re.I)
    SOLD_WHEN = re.compile(r"\b(?:what (?:did|have) we (?:sell|sold)|what sold|cosa abbiamo venduto|quanto abbiamo venduto)\s*(?P<when>yesterday|today|this week|last week|so far|ieri|oggi|questa settimana|la settimana scorsa)?\W*$", re.I)
    ORDER_Q = re.compile(r"\b(?:status|state|stato|total|totale|details?|dettagli|what(?:'s| is) in|contents? of|when was|who (?:placed|made)|tracking (?:number|code)? ?(?:of|for)?|where(?:'s| is)) (?:of |for |the )?(?:order|ordine)?\s*#?\s*(?P<n>\d{4,6})\b|\b(?:order|ordine)\s*#?\s*(?P<n2>\d{4,6})\b.{0,20}?\b(?:status|shipped|paid|delivered|total|details|where|stato|spedito|totale)\b|\b(?:did (?:we|i) ship|have we shipped|is|was|has|abbiamo spedito)\s+(?:order |ordine |#)?\s*(?P<n3>\d{4,6})\s*(?:shipped|delivered|paid|refunded|out|gone|spedito|consegnato|partito)?\W*$", re.I)
    PRODUCT_FACT = re.compile(r"\b(?:is|are|does|do|can|will|has|have|comes?|what|how|which|quanto|quale|è|sono|ha)\b.{0,40}?\b(?:dishwasher|microwave|waterproof|washable|charger|adapter|cable|battery|charge|charging|warranty|garanzia|material|made of|made in|size|dimensions?|weigh|weight|heavy|capacity|ml|colou?rs?|models?|iphone|samsung|bristles|plastic|lead[- ]free|vegan|safe|last|hours|how long does the battery|sizes|fit|fits|include[sd]?|in the box|come with|comes with|lavastoviglie|caricatore|batteria|materiale|peso|dimensioni|colori|taglie)\b", re.I)
    AVAILABLE_Q = re.compile(r"\b(?:is|are|do (?:we|you) (?:still )?have|c'è|ci sono|abbiamo ancora|avete ancora)\s+(?:the |any |some |a |an |il |la |i |le |dei |delle )?(?P<what>[a-zà-ú][a-zà-ú0-9 \-]{2,30}?)\s+(?:still )?(?:available|in stock|sold out|out of stock|left|disponibil[ei]|esaurit[oi]|finit[oi])\b|\b(?:when|quando)\s+(?:will|do|does|are|is|arriva|arrivano|torna|tornano)\s+(?:the |il |la |i |le )?(?P<what2>[a-zà-ú][a-zà-ú0-9 \-]{2,30}?)\s+(?:be )?(?:back(?: in stock)?|available again|restocked|arrive|come back|disponibil[ei])\b", re.I)
    REFUNDS_Q = re.compile(r"\b(?:any|how many|quanti|quali|which|list)\s+(?:refunds?|returns?|cancellations?|cancelled orders?|rimborsi|resi|annullamenti)\b|\b(?:refunds?|returns?|cancellations?)\s+(?:this week|today|this month|so far|yesterday|lately)\b|\bdid (?:we|anyone) (?:refund|return|cancel) (?:anything|any orders?|something)\b|\bdid we lose money on any order\b|\b(?:orders?|ordini) (?:where|that|on which) we lost money\b|\blost money on (?:any|an) orders?\b|\bmoney[- ]losing orders\b", re.I)
    PRICE_SHIP_Q = re.compile(r"\b(?:how much (?:is|are|for|does|do|would|will)|what (?:do|would) (?:we|i) charge for|price (?:of|for)|cost (?:of|for)|total (?:for|of)|quanto (?:costa|costano|viene|vengono|paga)|quanto (?:è|sono))\s+(?:a |an |the |one |1 |il |la |un |una |due |tre |\d+ ?x? )?(?P<qty>\d+)?\s*(?:x\s*)?(?P<what>[a-zà-ú][a-zà-ú0-9 \-]{2,30}?)\s+(?:with|incl(?:uding|uded)?|plus|and|\+|con|più|compres[ao]|spedit[oi]|shipped|delivered|sent)\s*(?:the |la )?(?:shipping|delivery|postage|spedizione|consegna)?\s*(?:to|in|for|a|per|verso)\s+(?P<where>[a-zà-ú][a-zà-ú ]{2,25}?)\W*$|\bwhat do we charge for (?P<qty2>\d+)\s+(?P<what2>[a-zà-ú][a-zà-ú0-9 \-]{2,30}?)\s+(?:to|in|for)\s+(?P<where2>[a-zà-ú][a-zà-ú ]{2,25}?)\W*$", re.I)
    WEIGHT_Q = re.compile(r"\b(?:how (?:heavy|much (?:does|do|would|will) .{2,40}? weigh)|weight of|what(?:'s| is) the weight (?:of|for)|quanto pesa|quanto pesano|peso d(?:el|ella|i))\b(?:\s+(?:is|are|would be|sarebbe))?\s*(?:(?:the |a |an |il |la |un |una )?(?:parcel|package|box|shipment|pacco|spedizione)\s+(?:for|with|of|di|con|per)\s+)?(?:the |a |an |il |la |un |una |two |three |due |tre )?(?P<qty>\d+)?\s*(?:x\s*)?(?P<what>[a-zà-ú][a-zà-ú0-9 \-]{2,30}?)(?:\s+weigh)?\W*$", re.I)
    SOLD_TODAY_Q = re.compile(r"^\W*(?:(?:did we|have we|abbiamo) (?:sell|sold|venduto) (?:anything|something|qualcosa|nothing)|anything sold|any sales|nothing sold|(?:sold|venduto) (?:anything|something|qualcosa))(?:\s+(?P<when>today|yet|so far|this morning|yesterday|this week|oggi|stamattina|ieri|questa settimana))?\W*$|^\W*(?:sales|orders|vendite|ordini)\s+(?P<when2>today|yesterday|oggi|ieri)\W*$", re.I)
    ITEMS_TOTAL_Q = re.compile(r"\bhow many (?:items|units|pieces|products|things|pezzi|articoli) (?:did we sell|have we sold|sold|were sold|abbiamo venduto|venduti)(?: in total| so far| this week| today| this month| in totale| oggi| questa settimana)?\W*$|\b(?:total|totale) (?:items|units|pieces|pezzi) (?:sold|venduti)\b", re.I)
    REORDER_LIST_Q = re.compile(r"\b(?:what (?:do (?:i|we)|should (?:i|we)) (?:need to )?(?:reorder|re-order|restock|buy|order from the supplier)|what(?:'s| is) (?:running )?(?:low|out)|(?:reorder|restock|shopping) list|anything to reorder|cosa (?:devo|dobbiamo) (?:riordinare|ricomprare)|cosa (?:sta finendo|manca))\b", re.I)
    TOP3_Q = re.compile(r"\b(?:top|first|main|three|3|le tre|le prime) (?:\d |three |3 )?(?:things|tasks|priorities|jobs|cose|priorità|things to do)\b.{0,20}?\b(?:today|now|this morning|this week|oggi|stamattina|adesso|questa settimana)\b|\bwhat (?:matters|counts) most (?:today|now|this week)\b|\bmost important (?:thing|task)s? (?:today|now|this week)\b", re.I)
    BEST_CUSTOMER_Q = re.compile(r"\b(?:who(?:'s| is| are) (?:our|my|the) (?:best|top|biggest|most loyal|repeat) (?:customer|client|buyer)s?|(?:best|top|biggest) (?:customer|client|buyer)s?\b.{0,15}?\b(?:who|which|so far|this month|this week)|chi (?:è|sono) (?:il|i) (?:nostr[oi] )?miglior[ei] client[ei]|repeat (?:customers|buyers)\b.{0,15}?\b(?:who|how many|any))\b", re.I)
    STOCK_VALUE = re.compile(r"\b(?:how much (?:money|cash|capital) (?:is )?(?:tied up|sitting|stuck|invested) in (?:stock|inventory)|how much (?:stock|inventory|merchandise|goods) (?:do (?:we|i) have|is there|have we got)(?: in total| overall| altogether)?(?:,? in (?:euros?|money|value|€))?|quanto magazzino abbiamo|(?:stock|inventory|magazzino) (?:in (?:euros?|money|value)|totale)|(?:stock|inventory) value|value of (?:our|my|the) (?:stock|inventory)|quanto (?:vale|abbiamo) (?:il |in )?magazzino|how many days of stock (?:do we have|overall|in total|left)|days of stock)\b", re.I)
    OOS_SAY = re.compile(r"\b(?P<what>[a-zà-ú][a-zà-ú0-9 \-]{2,30}?)\s+(?:is|are|è|sono)\s+(?:out of stock|sold out|esaurit[oi]|finit[oi])\b.{0,30}?\b(?:what (?:do|should) i (?:tell|say|answer|write)|cosa (?:dico|rispondo))\b|\b(?:what (?:do|should) i (?:tell|say to|answer)|cosa (?:dico|rispondo))\b.{0,30}?\b(?:out of stock|sold out|esaurito)\b", re.I)
    BANK_TRANSFER = re.compile(r"\b(?:bank transfer|wire transfer|bonifico|pay (?:on|at) delivery|cash on delivery|contrassegno|paypal (?:friends|family)|pay (?:by|with|via) (?:bank|wire|bonifico|crypto|bitcoin))\b", re.I)
    BULK_DISC = re.compile(r"\b(?:someone |a customer |a buyer |un cliente )?(?:ordered|wants|asks? for|is asking for|would like|bought|ha ordinato|vuole|chiede)\s+(?P<n>\d{1,4})\s+(?P<what>[a-zà-ú][a-zà-ú0-9 \-]{2,30}?)\b.{0,40}?\b(?:discount|sconto|price break|cheaper|deal|wholesale)\b|\b(?:discount|sconto)\b.{0,30}?\b(?:for|on|per|su)\s+(?P<n2>\d{1,4})\s+(?P<what2>[a-zà-ú][a-zà-ú0-9 \-]{2,30}?)\b", re.I)
    FIRST_CUST = re.compile(r"\b(?:how (?:do|can|should) (?:i|we) (?:get|find|win|reach|attract) (?:my |our |the )?first (?:\d+ )?(?:customers?|sales?|orders?|buyers?)|first (?:\d+ )?(?:customers|sales|orders) (?:how|where|tips)|come (?:trovo|trovare|avere) i primi (?:clienti|ordini)|where do (?:my |the )?first (?:customers|sales) come from|nobody is buying|no sales yet)\b", re.I)
    ADS_BUDGET = re.compile(r"\b(?:i have|i've got|we have|ho|abbiamo|budget(?: of| is)?|with)\s*" + _MONEY.replace("(\\d", "(?P<amt>\\d") + r"\s*(?:a month|per month|al mese|a week|per week)?\s*(?:for|to spend on|budget for|di budget per|in|per)\s+(?:ads|advertising|marketing|meta ads|facebook ads|instagram ads|tiktok ads|google ads|pubblicità|promozione)\b|\bwhere (?:do|should) i (?:put|spend|invest) (?:my |the )?(?:ad|ads|marketing) (?:money|budget|euros)\b|\b(?:ads?|advertising|marketing) budget\b.{0,20}?\bwhere\b", re.I)
    VAT_ON = re.compile(r"\b(?:what(?:'s| is) the |how much |quanto è l'|quanta )?(?:vat|iva|sales tax)\b.{0,20}?\b(?:on|of|in|su|per|for)\s+(?:a |an |the |un |una |il |la )?" + _MONEY.replace("(\\d", "(?P<amt>\\d") + r"(?:\s+(?P<what>[a-zà-ú][a-zà-ú0-9 \-]{2,30}?))?\W*$|\b(?:vat|iva)\s+(?:included|inclusa|compresa)\b.{0,20}?" + _MONEY.replace("(\\d", "(?P<amt2>\\d"), re.I)
    FEES_PAID = re.compile(r"\b(?:how much (?:did|have|do) we (?:pay|paid|spend|spent|lose|lost) (?:in|on) (?:payment |card |stripe |paypal |gateway |transaction )?fees|(?:payment |card |gateway |transaction )?fees (?:so far|this week|this month|paid|total)|quanto abbiamo pagato di commissioni|commissioni (?:pagate|totali))\b", re.I)
    BIO_Q = re.compile(r"\b(?:write|draft|make|create|suggest|scrivi|scrivimi|fammi|crea)\b.{0,20}?\b(?:instagram|tiktok|ig|social|profile|profilo)?\s*(?:bio|biography|profile text|about text|tagline|slogan)\b", re.I)
    SET_FREE_SHIP = re.compile(r"\b(?:set|make|put|change|offer|introduce|metti|imposta|offri)\b.{0,15}?\bfree (?:shipping|delivery)\b.{0,20}?\b(?:over|above|from|for orders over|from orders of|sopra|oltre|da)\s*" + _MONEY.replace("(\\d", "(?P<amt>\\d") + r"|\bspedizione gratuita\b.{0,15}?\b(?:sopra|oltre|da)\s*" + _MONEY.replace("(\\d", "(?P<amt2>\\d")
                               + r"|^\W*free (?:shipping|delivery)\s+(?:over|above|from)\s*" + _MONEY.replace("(\\d", "(?P<amt3>\\d") + r"\W*(?:from now on|please|in italy)?\W*$"
                               + r"|\b(?:free (?:shipping|delivery) threshold|soglia (?:della )?spedizione gratuita)\s*(?:to|at|→|=|a)\s*" + _MONEY.replace("(\\d", "(?P<amt4>\\d"), re.I)
    WHY_NOBODY = re.compile(r"\b(?:why (?:did|has|does|is) (?:nobody|no one|no-one|noone) (?:buy|bought|buying|order|ordered|want)|why (?:isn'?t|doesn'?t|aren'?t|don'?t) (?:the |our |my )?(?P<what0>[a-zà-ú][a-zà-ú0-9 \-]{2,30}?) (?:sell|selling|move|moving)|why (?:are|is) (?:the |our |my )?(?P<what00>[a-zà-ú][a-zà-ú0-9 \-]{2,30}?) not selling|perch[eé] nessuno compra|perch[eé] non (?:si )?vend(?:e|ono))\b(?:\s+(?:the |our |my |i |le |il |la )?(?P<what>[a-zà-ú][a-zà-ú0-9 \-]{2,30}?))?\W*$", re.I)
    PAGE_LANG = re.compile(r"\b(?:translate|traduci)\b.{0,12}?\b(?:the |la |le )?(?P<page>shipping|returns?|faq|contact|about|spedizioni?|resi|contatti)\s+(?:page|policy|pagina)\b.{0,12}?\b(?:into|in|to) (?P<lang>english|italian|german|french|spanish|dutch|inglese|italiano|tedesco|francese|spagnolo|olandese)\b|\bmake the (?:shop|store|negozio) (?:bilingual|in (?:english|italian|german|french|spanish)( too| as well)?|multilingual)\b|\b(?:negozio|shop|store) (?:bilingue|anche in inglese|anche in italiano)\b", re.I)
    CHECK_IN = re.compile(r"^\W*(?:so |hey |ok |ciao |hi )?(?:how (?:r|are) (?:we|things|you guys|we doing)|how(?:'s| is) (?:it|everything|business|the shop|the store|the day) ?(?:going|doing)?|(?:is )?everything (?:ok|okay|fine|alright|good)(?: with the (?:shop|store))?|all (?:good|ok|fine|quiet)|any (?:problems?|issues?|trouble|news|updates?)|"
                          r"(?:give me an? |quick )?(?:update|status update|sitrep|rundown|briefing)(?: me)?|update me|catch me up|fill me in|anything (?:i should know|new|urgent|to report|happened|going on)|what(?:'s| is) (?:new|up|going on|happening|the situation)|what needs my attention|what should i look at|"
                          r"did anything happen(?: while i was (?:away|out|gone|asleep|at work))?|what did i miss|is anyone waiting(?: for (?:a reply|me|an answer))?|anyone waiting|(?:any )?(?:orders? )?to ship\??|any orders? (?:to ship|waiting|open|today)|"
                          r"stock (?:ok|okay|fine|alright)|(?:are we|is anything) (?:running )?(?:low|out)(?: on anything| of stock)?|are we running low on anything|come (?:va|andiamo|stiamo andando)|tutto (?:ok|bene|a posto)|novità|aggiornami|problemi|qualcosa da sapere|c'è qualcuno in attesa)\W*$", re.I)
    SOLD_HOW_MANY = re.compile(r"\b(?:how many|quant[ei])\s+(?P<what>[a-zà-ú][a-zà-ú0-9 \-]{2,30}?)\s+(?:did we sell|have we sold|sold|were sold|abbiamo venduto|venduti|vendute)(?:\s+(?P<when>this week|today|so far|yesterday|in total|questa settimana|oggi|ieri|in totale))?\W*$|\bwhen did we last sell (?:a |an |the )?(?P<what2>[a-zà-ú][a-zà-ú0-9 \-]{2,30}?)\W*$", re.I)
    STORE_OPEN = re.compile(r"^\W*(?:can you |could you |please |puoi )?(?P<verb>open|start|launch|turn on|close|stop|shut|apri|avvia|chiudi)\s+(?:up |down )?(?:the |my |our |il |lo |la )?(?:practice |test |fake |training |online )?(?:store|shop|negozio|bottega)\b", re.I)
    STORE_STOCK = re.compile(r"\b(?:what(?:'s| is| do we have| do i have) (?:in |the |our |my )?stock|stock (?:levels?|list|situation|status)|how many .{2,30}? (?:do (?:we|i) have|are left|in stock|left)|list (?:the |our |my )?products|(?:our|my) (?:products|catalogue|catalog)|cosa (?:abbiamo|c'è) in magazzino|quant[ei] .{2,30}? (?:abbiamo|restano|rimangono))\b", re.I)
    STORE_DAY = re.compile(r"\b(?:(?:run|simulate|start|do|play|fai)\s+(?:a |one |another |the next |un |un altro |\d+ |two |three |five |seven )?(?:more )?(?:practice |test |training )?(?:days?|giorn[oi])|(?:a |one |another )?(?:practice |test )?day (?:passes|goes by)|let (?:a|the) day pass|practice day|giorno di prova|passa un giorno)\b", re.I)
    STORE_REVIEW = re.compile(r"\b(?:review the (?:store|shop)|store review|what (?:do you|would you) (?:propose|suggest) (?:for|in) the (?:store|shop)|any proposals|what (?:should|needs to|do) (?:i|we) (?:do|fix) in the (?:store|shop)|cosa proponi per il negozio|controlla il negozio)\b", re.I)
    STORE_ORDERS = re.compile(r"\b(?:(?:open|pending|new|today'?s|latest|recent|last|unshipped|paid) orders|orders to ship|what (?:do i|should i|needs to be|do we) ship|which orders|show (?:me )?(?:the )?orders|ordini (?:da spedire|aperti|recenti|nuovi)|quali ordini)\b", re.I)
    STORE_LABELS = re.compile(r"\b(?:print|prepare|make|generate|create|give me|stampa|prepara|fammi)\b.{0,20}?\b(?:shipping labels?|labels?|packing slips?|etichette|bolle|lettere di vettura)\b|\b(?:shipping labels?|packing slips?|etichette)\b.{0,25}?\b(?:for|of|per)\b.{0,25}?\b(?:orders?|ordini|today|oggi)\b", re.I)
    LOGO_REQ = re.compile(r"\b(?:make|create|design|draw|do|prepare|generate|build|fai|crea|disegna|prepara)\b.{0,20}?\b(?:a |the |me a |me the |un |il |uno )?(?:new |nuovo )?logo\b(?:\s+(?:for|per)\s+(?:the |il |la |my |mio |nostro )?(?P<what>[^?.!]{2,60}))?|\bcan you (?:make|design|do|create) (?:a |the |me a )?logos?\b|\b(?:sai|puoi|riesci a) (?:fare|creare|disegnare) (?:un |il )?logo\b|\blogo\s+(?:for|per)\s+(?:the |il |la )?(?:shop|store|negozio)\b", re.I)
    BANNER_REQ = re.compile(r"\b(?:make|create|design|prepare|generate|do|fai|crea|prepara)\b.{0,12}?\b(?:a |the |me a |me the |an |un |una |il )?(?:new |nuovo |nuova )?(?:(?P<plat0>instagram|ig|facebook|fb)\s+)?(?P<kind>banner|cover|post image|image for (?:a |the )?post|graphic|visual|immagine|grafica|copertina|story|stories)\b(?:\s+(?:for|per)\s+(?P<platform>instagram|ig|facebook|fb|the shop|stories|story|the site|il sito)\b)?(?:.{0,10}?(?:saying|that says|with|about|con scritto|che dice|per)?\s*:?\s*[\"“']?(?P<text>[^\"”':]{4,120})[\"”']?)?\W*$", re.I)
    CODE_MAKE = re.compile(r"\b(?:make|create|add|set up|activate|open|start|launch|crea|attiva|fai|aggiungi|prepara)\s+(?:a |the |an |un |il |uno )?(?:new |nuovo )?(?:discount |promo |coupon |voucher )?(?:code|codice|coupon|voucher|buono)(?:\s+(?:sconto|promozionale|promo|di sconto))?\s*(?:called |named |chiamato |:)?\s*[\"“']?(?P<code>[A-Za-z][A-Za-z0-9\-]{2,19})[\"”']?\b.{0,40}?(?:(?P<pct>\d{1,2}(?:[.,]\d)?)\s*%|(?:€|eur|euro)?\s*(?P<fixed>\d{1,3}(?:[.,]\d{1,2})?)\s*(?:€|eur|euro|euros)?\s+(?:off|di sconto|sconto))(?:.{0,30}?\b(?:over|above|from|min(?:imum)?|sopra|da|oltre)\s*(?:i |gli |the )?(?:€|eur|euro)?\s*(?P<min>\d{1,4}(?:[.,]\d{1,2})?))?(?:.{0,30}?\b(?P<uses>\d{1,4})\s*(?:uses|times|customers|people|utilizzi|volte|usi))?"
                           r"|\b(?P<pct2>\d{1,2})\s*%\s*(?:off|discount|di sconto)\b.{0,30}?\b(?:with |using |code |codice |con il codice )+[\"“']?(?P<code2>[A-Z][A-Z0-9\-]{2,19})[\"”']?\b", re.I)
    CODE_OFF = re.compile(r"\b(?:switch off|turn off|disable|deactivate|stop|kill|remove|delete|end|expire|disattiva|spegni|elimina|togli|cancella|ferma)\s+(?:the |il |la )?(?:discount |promo )?(?:code|codice|coupon)(?:\s+sconto)?\s*[\"“']?(?P<code>[A-Za-z][A-Za-z0-9\-]{2,19})[\"”']?\W*$", re.I)
    CODE_Q = re.compile(r"\b(?:which|what|any|list|show|do we have|abbiamo|quali|che)\b.{0,20}?\b(?:discount |promo |active |live )?(?:codes?|coupons?|codici(?: sconto)?)\b.{0,20}?(?:active|live|running|do we have|are there|exist|attivi|\?|$)|\bcodes? (?:in use|usage|stats)\b|\bhow many (?:people|customers|orders) used (?:the )?code\b|\bquant[ei] (?:persone|clienti|ordini)? ?(?:hanno|ha) usato (?:il |lo )?codice\b|\bhow much .{0,20}\b(?:given away|discounts?|coupons?|codes?)\b.{0,20}(?:discounts?|codes?|coupons?|\?|$)|\bquanto .{0,20}\bsconti\b", re.I)
    GIFT_WRAP = re.compile(r"\b(?:add|offer|enable|activate|turn on|switch on|set up|start|aggiungi|attiva|offri|metti)\s+(?:a |the |an |un |una |il |la )?(?:gift[- ]?wrap(?:ping)?|confezione regalo|pacchetto regalo)(?: option| service| come opzione)?\b(?:.{0,30}?(?:at|for|a|per)\s*(?:€|eur|euro)?\s*(?P<price>\d{1,2}(?:[.,]\d{1,2})?))?|\bgift[- ]?wrap(?:ping)?\b.{0,20}?\b(?:at|for)\s*(?:€|eur|euro)?\s*(?P<price2>\d{1,2}(?:[.,]\d{1,2})?)\s*(?:€|eur|euros?)?\b.{0,20}?\b(?:add|offer|enable|turn on|please|option)\b|\b(?:add|offer|enable)\b.{0,10}?['\"“]?gift wrap['\"”]?\b.{0,20}?\b(?:option|at)\b.{0,10}?(?P<price3>\d{1,2}(?:[.,]\d{1,2})?)|\b(?:confezione|pacchetto) regalo\b.{0,30}?(?:€|eur|euro)?\s*(?P<price4>\d{1,2}(?:[.,]\d{1,2})?)", re.I)
    GIFT_WRAP_OFF = re.compile(r"\b(?:remove|disable|turn off|switch off|stop|drop|togli|disattiva|rimuovi|elimina)\s+(?:the |il |la )?(?:gift[- ]?wrap(?:ping)?|confezione regalo|pacchetto regalo)(?: option)?\W*$", re.I)
    NOTICE_SET = re.compile(r"\b(?:put|add|show|set|display|write|metti|mostra|scrivi|aggiungi)\s+(?:a |the |an |un |una |l')?(?:notice|banner|message|note|announcement|avviso|banner|messaggio|annuncio)\s+(?:on|at|to|across|in|sul|nel|nella|su|sulle|sulla)\s+(?:the |every |all |il |tutte le |ogni |lo )?(?:shop|store|site|website|pages?|home ?page|top|negozio|sito|pagine)\b.{0,20}?(?:saying|that says|reading|with|:|che dice|che dica|con)\s*[\"“']?(?P<text>[^\"”']{6,180})[\"”']?\W*$"
                            r"|\b(?:notice|banner|avviso|annuncio)\s*:\s*[\"“']?(?P<text2>[^\"”']{6,180})[\"”']?\W*$", re.I)
    NOTICE_OFF = re.compile(r"\b(?:remove|take down|delete|clear|hide|togli|rimuovi|cancella|elimina)\s+(?:the |il |la |l')?(?:notice|banner|announcement|avviso|messaggio|annuncio)(?: from the (?:shop|site|pages?)| dal (?:sito|negozio))?\W*$", re.I)
    OFFLINE_STOCK = re.compile(r"\b(?:i |we |ho |abbiamo )?(?:sold|gave away|gave|handed out|took|used|broke|dropped|venduto|regalato|dato via|rotto)\s+(?P<n>\d{1,3}|a|an|one|two|three|four|five|un|una|due|tre)\s+(?P<what>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?)\s+(?:at|on|to|for|in|as|al|a|per|come|during)\s+(?:the |a |my |our |il |la |un |una )?(?:market|fair|stall|event|street market|christmas market|mercato|mercatino|fiera|friend|friends|neighbou?r|mum|mom|dad|sister|brother|family|colleague|office|amico|amica|gift|present|photo shoot|shoot|sample|test|cash|hand|regalo)\b"
                               r"|\b(?:give|gave|regala|dai)\s+(?:the |a |an |il |la |un |una )?(?P<what2>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?)\s+to (?:my |a |our |un |una |mia |mio )?(?:friend|mum|mom|dad|sister|brother|neighbou?r|colleague|family|amico|amica|mamma|papà)\b.{0,40}?\b(?:free|gift|regalo|gratis|adjust|update|fix|take it off|off the stock|stock)\b"
                               r"|\b(?:someone|a customer|customer|the customer|a buyer|un cliente|una cliente)\s+(?:returned|sent back|gave back|ha restituito|ha reso|ha rimandato)\s+(?:the |a |an |il |la |un |una )?(?P<what3>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?)\b.{0,60}?\b(?:works? fine|works|is fine|it'?s fine|undamaged|intact|unused|like new|good condition|perfect|funziona|intatt[oa]|come nuov[oa]|resell|back on the shelf|restock)\b", re.I)
    STORE_SHIPPED = re.compile(r"^\W*(?:all |everything |tutto )?(?:shipped|sent|handed (?:to|over to) (?:the )?(?:courier|gls|carrier)|spedito|spediti|consegnato al corriere)\b.{0,30}$|^\W*(?:i (?:have |'ve )?)?(?:shipped|sent|posted) (?:all |every |the |today's )?(?:orders|parcels|packages|ordini|pacchi)\b.{0,30}$"
                               r"|^\W*(?:ok |done[,.]? |fatto[,.]? )?(?:i (?:have |'ve |just )?)?(?:shipped|sent|posted|dispatched|mailed) (?:everything|all of them|all of it|them all|the lot|all the orders|all|tutto|tutti)\b.{0,30}$|^\W*(?:all of them|they|everything|all orders|the orders|tutti gli ordini) (?:are|is|were|got|sono) (?:shipped|sent|out|gone|dispatched|on their way|with the courier|partiti|spediti)\b.{0,30}$|^\W*(?:ho spedito tutto|spedito tutto|tutto spedito|sono partiti tutti)\b.{0,30}$|^\W*(?:everything|all) (?:went|is) out (?:today|this morning|with (?:the )?(?:courier|gls))\b.{0,20}$", re.I)
    STORE_NAME_Q = re.compile(r"\b(?:what(?:'s| is) (?:the |my |our )?(?:store|shop) (?:called|name)|what(?:'s| is) the name of (?:the|my|our) (?:store|shop)|come si chiama il (?:negozio|shop))\b", re.I)
    ADD_PRODUCT = re.compile(r"^\W*(?:can you |could you |please |puoi )?(?:add|list|create|put up|aggiungi|metti|inserisci)\s+(?:a |the |this |new |a new |another |un |una |nuovo |nuova |un nuovo |una nuova )*(?:product|item|listing|article|prodotto|articolo)\s*[:\-–—]?\s*(?P<name>.+?)(?=\s*[,;:—]|\s+(?:that|which|it|costs?|costing|cost|at|sells?|selling|for|priced?|prezzo|costa|che)\b|\W*$)(?P<rest>.*)$", re.I | re.S)
    PRICE_CHANGE = re.compile(r"\b(?:lower|raise|increase|decrease|drop|cut|bump|change|set|update|put|move|abbassa|alza|metti|cambia|porta)\s+(?:the |il |la )?(?:price|prezzo)\s+(?:of|for|di|del|della|dello|dei)\s+(?:the |a |an |our |my |il |la |lo |i )?(?P<what>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?)\s+(?:to|at|a|down to|up to|→)\s*" + _MONEY.replace("(\\d", "(?P<v1>\\d")
                              + r"|\b(?:make|price|sell)\s+(?:the |il |la )?(?P<what2>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?)\s+(?:at |for |a )?" + _MONEY.replace("(\\d", "(?P<v2>\\d") + r"\s*(?:from now on|instead|d'ora in poi)\b"
                              + r"|\b(?:lower|raise|increase|decrease|drop|cut|bump|change|set|update|move|abbassa|alza|cambia|porta)\s+(?:the |il |la |our |my )?(?P<what3>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?)\s+(?:price|prezzo)\s+(?:to|at|a|down to|up to|→)\s*" + _MONEY.replace("(\\d", "(?P<v3>\\d")
                              + r"|\b(?:lower|raise|increase|decrease|drop|cut|bump|put|move|abbassa|alza|porta|metti)\s+(?:the |il |la |our |my )?(?P<what4>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?)\s+(?:to|at|a|down to|up to|→)\s*" + _MONEY.replace("(\\d", "(?P<v4>\\d") + r"(?:\s*(?:€|eur|euro|euros))?\W*$", re.I)
    STOCK_CHANGE = re.compile(r"\b(?:set|update|put|correct|metti|aggiorna)\s+(?:the )?stock\s+(?:of|for|di|del|della)\s+(?:the |il |la )?(?P<what>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?)\s+(?:to|at|a)\s+(?P<n>\d+)\b|\b(?:we |i )?(?:received|got|have got|restocked|arrived with|sono arrivat[ei])\s+(?P<n2>\d+)\s+(?:more |new |extra |altri |altre |nuov[ei] )?(?P<what2>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?)(?:\s+(?:today|from the supplier|dal fornitore|oggi))?\W*$|\b(?:the |il |la )?(?P<what3>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?)\s+(?:is|are|è|sono)\s+back(?: in stock)?\W+\s*(?P<n3>\d+)\s*(?:pieces|pcs|units|pezzi)?\W*$|\b(?:the |il |la )?(?P<what4>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?)\s+(?:is|are|è|sono)\s+back in stock\W*$", re.I)
    ORDER_MORE = re.compile(r"^\W*(?:please |can you |could you |let'?s |ok |ordina |)?(?:order|reorder|buy|get|restock|ordina|riordina|compra)\s+(?P<n>\d+)\s+(?:more |extra |new |pcs of |pieces of |units of |altri |altre |pezzi di )?(?P<what>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?)(?:\s+(?:from the supplier|dal fornitore|today|now|oggi|subito))?\W*$", re.I)
    # ---- shop sense: reviews, free shipping, couriers, hashtags, video ideas ----
    BAD_REVIEW = re.compile(r"\b(?:(?:1|one|2|two)[- ]star|bad|negative|angry|nasty|terrible|awful|unfair|brutta|negativa|cattiva)\s+(?:review|recensione|rating|feedback|stelle)\b|\brecensione (?:a |da |di )?(?:1|una|2|due) stell[ae]\b|\b(?:1|una) stella\b.{0,20}?\brecensione\b|\b(?:review|recensione)\b.{0,40}?\b(?:broke|broken|damaged|late|never arrived|rude|scam|fake|rotto|rotta|danneggiato|mai arrivato)\b|\b(?:left|gave|wrote|posted|ha lasciato|ha scritto)\s+(?:us |me |a |una )?(?:\d[- ]star|bad|negative|brutta) (?:review|recensione)\b", re.I)
    FREE_SHIP = re.compile(r"\b(?:should (?:i|we) (?:offer|do|give|have) free (?:shipping|delivery)|free (?:shipping|delivery) (?:threshold|or not|worth it|yes or no|good idea)|is free (?:shipping|delivery) (?:a good idea|worth it|smart)|(?:offer|give) free (?:shipping|delivery)\?|spedizione gratuita (?:sì o no|conviene|o no)|conviene (?:la |offrire la )?spedizione gratuita|soglia (?:per la |della )?spedizione gratuita)", re.I)
    COURIER = re.compile(r"\b(?:which|what|cheapest|best|good|migliore|quale|che)\b.{0,30}?\b(?:courier|carrier|shipping (?:company|service|provider)|corriere|spedizioniere)\b|\b(?:corriere|courier|carrier)\b.{0,20}?\b(?:cheap|cheapest|economico|conviene|use|choose|pick|recommend)\b|\bhow (?:do|should|can) (?:i|we) ship (?:the |my |our )?(?:orders|parcels|packages|products)\b|\b(?:cheapest|best|good|smartest) way to (?:ship|send|post|spedire)\b|\bcome spedisco\b", re.I)
    HASHTAGS = re.compile(r"\b(?:what|which|quali|che)\s+hashtags?\b|\bhashtags?\s+(?:for|per|to use|should (?:i|we) use|da usare)\b|\b(?:suggest|give me|dammi|suggerisci)\b.{0,12}?\bhashtags?\b", re.I)
    VIDEO_IDEAS = re.compile(r"\b(?:(?P<n>\d+|three|four|five|six|a few|some|un paio di|qualche|tre|cinque)\s+)?(?:tiktok|reels?|instagram|short|short-form|video|content|post)\s+(?:video |content |post )?(?:ideas?|idee|concepts?|hooks?|scripts?)\b|\b(?:ideas?|idee)\s+(?:for|per|di)\s+(?:a |some |\d+ |un |dei )?(?:tiktoks?|reels?|videos?|short videos?|video|contenuti)\b", re.I)
    TODO_ADD = re.compile(r"^\W*(?:please\s+|can you\s+|could you\s+)?(?:add|put|write|note|jot(?: down)?|aggiungi|segna|metti)\s+(?P<item>.+?)\s+(?:to|on|in|onto|into|alla|nella|sulla)\s+(?:my |the |our |our |la |mia )?(?:to-?do(?: list)?|list|lista|todo|tasks?|reminders?|note)s?\W*$"
                          r"|^\W*(?:remind me to|ricordami di|todo:|to-do:|to do:)\s*(?P<item2>.+?)\W*$", re.I)
    TODO_SHOW = re.compile(r"^\W*(?:what(?:'s| is) (?:on )?(?:my |the |our )?(?:to-?do|list|todo)(?: list)?|show (?:me )?(?:my |the |our )?(?:to-?do|todo|list)(?: list)?|(?:my |the )?(?:to-?do|todo)(?: list)?\??|my list|read (?:me )?(?:my |the )?(?:to-?do|list)|cosa (?:c'è|ho) (?:da fare|in lista)|(?:la )?(?:mia )?lista)\W*$", re.I)
    TODO_DONE = re.compile(r"^\W*(?:(?:mark |tick |check )?(?:off )?(?:number |item |#)?(?P<n>\d+)\s+(?:as )?(?:done|is done|finished|complete[d]?|fatto|fatta)|(?:done|finished|fatto)\s+(?:with )?(?:number |item |#)?(?P<n2>\d+)|(?:i(?:'ve| have)? )?(?:did|called|sent|finished|handled|ordered|paid|booked|emailed|wrote|bought|fixed|posted|shipped|answered|already did|took care of)\s+(?P<what>.{3,60}?)(?:,? (?:you can )?(?:tick|cross|mark|check|strike) (?:it|that)(?: off)?|,? (?:it's )?done)?)\W*$", re.I)
    TIME_IN = re.compile(r"\b(?:what(?:'s| is) the time|what time is it|che ora (?:è|sono)|che ore sono|current time|local time)(?: (?:now|right now|adesso|ora))?(?: (?:in|at|a) (?P<place>[a-zà-ú][a-zà-ú .'-]{1,40}?))?\W*$", re.I)
    TRANSLATE = re.compile(r"^\W*(?:can you |could you |please |per favore )?(?:translate|traduci(?:mi)?|traduce)(?:\s*[:\-–—]\s*|\s+)(?:this |that |it |the following |me |questo |questa )?"
                           r"(?:(?:into|in|to|a) (?P<lang>english|italian|german|french|spanish|portuguese|chinese|dutch|inglese|italiano|tedesco|francese|spagnolo|portoghese|cinese|olandese))?\s*[:\-–—]?\s*(?P<text>.+)?$", re.I | re.S)
    SAY_IN = re.compile(r"^\W*(?:how (?:do|would) (?:you|i) say|come si dice)\s+[\"“']?(?P<text>.+?)[\"”']?\s+in (?P<lang>english|italian|german|french|spanish|portuguese|chinese|dutch|inglese|italiano|tedesco|francese|spagnolo|portoghese|cinese|olandese)\W*$", re.I | re.S)
    LANGS = {"inglese": "English", "italiano": "Italian", "tedesco": "German", "francese": "French", "spagnolo": "Spanish", "portoghese": "Portuguese", "cinese": "Chinese", "olandese": "Dutch"}
    AWAY = re.compile(r"^\W*(?:i'?m |i am |sono |vado |going |off )?(?:off to|going to|heading to|away for|out for|back in|be back in|at|in|a|fuori per|torno tra|torno fra)\s+(?:lunch|dinner|the gym|gym|a meeting|meetings|work|bed|sleep|pranzo|cena|palestra|riunione|letto|(?:about |circa |~)?\d+ ?(?:min|minutes|minuti|h|hours?|ore|ora))\b.{0,40}?(?:back in|torno (?:tra|fra)|for)?\s*(?:about |circa |~)?(?P<n>\d+|an?|un[ao]?|half an|mezz')?\s*(?P<u>min(?:ute)?s?|minuti|h|hours?|ore|ora)?\W*$"
                      r"|^\W*(?:brb|bbl|afk|gotta go|i have to go|talk later|ci sentiamo dopo|a dopo|torno dopo)\W*$", re.I)
    HERE_Q = re.compile(r"^\W*(?:are you (?:there|here|awake|alive|online|around|still there|with me)|you there|ci sei|sei (?:lì|li|online|sveglio)|hello\?+|anyone (?:there|home))\W*$", re.I)
    LAST_DOC = re.compile(r"\b(?:send|resend|show|give|forward|mandami|rimandami|inviami)\b.{0,20}\b(?:last|latest|previous|that|the) (?:doc(?:ument)?|report|file|pdf|comparison|seller check|research)\b|\b(?:last|latest) (?:doc(?:ument)?|report|file) (?:again|please)\b|\bupload\b.{0,20}\b(?:doc(?:ument)?|report|file)\b.{0,20}\b(?:drive|google)\b", re.I)
    STORE_Q = re.compile(r"\b(?:how(?:'s| is| are) (?:the |my |our )?(?:practice |test |fake )?(?:store|shop|sales|orders|numbers)(?: doing| going)?|how(?:'s| is| was| did) (?:the |this |my |our )?(?:week|day|month|today|weekend|business|settimana|giornata)(?: going| go| been| doing)?(?=\W*$)|com'?è andata (?:la |questa )?(?:settimana|giornata|oggi)|come va (?:la |questa )?settimana|(?:store|shop) (?:numbers|stats|status|report)|come va (?:il negozio|lo shop)|quanti ordini)\b", re.I)
    DECIDED = re.compile(r"\b(?:what did we (?:decide|say|agree)|what was (?:decided|agreed)|remind me what we (?:decided|said|agreed)|cosa avevamo (?:deciso|detto)|what were (?:the|our) (?:conclusions|findings))\b.{0,12}?(?:about|on|for|regarding|su|per)\s+(?P<topic>.+?)\W*$", re.I)
    WHY_SLOW = re.compile(r"\bwhy (?:did|was|has) (?:the |that |my |your )?(?P<what>.{2,40}?) (?:take so long|so slow|take (?:that|so) much time|fail|not work|go wrong|break)\b|\bwhat (?:went wrong|happened) (?:with|on|during) (?:the |that )?(?P<what2>.{2,40}?)\W*$|\bperch[eé] (?:ci hai messo tanto|è andata male)\b", re.I)
    IT_BIZ = re.compile(r"\b(partita iva|p\.? ?iva|vat number|forfettario|forfetario|flat[- ]tax|regime forfettario|inps|ateco|codice ateco|scia|camera di commercio|registro (?:delle )?imprese|commercialista|oss\b|one[- ]stop[- ]shop|fattura elettronica|electronic invoic)\w*", re.I)
    TAX_ON = re.compile(r"\b(?:how much )?(?:tax(?:es)?|imposte|tasse)\b.{0,30}?(?:on|su|for|per)\s*" + _MONEY + r"\s*(?:of |di |in )?(?:sales|revenue|turnover|income|fatturato|vendite|incassi)?", re.I)
    RETURNS_Q = re.compile(r"\b(?:customer|client|buyer|cliente)\b.{0,40}?\b(?:refund|return|rimborso|reso|money back)\b.{0,60}?\b(?:used|worn|opened|damaged by|after \d+ days|late|too late|no receipt|without (?:the )?box|usato|aperto|in ritardo)\b|\b(?:do i have to|must i|am i obliged to|devo)\b.{0,20}?\b(?:refund|accept the return|rimborsare|accettare il reso)\b", re.I)
    OPINION = re.compile(r"\b(?:what do you think(?: about| of)?|what(?:'s| is) (?:your (?:take|opinion|view)|better)|which (?:is|one is|would you) (?:better|pick|choose|recommend)|should i (?:use|go with|pick|choose)|would you (?:recommend|suggest)|is it worth|che ne pensi|cosa ne pensi|secondo te|meglio)\b", re.I)
    VS = re.compile(r"\b(?P<a>[a-z0-9][a-z0-9 .'+-]{1,30}?)\s+(?:vs\.?|versus|or|o|oppure)\s+(?P<b>[a-z0-9][a-z0-9 .'+-]{1,30}?)(?=[\s?.!,]|$)", re.I)

    WRITE_DESC = re.compile(r"\b(?:write|draft|make|create|give|scrivi|scrivimi|fammi)\b.{0,20}?\b(?:product )?(?:description|descrizione|listing text|product text|blurb|copy)\b.{0,20}?\b(?:for|of|about|per|di)\s+(?:a |an |the |our |my |un |una |il |la )?(?P<what>.+?)(?:,\s*(?P<lines>\d+)\s*(?:lines?|righe|sentences?|frasi))?\W*$", re.I)
    NAME_SHOP = re.compile(r"\b(?:what (?:should|could|do) i (?:name|call)|name ideas? for|names? for|suggest (?:a )?names?|come (?:chiamo|lo chiamo)|nome per)\b.{0,20}?\b(?:shop|store|brand|business|negozio|marchio)\b", re.I)
    LAUNCH_LIST = re.compile(r"\b(?:make|write|give|prepare|build|fammi|scrivi)\b.{0,12}?\b(?:to-?do|todo|check-?list|task list|plan)\b.{0,30}?\b(?:launch|launching|opening|open|go live|lancio|apertura|aprire)\b", re.I)
    MAIL_CODE = re.compile(r"\b(?:check|look (?:in|at)|read|open|controlla|guarda)\b.{0,12}?\b(?:my |the |your |la |il )?(?:e-?mail|gmail|inbox|posta|mail)\b.{0,30}?\b(?:code|codice|verification|verifica|otp|link|conferma|confirmation)\b|\b(?:verification|confirmation) (?:code|link|mail|email)\b.{0,20}?\b(?:e-?mail|gmail|inbox|posta|arrived|check)\b", re.I)

    def __init__(self, memory=None, mind=None, library=None, inbox=None, store=None, log=None, planner=None):
        from .advice import Advice
        from .selftalk import SelfTalk
        self.advice = Advice(store=store, inbox=inbox, memory=memory)
        self.selftalk = SelfTalk(store=store, inbox=inbox, memory=memory, mind=mind)
        self.last_reply = None
        self.last_design = None                                                  # what "make it blue" / "I like the badge" refer to
        self.selftalk.last_reply = lambda: self.last_reply
        self.planner = planner
        self.memory = memory
        self.mind = mind
        self.library = library
        self.inbox = inbox
        self.store = store
        self.log = log or (lambda kind, **f: None)

    # ---- entry --------------------------------------------------------------------------------
    GREET = re.compile(r"^\W*(hi|hello|hey|yo|ciao|buongiorno|buonasera|good (morning|afternoon|evening)|morning|evening)\b[\s,!.]*(there|bot|mate|man)?[\s,!.]*(how'?s it going|how are you|how are things|what'?s up|come va|tutto bene|all good)?\W*$", re.I)

    def reply(self, text):
        """The direct answer, or a dict {"customer": <their message>} / {"todo": [...], "text": ...} for the agent to act on, or None."""
        out = self._reply(text)
        if isinstance(out, str) and not re.search(r"^\W*(?:are you sure|sure\??|really\??|why\??|what else|and the |what about|ok do it|do it|too expensive|no time)", (text or "").lower()):
            self.last_reply = ((text or "").strip(), out)                   # so “are you sure about that?” / “why?” / “and the mug?” know what 'that' was
        return out

    def note_reply(self, text, out):
        """Core calls this for answers it produced itself (brain, status…) so 'are you sure?' covers them too."""
        if isinstance(out, str) and out and not re.search(r"^\W*(?:are you sure|sure\??|really\??)", (text or "").lower()):
            self.last_reply = ((text or "").strip(), out)

    def _reply(self, text):
        t = (text or "").strip()
        if not t or t.startswith("/"):
            return None
        low = t.lower()
        e = self.echo_test(t)                                          # "answer with 1234ABC if you got this", "reply OK", "are you there?" — a line check, not a job
        if e:
            return e
        if self.GREET.match(t):
            return self.greet()
        if self.CAN_DO.search(t) and not re.search(r"\b(alone|on your own|by yourself|without me)\b|\b(when|if|with|about|for the shop|while)\b.{0,40}?\b(customer|angry|rude|shop|store|order|refund|me)\b", low):
            return self.can_do()
        if self.BYE.match(t) and len(low.split()) <= 8:
            return self.bye()
        if self.THANKS.match(t):
            return "You're welcome. I'm here when you need the next thing."
        if self.TODAY.search(t):
            return self.today()
        st_ = self.selftalk.reply(t)                                    # about me and about judgment: 'what are you doing?', 'why did you propose…', 'if you were me…'
        if st_:
            return st_
        q = self.quick(t)                                              # to-do, clock, opinions — also answered while I'm busy
        if q is not None:
            return q
        m = self.CUSTOMER.search(t) or (self.CUSTOMER_FWD.match(t) if not re.search(r"\b(should (?:i|we)|do (?:i|we)|can (?:i|we)|what (?:do|should|can) (?:i|we)|how (?:do|should|can) (?:i|we)|is (?:it|that)|devo|posso)\b|\?\s*$", t, re.I) else None)
        if m:
            adv = self.advice.reply(t, only=self.advice.SITUATIONS)     # "a customer wants an invoice / asks where it's made" → guidance first; forwarding the message still gets a draft
            if adv:
                return adv
            return {"customer": self._customer_text(t, m), "photo": bool(re.search(r"\b(photo|picture|image|foto|pic)s?\b", t, re.I))}
        m = self.MATHS.match(t)
        if m:
            r = self.maths(m)
            if r:
                return r
        if self.THANK_NOTE.search(t):
            return self.thank_note(t)
        if self.CANCEL_HOW.search(t):
            return self.cancel_how(t)
        m = self.DOMAIN_Q.search(t)
        if m:
            return {"domain": (m.group("dom") or m.group("dom2")).lower()}
        if self.COMPLAINTS_Q.search(t) and self.inbox is not None and not re.search(r"https?://|\b(handle|deal with|respond|answer|reply|gestire|rispondere)\b", low):
            return self.complaints(t)
        if self.FREE_RETURNS.search(t):
            return self.free_returns(t)
        if self.FIRST_CUST.search(t):
            return self.first_customers(t)
        m = self.ADS_BUDGET.search(t)
        if m and not re.search(r"https?://", t):
            return self.ads_budget(_num(m.group("amt")) if m.group("amt") else None, t)
        if re.search(r"^\W*(?:ads?|advertising|marketing) budget\W*$|\bhow much (?:should|do|could) (?:i|we) (?:spend|put|invest|budget) (?:on|in|for) (?:ads|advertising|marketing|meta ads|facebook ads|instagram ads|tiktok ads|google ads|promotion)\b|\bwhat(?:'s| is) a (?:good|sensible|reasonable) (?:ads?|advertising|marketing) budget\b|\bshould (?:i|we) (?:run|start|do|try) ads\b|\bquanto (?:spendere|investire) in pubblicità\b", low) and not re.search(r"https?://", t):
            return self.ads_budget(None, t)
        if re.search(r"^\W*(?:ok,? |yes,? |please |go on,? )?(?:prepare|set up|start|launch|make|do|write|plan|prepara|avvia) (?:the |an? |my |our )?(?:first )?(?:ad test|ads? test|test (?:ad|campaign)|ad campaign|ads campaign|campaign|meta ad|tiktok ad|ads)\b.{0,30}$", low):
            return self.ad_test()
        if re.search(r"^\W*(?:show|give|send) me (?:the |my |all (?:the )?|any )?(?:drafts?|replies|customer (?:drafts?|replies)|pending (?:drafts?|replies)|inbox|waiting messages?)\W*$|^\W*(?:what(?:'s| is) )?(?:in the )?inbox\W*$|\bshow (?:me )?(?:the )?(?:drafts?|replies) (?:again|waiting)\b", low) and self.inbox is not None:
            return self.show_drafts()
        m = re.match(r"^\W*(?:ok,? |yes,? |please |go on,? )?(?:add|make|create|list|set up|prepare|aggiungi|crea)\s+(?:the |that |this |a |il |quel )?(?:bundle|kit|set|pack|combo)\b(?:\s*[:\-–—]?\s*(?P<a>[a-zà-ú][a-zà-ú0-9 ]{2,40}?)\s*\+\s*(?P<b>[a-zà-ú][a-zà-ú0-9 ]{2,40}?))?\W*(?:(?:at|for|a)\s+" + _MONEY.replace("(\\d", "(?P<price>\\d") + r")?\W*$", low)
        if m and self.store is not None:
            return self.make_bundle(m.group("a"), m.group("b"), _num(m.group("price")) if m.group("price") else None)
        m = self.VAT_ON.search(t)
        if m and not re.search(r"\b(register|number|partita|threshold|oss)\b", low):
            return self.vat_on(_num(m.group("amt") or m.group("amt2")), m.group("what") or "", t)
        if self.BIO_Q.search(t) and not re.search(r"https?://|\bwebsite\b", low):
            return self.shop_bio(t)
        m = self.WRITE_PAGE.search(t)
        if m and not re.search(r"https?://|\bwebsite\b|\bsito\b", low):
            return self.write_page((m.group("kind") or m.group("kind2")).lower(), t)
        m = self.CAPTIONS.search(t)
        if m and not re.search(r"https?://", t):
            return self.captions(m.group("what"), m.group("n"), t)
        st = self.store_talk(t)                                        # the practice shop in plain words (open, stock, prices, labels…)
        if st is not None:
            return st
        sense = self.shop_sense(t)                                     # bad review, free shipping, couriers, hashtags, video ideas
        if sense is not None:
            return sense
        adv = self.advice.reply(t)                                     # incidents and decisions a shopkeeper meets (lost parcel, chargeback, wholesale, influencer…)
        if adv is not None:
            return adv
        if self.PRICE.search(t) or (self.COST.search(t) and re.search(r"\b(price|charge|sell|margin|markup|prezzo)\b", low)):
            p = self.pricing(t)
            if p:
                return p
        m = self.SHIP_OK.search(t)
        if m:
            return self.shipping_ok(_num(m.group(1) or m.group(2)), t)
        if self.START.search(t) and re.search(r"\b(sell|selling|shop|store|online|business|vendere|negozio|dropship)", low):
            return self.start_plan(t)
        return None

    ECHO = re.compile(r"^\W*(?:hello|hi|hey|ciao|test|testing|ping|please|ok)?[\s,!.:-]*(?:(?:can you |could you |just |please )?(?:answer|reply|respond|write|say|type|send|echo|repeat|write back|rispondi|scrivi)(?: me| back| to me| to this| to this (?:mail|email|message))?\s*(?:with|only|just|the word|the code|exactly|con|solo)?\s*(?:(?P<q>[\"“'‘«])(?P<quoted>[^\"”'’»]{1,40})[\"”'’»]|(?P<word>[A-Za-z0-9][A-Za-z0-9_#!-]{0,15}))\s*(?:(?:if|when|once|so i know|so that i know|to confirm|to show|to prove|se|quando)\b.{0,80})?)\W*$", re.I)
    ALIVE = re.compile(r"^\W*(?:hello|hi|hey|ciao|test|testing)?[\s,!.]*(?:are you (?:there|alive|awake|up|online|working|on|receiving|getting this|reading this)|(?:do|did|can) you (?:get|read|receive|see|hear) (?:me|this|my (?:mail|email|message)s?)|(?:is )?(?:this|the bot|the line|it) (?:working|alive|on|up)|anyone there|(?:this is a |just a )?(?:test|line check|ping|check)|ci sei|sei (?:vivo|online|sveglio)|mi (?:senti|leggi|ricevi)|funzioni|ping)\W*(?:\?|!)*\W*$", re.I)

    def echo_test(self, t):
        """A line check in plain words → the literal reply. Never treated as a research job."""
        low = t.lower()
        if re.search(r"https?://|\b(customer|order|refund|price|supplier|seller|research|find|search|document|doc|website|post)\b", low):
            return None
        if len(low.split()) > 18:
            return None
        m = self.ECHO.match(t)
        if m:
            code = (m.group("quoted") or m.group("word") or "").strip(" .!?")
            has_cond = bool(re.search(r"\b(if|when|once|so i know|so that i know|to confirm|to show|to prove|se|quando)\b", low))
            skip = {"me", "back", "now", "soon", "later", "this", "that", "it", "please", "asap", "with", "only", "here", "something", "anything", "hello", "hi", "to"}
            plain_ok = bool(m.group("quoted")) or has_cond or re.fullmatch(r"(?:ping|pong|ok|okay|yes|test|received|ricevuto|[A-Z0-9]{2,16}|\d{2,16})", code)
            if code and code.lower() not in skip and plain_ok:
                return f"{code}\n(Got your message — both lines work.)"
        if self.ALIVE.match(t) and not self.HERE_Q.match(t):                 # 'are you there?' has its own richer answer (here())
            return self.here()
        return None

    # ---- quick things (answered even in the middle of a job) --------------------------------------
    def quick(self, t):
        """To-do adds/list/done, 'what time is it in X', and A-vs-B opinions. None when it's not one of these."""
        low = t.lower()
        if self.CHECK_IN.match(t) and not re.search(r"https?://", t):
            return self.check_in(t)
        m = self.REMIND_AT.match(t)
        if m and self.memory is not None:
            return self.remind_at(m.group("when"), m.group("what"))
        m = re.match(r"^\W*(?:i (?:have to|need to|must|should|will|'ll)|we (?:have to|need to|must|should)|devo|dobbiamo)?\s*(?P<what>(?:call|phone|ring|e-?mail|mail|write to|pay|visit|chase|contact|chiamare|chiama|pagare|paga|scrivere a|scrivi a)\s+(?:the |il |la |lo |my |our )?[a-zà-ú][a-zà-ú0-9 \-']{2,50}?)\s+(?P<when>tomorrow(?: morning| afternoon| evening| at \d{1,2}(?::\d{2})?)?|domani(?: mattina| pomeriggio)?|tonight|stasera|on (?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)(?: morning| at \d{1,2})?|next week|la settimana prossima)\W*$", low)
        if m and self.memory is not None and not re.search(r"\?", t):
            return self.remind_at(m.group("when"), m.group("what"))
        m = self.TODO_ADD.match(t)
        if m and self.memory is not None:
            item = (m.group("item") or m.group("item2") or "").strip(" '\"“”.")
            if 2 <= len(item) <= 200 and not re.search(r"https?://", item):
                n = self.memory.add(item[0].upper() + item[1:])
                return {"todo_added": n, "text": f"Added to your to-do list as #{n}: {item[0].upper() + item[1:]}\n({len(self.memory.open_items())} open — say “my to-do list” to see it, “done {n}” when it's handled.)"}
        if self.TODO_SHOW.match(t) and self.memory is not None:
            items = self.memory.open_items()
            if not items:
                return "Your to-do list is empty. Say “add … to my list” and I keep it."
            return "Your to-do list:\n" + "\n".join(f"  {x['id']}. {x['text']}" for x in items) + "\nSay “done <number>” when one is handled."
        m = self.TODO_DONE.match(t) if not re.search(r"\?\s*$|^\W*(?:did|have|has|is|was|are|were) (?:we|i|it|the|you)\b", t, re.I) else None   # "did we ship 51001?" is a question, not a tick
        if m and self.memory is not None:
            n = m.group("n") or m.group("n2")
            x = None
            if n:
                x = self.memory.done(n)
            else:
                what = (m.group("what") or "").lower()
                words = [w for w in re.findall(r"[a-zà-ú]{4,}", what) if w not in ("with", "that", "this", "just", "already")]
                for it in self.memory.open_items():
                    if words and sum(w in it["text"].lower() for w in words) >= max(1, len(words) - 1):
                        x = self.memory.done(it["id"])
                        break
                if x is None and not words:
                    return None
            if x:
                left = len(self.memory.open_items())
                return f"Ticked off: {x['text']}" + (f" — {left} left." if left else " — list empty, nice.")
            return "I couldn't find that on the list. Say “my to-do list” and then “done <number>”." if n else None
        if self.HERE_Q.match(t):
            return self.here()
        if self.MAIL_CODE.search(t):
            return {"mail_code": True, "hint": self._sender_hint(t)}
        m = self.WRITE_DESC.search(t)
        if m and len(t.split()) <= 30:
            return self.description(m.group("what"), int(m.group("lines") or 0), t)
        if self.NAME_SHOP.search(t):
            return self.shop_names(t)
        if self.LAUNCH_LIST.search(t):
            return self.launch_list(t)
        if self.AWAY.match(t) and not re.search(r"\b(research|find|check|compare|build|write|look|cerca|trova)\b", low):
            return {"away": self._away_minutes(t), "text": self.away_line(t)}
        if self.LAST_DOC.search(t) or self.LAST_DOC_IT.search(t):
            return {"last_doc": True, "to_drive": bool(re.search(r"\b(drive|google|upload|carica)\b", low))}
        if self.PLATE.match(t):
            return self.plate()
        if self.INBOX_Q.search(t) and self.inbox is not None and not re.search(r"https?://|\b(abandoned|cart|newsletter|campaign|marketing)\b", low):
            return self.inbox_waiting()
        if self.STORE_Q.search(t) and self.store is not None:
            try:
                if self.STORE_NUM.search(t) and self.store.data.get("orders"):
                    return self.store_numbers(t)
                return self.store.numbers_text() + "\n(/store for the pages and the orders to ship)"
            except Exception:
                return None
        m = self.DECIDED.search(t)
        if m:
            return self.decided(m.group("topic"))
        m = self.WHY_SLOW.search(t)
        if m:
            return self.why_slow((m.group("what") or m.group("what2") or "").strip())
        m = self.TAX_ON.search(t)
        if m and re.search(r"\b(ital(?:y|ia)|forfettario|partita iva)\b", low):
            return self.tax_on(_num(m.group(1)))
        if self.IT_BIZ.search(t) and re.search(r"\?|\b(do i need|need|serve|devo|how|what|quanto|come|cosa)\b", low):
            return self.it_biz(t)
        if self.RETURNS_Q.search(t) and not self.CUSTOMER.search(t):       # "…what do I answer?" → a draft instead (inbox)
            return self.returns_rule(t)
        m = self.TIME_IN.search(t)
        if m:
            return self.clock(m.group("place"))
        mp = self.PAGE_LANG.search(t) if self.store is not None else None
        if mp and mp.group("page"):
            return self.page_language(mp.group("page"), mp.group("lang") or "", t)
        m = self.SAY_IN.match(t) or self.TRANSLATE.match(t)
        if m:
            lang = (m.group("lang") or "").lower()
            body = (m.group("text") or "").strip(" :\"“”'")
            if body:
                lang = self.LANGS.get(lang, lang.title() if lang else "")
                if not lang:                                                  # guess: Italian text → English, else → Italian
                    lang = "English" if re.search(r"\b(il|la|di|che|per|non|una|uno|sono|con|del|della|grazie|ciao|dove|quando)\b", body.lower()) else "Italian"
                return {"translate": body, "to": lang}
        if self.OPINION.search(t) or self.VS.search(t) and re.search(r"\?$", t.strip()):
            op = self.opinion(t)
            if op:
                return op
        return None

    @staticmethod
    def _sender_hint(t):
        m = re.search(r"\b(?:from|da|di)\s+([a-z0-9][a-z0-9.-]{2,30})\b", t.lower())
        if m and m.group(1) not in ("the", "my", "your", "gmail", "email", "mail", "inbox"):
            return m.group(1)
        m = re.search(r"\b(shopify|etsy|ebay|amazon|vinted|tiktok|instagram|facebook|meta|paypal|stripe|aliexpress|alibaba|cj|wix|canva|pinterest|x|twitter|linkedin|google|apple)\b", t.lower())
        return m.group(1) if m else ""

    def _fact_lines(self, what):
        """Facts the owner or the shop already gave about a product — the only material a description may use."""
        facts = []
        try:
            p = self.store.find_product(what) if self.store is not None else None
            pw = [w for w in re.findall(r"[a-z]{4,}", p["name"].lower()) if w not in ("with", "pack")] if p else []
            ww = [w.rstrip("s") for w in re.findall(r"[a-z]{4,}", what.lower())]
            # the request's own head noun (last word: "cork SANDAL") must be in the product name — "cork" alone is not the same product
            if p and ww and any(ww[-1] == w.rstrip("s") for w in pw) and sum(w.rstrip("s") in ww for w in pw) >= max(1, len(pw) // 2):
                facts.append(p.get("short") or p["name"])
                facts += [d for d in p.get("details", [])[:4] if d.lower()[:25] not in (p.get("short") or "").lower()]
        except Exception:
            pass
        try:
            for r in (self.memory.notes(what, limit=2) if self.memory else []):
                if r.get("kind") in ("research", "summary", "study", "learned"):
                    facts.append(r["text"][:200])
        except Exception:
            pass
        return facts

    def description(self, what, lines, full_text):
        """'write me a product description for a cork sandal, 2 lines' — from the facts I have; never invented specs."""
        what = what.strip(" .,'\"")
        given = re.search(r"^(.*?)[,;:\-–—]\s*(?:it'?s|they'?re|it is|made (?:of|from|in)|features?|with|has|comes? with)\b\s*(.{6,160})$", what, re.I)
        if given:                                                         # "linen apron, it's made of washed linen with two pockets"
            what, extra = given.group(1).strip(" ,"), given.group(2).strip(" .")
        else:
            extra = ""
        lines = lines or 3
        facts = self._fact_lines(what)
        if extra:
            facts.append(extra)
        text = ""
        if self.planner is not None and self.planner.installed():
            try:
                text = self.planner.chat("You write short, honest product descriptions for a small online shop. Use ONLY the facts given; no prices, no delivery promises, no health or 'best' claims, no invented materials.",
                                         f"Product: {what}\nFacts:\n" + ("\n".join(f"- {f}" for f in facts) if facts else "- (none beyond the name)") + f"\nWrite {lines} short sentence(s), plain words, no hashtags, no emoji.",
                                         max_tokens=60 * lines + 40, temperature=0.3, timeout=120).strip().strip('"“”')
            except Exception:
                text = ""
        if text and re.search(r"[$€£]\s?\d|\d\s?(?:€|eur)|\b(free shipping|guaranteed|best|cures?|100 ?%)\b|ships? (in|within)", text, re.I):
            text = ""                                                     # the model slipped in a price/claim → fall back to the template
        note = ""
        if not text:
            core = what[0].upper() + what[1:]
            fl = [f for f in facts if len(f) < 140][:max(1, lines - 1)]
            if fl:
                first = fl[0].rstrip(".")
                text = f"{core} — {first}." + (" " + " ".join(f.rstrip('.') + "." for f in fl[1:]) if fl[1:] else "")
            else:
                text = f"{core} — made for everyday use, in a simple design that goes with anything."
            text += " Tell us which one you'd like and we prepare it with care."
            note = "\n(Plain version — my thinking model is off, or I have no facts on it yet. Give me 2–3 facts — material, size, what makes it different — and I rewrite it.)" if not facts else "\n(Built only from the facts I have on it. Add a detail and I rewrite it.)"
        return f"Description for {what}:\n{text}{note}"

    def shop_names(self, t):
        """'what should I name my shop? it sells cork sandals' → 6 name ideas built from what it sells + how to check them."""
        m = re.search(r"\b(?:sells?|selling|for|vende|di)\s+(?:my |our |the )?([a-z][a-z \-]{2,40}?)(?:\s+online|\s*[,.?!]|$)", t, re.I)
        what = (m.group(1).strip() if m else "").lower()
        words = [w for w in re.findall(r"[a-z]{3,}", what) if w not in ("shop", "store", "online", "products", "things", "stuff", "and", "the")]
        core = (words[0] if words else "shop").rstrip("s")
        core2 = (words[1] if len(words) > 1 else "").rstrip("s")
        cap = core.capitalize(); cap2 = core2.capitalize()
        ideas = [f"{cap}&Co", f"Casa {cap}", f"{cap} Studio", f"The {cap} Room", f"Ciao {cap}", f"{cap}{cap2 or 'Lab'}", f"Piccolo {cap}", f"{cap} Milano"]
        ideas = list(dict.fromkeys(i for i in ideas if len(i) <= 18))[:6]
        return (f"Name ideas for a shop that sells {what or 'this'}:\n" + "\n".join(f"  • {i}" for i in ideas) +
                "\nHow to pick: say it out loud (easy to spell over the phone?), then check in this order — .com/.it domain free, Instagram and TikTok handle free, "
                "no identical trademark (EUIPO search), no famous brand inside the name. Tell me your favourite two and I check the handles and domains for you.")

    def launch_list(self, t):
        """'make a to-do list for launching the store next monday' → the launch checklist, on the to-do list, in order."""
        when = re.search(r"\b(next (?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|week|month)|tomorrow|this (?:week|weekend|friday)|on \w+day|in \d+ days?|lunedì|domani)\b", t, re.I)
        when = when.group(0) if when else "launch day"
        todo = ["Final check of every product page: photos, honest description, price, stock, options",
                "Shipping set: prices per country, free-shipping threshold, delivery days written on the shipping page",
                "Legal pages live: terms, privacy, returns (14-day EU withdrawal), contact with a real address and email",
                "Test order end to end with a real card (then refund it): checkout, confirmation mail, order in admin",
                "Payment methods on: card + PayPal; confirm the payout account",
                "Launch posts drafted for Instagram/TikTok (3 posts + 1 story) — I draft, you approve",
                "Customer replies ready: shipping times, returns, 'where is my order' — I answer from the policy, you approve",
                f"{when.capitalize()}: open the shop, publish post 1, watch the first orders and messages together"]
        return {"todo": todo, "text": f"Launch list for {when} — in the order I'd do it, and it's on your to-do list now:\n" +
                "\n".join(f"{i + 1}. {s}" for i, s in enumerate(todo)) + "\nTell me which ones you want me to do (2, 3, 6 and 7 are mine to prepare)."}

    # ---- Italian business basics (rules of thumb, always "confirm with a commercialista") -----------
    IT_NOTE = "\n(Rules of thumb from the official rules as I know them — confirm the numbers with a commercialista before you file anything.)"

    def it_biz(self, t):
        low = t.lower()
        if re.search(r"partita iva|p\.? ?iva|vat number", low) and re.search(r"\b(need|serve|devo|do i|necessary|required|without|senza|start|open|aprire)\b", low):
            return ("Yes — for a shop that is open all the time (your own site or a marketplace storefront) Italy treats selling as a continuous business, so you need a "
                    "Partita IVA from the first sale. The famous “€ 5,000 a year without Partita IVA” does not exist for selling goods: that threshold is for occasional freelance services (INPS gestione separata). "
                    "Only truly occasional sales (a few used items of your own, no stock, no ads) are exempt.\n"
                    "What opening it means: Partita IVA with ATECO 47.91.10 (retail via internet), Registro Imprese, SCIA to the Comune (SUAP), INPS Gestione Commercianti — a commercialista does it all in about a week, "
                    "typically € 300–600 for the set-up and € 800–1,500 a year to keep the books. Regime forfettario (see below) is the usual choice for a small shop." + self.IT_NOTE)
        if re.search(r"forfettario|forfetario|flat[- ]tax", low):
            return ("Regime forfettario for an online shop: allowed up to € 85,000 revenue a year; no VAT charged to customers and none reclaimed; taxable income = revenue × 40 % (the coefficient for retail); "
                    "on that you pay a flat 5 % for the first 5 years of a new business, then 15 %. On top come INPS Gestione Commercianti contributions: a fixed minimum of roughly € 4,600 a year "
                    "(you can ask for a 35 % reduction under forfettario) plus about 24 % on income above ~€ 18,500. Example: € 20,000 sales → € 8,000 taxable → € 400 tax (5 %) + INPS ≈ € 3,000 with the reduction." + self.IT_NOTE)
        if re.search(r"\binps\b", low):
            return ("INPS for an online shop = Gestione Commercianti: a fixed minimum contribution of about € 4,600 a year even with tiny sales (reduced by 35 % on request if you're in forfettario), "
                    "plus roughly 24 % of business income above the minimum base (~€ 18,500). It's the biggest fixed cost of a small shop in Italy — plan for it from month one." + self.IT_NOTE)
        if re.search(r"\boss\b|one[- ]stop[- ]shop", low):
            return ("OSS (One Stop Shop) matters once your sales to consumers in OTHER EU countries pass € 10,000 a year in total: above that you charge the customer's country VAT and declare it through one quarterly OSS return "
                    "in Italy instead of registering in every country. Under € 10,000 you keep Italian VAT (or none, in forfettario). Note: forfettario sellers who cross € 10,000 of EU distance sales still have to apply destination VAT via OSS." + self.IT_NOTE)
        if re.search(r"ateco", low):
            return "ATECO for an online shop: 47.91.10 — “commercio al dettaglio di qualsiasi tipo di prodotto effettuato via internet”. Dropshipping uses the same code. Handmade goods you make yourself add the artisan code for the craft." + self.IT_NOTE
        if re.search(r"fattura elettronica|electronic invoic", low):
            return "Electronic invoicing (fattura elettronica via SdI) is mandatory for all Partita IVA holders in Italy, forfettario included. For consumer sales on your own shop you issue a daily 'corrispettivo' instead of an invoice unless the customer asks for one." + self.IT_NOTE
        if re.search(r"commercialista", low):
            return "A commercialista for a small online shop costs about € 800–1,500 a year (forfettario, few invoices) — online ones (Fiscozen, Flextax, Taxfix-style) sit at the low end. Worth it from day one: the INPS and forfettario rules have traps." + self.IT_NOTE
        return None

    def tax_on(self, amount):
        taxable = amount * 0.40
        return (f"On {_eur(amount)} of sales in regime forfettario: taxable income = 40 % = {_eur(taxable)}; flat tax 5 % = {_eur(taxable * 0.05)} in the first 5 years (15 % = {_eur(taxable * 0.15)} after). "
                f"Separately, INPS Gestione Commercianti asks a fixed minimum of about € 4,600 a year (≈ € 3,000 with the 35 % forfettario reduction) whatever you sell — so at small volumes INPS, not tax, is the real cost. "
                f"Outside forfettario you'd pay VAT 22 % on sales plus IRPEF (23 % upward) on the real profit." + self.IT_NOTE)

    def returns_rule(self, t):
        low = t.lower()
        if re.search(r"\b(used|worn|opened|usato|aperto|without (?:the )?box)\b", low):
            return ("EU rule (Italy included): within 14 days of delivery the customer can withdraw for any reason and you must refund within 14 days of getting the goods back — even if the item was used. "
                    "BUT you may deduct the loss in value caused by handling beyond what a shop would allow (worn outside, washed, scratched). Two exceptions where you can refuse: sealed hygiene goods that were unsealed "
                    "(cosmetics, earbuds, underwear) and made-to-order items. If they say it's faulty, that's the 2-year legal guarantee instead: repair/replace first, refund if that fails.\n"
                    "What I'd do: ask for photos, refund the price minus a fair deduction (say 20–30 % for clear use), explain it in one calm sentence. Want me to draft that reply?")
        if re.search(r"\b(after \d+ days|late|too late|in ritardo)\b", low):
            return ("After the 14-day withdrawal window you're not obliged to take a change-of-mind return — unless your own returns page promises more (a 30-day policy binds you). "
                    "A faulty item is different: the 2-year legal guarantee applies whenever the defect shows up. Many small shops still accept a late return as store credit — cheap goodwill. Want me to draft the reply?")
        if re.search(r"\bdamaged by\b", low):
            return ("Damage the customer caused is not covered by withdrawal or guarantee — you can refuse the refund. Damage in transit is your risk until delivery: refund or replace, then claim from the courier. "
                    "Ask for photos of the item and the box before deciding. Want me to draft the reply?")
        return ("Refunds in the EU, in one breath: 14 days to withdraw for any reason (refund within 14 days of return, you may deduct for use beyond trying it), 2-year legal guarantee for defects (repair/replace, then refund), "
                "transit damage is on you until delivery, sealed hygiene goods and custom items are excluded from withdrawal. Tell me the exact case and I draft the reply.")

    def here(self):
        """'are you there?' → yes, plus what I'm doing — the honest one-liner an assistant gives."""
        try:
            if self.mind and self.mind.job:
                return "Yes, here — " + self.mind.status_line()
        except Exception:
            pass
        bits = []
        try:
            n = len(self.inbox.items("new")) if self.inbox else 0
            if n:
                bits.append(f"{n} customer message(s) wait for your tap")
        except Exception:
            pass
        try:
            k = len(self.memory.open_items()) if self.memory else 0
            if k:
                bits.append(f"{k} open to-do(s)")
        except Exception:
            pass
        return "Yes, here and free." + (" " + " · ".join(bits) + "." if bits else "") + " What do you need?"

    @staticmethod
    def _away_minutes(t):
        low = t.lower()
        m = re.search(r"(\d+|an?|un[ao]?|half an|mezz')\s*(min(?:ute)?s?|minuti|h|hours?|ore|ora)\b", low)
        if m:
            n = m.group(1)
            n = 30 if n.startswith(("half", "mezz")) else 1 if n in ("a", "an", "un", "una", "uno") else int(n)
            return n * 60 if m.group(2).startswith(("h", "or")) else n
        return {"lunch": 60, "pranzo": 60, "dinner": 90, "cena": 90, "gym": 90, "palestra": 90, "meeting": 60, "riunione": 60, "work": 300, "bed": 480, "sleep": 480, "letto": 480}.get(
            next((w for w in ("lunch", "pranzo", "dinner", "cena", "gym", "palestra", "meeting", "riunione", "work", "bed", "sleep", "letto") if w in low), ""), 45)

    def away_line(self, t):
        mins = self._away_minutes(t)
        span = f"{mins // 60} h" if mins >= 120 else f"{mins} min" if mins < 60 else "1 h"
        busy = ""
        try:
            if self.mind and self.mind.job:
                busy = f" I keep going on “{self.mind.job['goal'][:50]}” and the result waits here."
        except Exception:
            pass
        return f"Enjoy — I'll count on about {span}.{busy} If nothing is running I use the time to study (PDFs, business videos) and I only ping you for something urgent. Say hi when you're back."

    def decided(self, topic):
        """'what did we decide about shipping prices?' → my notes and lessons on it, dated — not a fresh guess."""
        topic = topic.strip(" ?.!")
        out = []
        try:
            for r in (self.memory.notes(topic, limit=3) if self.memory else []):
                out.append(f"• {r['t'][:10]} ({r.get('kind', 'note')} on {r.get('topic', '')[:40]}): {r['text'][:220]}")
        except Exception:
            pass
        try:
            from . import mind as _m
            words = set(re.findall(r"[a-z0-9]{3,}", topic.lower()))
            for j in _m._load(_m.LESSONS)[-40:]:
                hay = (j.get("goal", "") + " " + j.get("outcome", "")).lower()
                if words and sum(w in hay for w in words) >= max(1, len(words) - 1):
                    out.append(f"• {j.get('t', '')[:10]} job “{j.get('goal', '')[:50]}”: {j.get('outcome', '')[:200]}")
        except Exception:
            pass
        try:
            docs = [d for d in (self.library.recent(30) if self.library else []) if all(w in d.get("title", "").lower() for w in topic.lower().split()[:2])]
            for d in docs[:2]:
                out.append(f"• {str(d.get('t', ''))[:10]} document: {d.get('title', '')} (/library)")
        except Exception:
            pass
        if not out:
            return f"I have nothing written down about “{topic}” — we never settled it with me, or it was before my notes. Want me to look into it now?"
        return f"What I have on “{topic}”:\n" + "\n".join(dict.fromkeys(out[:6])) + "\nIf that's not what you meant, tell me the angle."

    def why_slow(self, what):
        """'why did the seller check take so long yesterday?' → the reflected job: time, snags, lesson."""
        try:
            from . import mind as _m
            recs = _m._load(_m.LESSONS)
        except Exception:
            recs = []
        words = set(re.findall(r"[a-z0-9]{3,}", what.lower())) - {"the", "that", "this", "job", "task", "yesterday", "today", "last"}
        kinds = {"seller": "seller_check", "sellers": "seller_check", "check": "seller_check", "research": "research", "comparison": "compare", "compare": "compare", "website": "build_site", "site": "build_site", "video": "watch", "summary": "summarize"}
        want_kind = next((kinds[w] for w in words if w in kinds), None)
        cands = [r for r in recs if (want_kind and r.get("kind") == want_kind) or (words and any(w in r.get("goal", "").lower() for w in words))]
        if not cands:
            return f"I can't find a job like “{what}” in my journal — say 'what did you do today' or /lessons and I'll show what I have."
        r = cands[-1]
        mins = r.get("seconds", 0) / 60
        snags = [s for s in r.get("snags", []) if s]
        why = ("; ".join(snags[:3]) if snags else "no snags noted — it was simply the amount of pages to read (each listing means the page, its reviews and a social page)")
        return (f"The {r.get('kind', 'job')} “{r.get('goal', '')[:60]}” on {r.get('t', '')[:10]} took {mins:.0f} min" + (" and ran late" if r.get("late") else "") +
                f". What slowed it: {why}. Lesson I kept: {r.get('lesson') or 'none'}. Next time say a time limit and I trim the checks to fit.")

    CITY_TZ = {"milan": "Europe/Rome", "milano": "Europe/Rome", "rome": "Europe/Rome", "roma": "Europe/Rome", "italy": "Europe/Rome", "italia": "Europe/Rome",
               "london": "Europe/London", "londra": "Europe/London", "uk": "Europe/London", "england": "Europe/London", "paris": "Europe/Paris", "parigi": "Europe/Paris", "berlin": "Europe/Berlin", "berlino": "Europe/Berlin", "germany": "Europe/Berlin",
               "madrid": "Europe/Madrid", "spain": "Europe/Madrid", "lisbon": "Europe/Lisbon", "lisbona": "Europe/Lisbon", "portugal": "Europe/Lisbon", "amsterdam": "Europe/Amsterdam", "athens": "Europe/Athens", "istanbul": "Europe/Istanbul", "moscow": "Europe/Moscow",
               "new york": "America/New_York", "nyc": "America/New_York", "ny": "America/New_York", "boston": "America/New_York", "miami": "America/New_York", "toronto": "America/Toronto", "chicago": "America/Chicago", "texas": "America/Chicago", "dallas": "America/Chicago",
               "denver": "America/Denver", "los angeles": "America/Los_Angeles", "la": "America/Los_Angeles", "san francisco": "America/Los_Angeles", "california": "America/Los_Angeles", "seattle": "America/Los_Angeles", "vancouver": "America/Vancouver",
               "mexico city": "America/Mexico_City", "mexico": "America/Mexico_City", "sao paulo": "America/Sao_Paulo", "brazil": "America/Sao_Paulo", "buenos aires": "America/Argentina/Buenos_Aires",
               "dubai": "Asia/Dubai", "delhi": "Asia/Kolkata", "mumbai": "Asia/Kolkata", "india": "Asia/Kolkata", "bangkok": "Asia/Bangkok", "singapore": "Asia/Singapore", "hong kong": "Asia/Hong_Kong", "hongkong": "Asia/Hong_Kong",
               "shanghai": "Asia/Shanghai", "beijing": "Asia/Shanghai", "shenzhen": "Asia/Shanghai", "guangzhou": "Asia/Shanghai", "yiwu": "Asia/Shanghai", "china": "Asia/Shanghai", "cina": "Asia/Shanghai", "taipei": "Asia/Taipei", "seoul": "Asia/Seoul", "tokyo": "Asia/Tokyo", "japan": "Asia/Tokyo",
               "sydney": "Australia/Sydney", "melbourne": "Australia/Melbourne", "australia": "Australia/Sydney", "auckland": "Pacific/Auckland", "cairo": "Africa/Cairo", "lagos": "Africa/Lagos", "johannesburg": "Africa/Johannesburg", "nairobi": "Africa/Nairobi",
               "utc": "UTC", "gmt": "UTC"}

    def clock(self, place):
        """'what time is it in shenzhen?' → the local time there and the gap to the owner's clock (supplier chat hours matter)."""
        import zoneinfo
        here = _dt.datetime.now().astimezone()
        if not place:
            return f"It's {here:%H:%M} here ({here:%A %d %B})."
        key = place.strip().lower().rstrip("?.! ")
        tz = self.CITY_TZ.get(key)
        if not tz:
            cand = [z for z in zoneinfo.available_timezones() if key.replace(" ", "_") in z.lower()]
            tz = sorted(cand, key=len)[0] if cand else None
        if not tz:
            return f"I don't know the time zone of “{place.strip()}” offhand — tell me the country or a big city near it."
        there = here.astimezone(zoneinfo.ZoneInfo(tz))
        diff = (there.utcoffset() - here.utcoffset()).total_seconds() / 3600
        gap = "same time as here" if abs(diff) < 0.01 else f"{abs(diff):g} h {'ahead of' if diff > 0 else 'behind'} you"
        day = "" if there.date() == here.date() else (" (already tomorrow there)" if there.date() > here.date() else " (still yesterday there)")
        tip = ""
        if 0 <= there.hour < 8 or there.hour >= 22:
            tip = " — it's night there, so don't expect a reply from a supplier before their morning."
        elif 9 <= there.hour < 18 and there.weekday() < 5:
            tip = " — office hours there, a good moment to message a supplier."
        return f"In {place.strip().title()} it's {there:%H:%M}{day} — {gap}{tip}"

    OPINIONS = {
        ("shopify", "woocommerce"): ("Shopify if you want to be selling this week and not touch servers: hosted, ~€ 27–36/month plus 2 % transaction fee unless you use Shopify Payments, apps for everything, support 24/7. "
                                     "WooCommerce if you already have WordPress or want zero monthly licence: free plugin, but you pay hosting (~€ 5–15/month), you update and back it up yourself, and every extra (subscriptions, advanced shipping) is a paid plugin. "
                                     "For a first dropshipping store with no tech person: Shopify. For a content site that also sells a few things: WooCommerce."),
        ("shopify", "etsy"): ("Etsy first if your products are handmade/vintage/craft supplies: buyers are already there, listing costs $0.20 and ~6.5 % + payment fees per sale, no marketing needed at the start. "
                              "Shopify when you want your own brand, repeat customers and no marketplace rules — but then you bring the traffic yourself. Many small sellers do both: Etsy for discovery, Shopify for the brand."),
        ("aliexpress", "cj dropshipping"): ("AliExpress is the widest catalogue with the slowest and least predictable shipping (10–30 days to Italy unless the seller uses AliExpress Standard/Choice). "
                                            "CJ Dropshipping has fewer products but its own warehouses (some in Europe), quality checks and 5–12 day lines — better for a store that has already found its 3–5 products. "
                                            "Start on AliExpress to test, move winners to CJ or a European wholesaler."),
        ("dropshipping", "own stock"): ("Dropshipping = no money tied up in stock, but thin margins (10–25 %) and you don't control shipping or quality. Own stock = better margins (40–60 %), fast shipping, your own packaging — but cash upfront and the risk of unsold boxes. "
                                        "Sensible path: dropship to find what sells, then buy 50–100 units of the winners from the same or a European supplier."),
        ("instagram", "tiktok"): ("TikTok gives reach for free right now — a new account can get 10k views from zero if the first 2 seconds are good; Instagram is better for trust and repeat buyers (profile as a shop window, DMs, saved posts). "
                                  "For a new small store: make short vertical videos for TikTok and repost them as Reels — one production, two channels."),
        ("paypal", "stripe"): ("Offer both. Stripe is what Shopify Payments uses underneath: cards, Apple/Google Pay, ~1.5 % + € 0,25 for EU cards. PayPal costs more (~3.4 % + € 0,35) but many Italian buyers only trust PayPal on an unknown shop — not offering it loses sales."),
        ("amazon", "own store"): ("Amazon = traffic and trust from day one, but 15 % referral fee, FBA storage costs, price wars and no customer relationship. Own store = your margin and your customers, but you buy every visitor with ads or content. "
                                  "For a brand you plan to keep: own store, with Amazon as a second channel later."),
        ("facebook ads", "google ads"): ("Google Ads catches people already searching for the product (high intent, good for known items like “cork sandals”); Facebook/Instagram ads create the want (good for new/impulse products under € 40, needs video). "
                                         "Under € 300/month budget: pick one, test 2 weeks, read the numbers — don't split it."),
    }
    ALIASES = {"woo": "woocommerce", "woo commerce": "woocommerce", "wordpress": "woocommerce", "ali": "aliexpress", "ali express": "aliexpress", "cj": "cj dropshipping", "cjdropshipping": "cj dropshipping",
               "ig": "instagram", "insta": "instagram", "tik tok": "tiktok", "own shop": "own store", "my own store": "own store", "own website": "own store", "own site": "own store", "my own site": "own store",
               "stock": "own stock", "holding stock": "own stock", "inventory": "own stock", "buying stock": "own stock", "meta ads": "facebook ads", "fb ads": "facebook ads", "instagram ads": "facebook ads", "adwords": "google ads"}

    def opinion(self, text):
        low = text.lower()
        names = set()
        for key in list(self.ALIASES) + [n for pair in self.OPINIONS for n in pair]:
            if re.search(r"\b" + re.escape(key) + r"\b", low):
                names.add(self.ALIASES.get(key, key))
        for pair, ans in self.OPINIONS.items():
            if set(pair) <= names:
                return f"My take on {pair[0].title()} vs {pair[1].title()}: {ans}\nIf you tell me the product and budget I can make it more precise."
        if len(names) == 1:
            n = next(iter(names))
            for pair, ans in self.OPINIONS.items():
                if n in pair:
                    other = pair[1] if pair[0] == n else pair[0]
                    return f"On {n.title()} (compared with {other.title()}, the usual alternative): {ans}"
        return None

    # ---- answers -------------------------------------------------------------------------------
    def can_do(self):
        shop = " · the practice shop (/store)" if self.store is not None else ""
        return ("Here's what I do, in plain words:\n"
                "• Look things up on the web and hand you a proper document (links, pictures, key points) — “research X, write me a document”\n"
                "• Check sellers deeply before you buy — page, reviews, social pages, complaints, shipping — “is this seller ok? <link>” or “find me reliable suppliers of X”\n"
                "• Compare suppliers side by side — “compare suppliers of X”\n"
                "• Read a page or a video for you — paste a link\n"
                "• Answer customers — forward me their message, I draft the reply, you approve\n"
                "• Draft social posts and rehearse posting on a practice network — “rehearse posting about X”\n"
                "• Build a full website for a business — “build a website for <place>” (and train on random real places)\n"
                "• Price things — “how much should I charge for X that costs me Y?”\n"
                "• Keep your to-do list — “add … to my list”, “my to-do list”, “done 2” — and tell you the time in a supplier's city\n"
                "• Give you my take — “shopify vs woocommerce?”, “is 9 € shipping to Germany normal?”, “should I offer free shipping?”, “a customer left a 1-star review, what do I do?”, “which courier is cheapest?”\n"
                "• Run the practice shop with you in plain words — “open the practice store”, “what's in stock?”, “lower the price of the lamp to 35”, “add a new product: …”, “print the shipping labels”, “all shipped”\n"
                "• Social bits — “what hashtags for eco products?”, “3 tiktok video ideas for the cork case”\n"
                "• Study on my own when you're away (PDFs, business videos → my Drive library)" + shop + "\n"
                "Pace words work: “make it quick, 10 minutes” or “I'm at work 5 hours, take it slow”. Say “stop” or “what are you doing?” any time.")

    def greet(self):
        """Hello with a one-line status: what's waiting, what I did last — so the owner knows where we stand."""
        hour = _dt.datetime.now().hour
        hello = "Good morning!" if 5 <= hour < 12 else "Good afternoon!" if 12 <= hour < 18 else "Good evening!"
        bits = []
        try:
            new = len(self.inbox.items("new")) if self.inbox else 0
            if new:
                bits.append(f"{new} customer message(s) wait for your tap (/inbox)")
        except Exception:
            pass
        try:
            from . import mind as _m
            last = (_m._load(_m.LESSONS) or [None])[-1]
            if last:
                bits.append(f"last job: {last.get('kind', '?')} “{last.get('goal', '')[:40]}” ({'done' if last.get('delivered') else 'not delivered'})")
        except Exception:
            pass
        try:
            n = len(self.memory.open_items()) if self.memory else 0
            if n:
                bits.append(f"{n} open to-do(s)")
        except Exception:
            pass
        return hello + " All good here." + (" " + " · ".join(bits) + "." if bits else "") + " What do you need — a search, a seller check, a document, a website, or just a question?"

    def bye(self):
        n = 0
        try:
            n = len(self.memory.open_items()) if self.memory else 0
        except Exception:
            pass
        tail = f" You have {n} open to-do(s); I'll keep studying quietly." if n else " I'll keep studying quietly and ping you only if something needs you."
        return "Alright — talk later." + tail

    def today(self):
        day = _dt.date.today().isoformat()
        parts = []
        try:
            from . import mind as _m
            jobs = [r for r in _m._load(_m.LESSONS) if r.get("t", "")[:10] == day]
            if jobs:
                parts.append(f"• {len(jobs)} job(s) finished: " + "; ".join(f"{j.get('kind', '?')} “{j.get('goal', '')[:50]}”" + ("" if j.get("delivered") else " (not delivered)") for j in jobs[-6:]))
            jl = [r for r in _m._load(_m.JOURNAL) if r.get("t", "")[:10] == day]
            if jl and not jobs:
                parts.append(f"• {len(jl)} step(s) worked today, last: {jl[-1].get('what', '')[:80]}")
        except Exception:
            pass
        try:
            docs = [d for d in (self.library.recent(20) if self.library else []) if str(d.get("t", ""))[:10] == day]
            if docs:
                parts.append("• documents written: " + "; ".join(d.get("title", "?")[:50] for d in docs[:5]))
        except Exception:
            pass
        try:
            notes = self.memory.notes(limit=30, days=1) if self.memory else []
            kinds = {}
            for r in notes:
                kinds.setdefault(r.get("kind", "note"), []).append(r.get("topic", ""))
            for k, topics in list(kinds.items())[:5]:
                parts.append(f"• {k}: " + "; ".join(dict.fromkeys(t[:40] for t in topics))[:160])
        except Exception:
            pass
        try:
            if self.inbox:
                new = len(self.inbox.items("new"))
                if new:
                    parts.append(f"• {new} customer message(s) waiting for your tap (/inbox)")
        except Exception:
            pass
        if not parts:
            return "Nothing finished yet today — no jobs, no documents. Give me something to do, or I'll study in the quiet time."
        return f"Today ({day}):\n" + "\n".join(parts)

    # ---- the practice store in plain words ----------------------------------------------------
    def store_talk(self, t):
        """'open the practice store', 'what's in stock?', 'lower the price of the lamp to 35', 'add a new product: …',
        'print the shipping labels', 'all shipped' → a store command or an owner change for core to run. None otherwise."""
        if self.store is None or re.search(r"https?://", t):
            return None
        low = t.lower()
        m = self.WHATIF.search(t)
        if m:
            return self.what_if(m)
        m = self.ORDER_Q.search(t)
        if m:
            r = self.order_info(int(m.group("n") or m.group("n2") or m.group("n3")), t)
            if r:
                return r
        m = self.AVAILABLE_Q.search(t)
        if m and not re.search(r"https?://|\b(domain|dominio|amazon|aliexpress|supplier)\b", low):
            r = self.available(m.group("what") or m.group("what2") or "", back=bool(m.group("what2")))
            if r:
                return r
        m = self.PRICE_SHIP_Q.search(t)
        if m:
            r = self.price_with_shipping(int(m.group("qty") or m.group("qty2") or 1), m.group("what") or m.group("what2") or "", m.group("where") or m.group("where2") or "")
            if r:
                return r
        m = self.WEIGHT_Q.search(t)
        if m and re.search(r"\b(parcel|package|box|shipment|pacco|weigh|heavy|weight|pesa|peso)\b", low):
            r = self.parcel_weight(int(m.group("qty") or 1), m.group("what") or "")
            if r:
                return r
        if self.REFUNDS_Q.search(t) and not re.search(r"\b(policy|how do i|how to|process|handle|rule|law|legge|come gestisco)\b", low):
            return self.refunds_list(t)
        m = self.SOLD_TODAY_Q.match(t)
        if m:
            return self.sold_today((m.group("when") or m.group("when2") or "today").lower())
        if self.ITEMS_TOTAL_Q.search(t):
            return self.items_total(t)
        if self.REORDER_LIST_Q.search(t) and not re.search(r"\bhow much should i order of\b|\bhow many .{2,30} should i order\b", low):
            return self.reorder_list()
        if self.TOP3_Q.search(t):
            return self.top3(t)
        if self.BEST_CUSTOMER_Q.search(t):
            return self.best_customer()
        if self.PRODUCT_FACT.search(t) and not re.search(r"https?://|\b(supplier|amazon|aliexpress|temu|competitor|our shop|the shop|website|domain|price|prices|pricing|charge|cost|costs|margin|stock|sold|sell|orders?|order of|customers? (?:says?|wrote)|post|caption|how much should|how many should|reorder|discount|€|euro)\b|\d+[.,]\d\d", low):
            r = self.product_fact(t)
            if r:
                return r
        m = self.COST_CHANGE.search(t)
        if m:
            what = next(g for g in (m.group("what"), m.group("what2"), m.group("what3"), m.group("what4"), m.group("what5"), m.group("what6"), m.group("what7")) if g)
            value = _num(next(g for g in (m.group("v1"), m.group("v2"), m.group("v3"), m.group("v4"), m.group("v5"), m.group("v6"), m.group("v7")) if g))
            p = self.store.find_product(what)
            if p and value > 0:
                return {"store_change": {"kind": "cost", "product": p["id"], "value": round(value, 2), "name": p["name"], "old": p.get("cost", 0), "price": p["price"]}}
        if re.search(r"\b(?:cheapest|least expensive|most expensive|priciest|lowest[- ]priced|highest[- ]priced|più economico|più caro|meno caro)\b.{0,15}?\b(?:product|item|thing|one|prodotto|articolo)\b|\bwhat(?:'s| is) (?:our|the|my) (?:cheapest|most expensive|priciest) (?:product|item)\b", low):
            prods = sorted(self.store.products(), key=lambda p: p["price"])
            if prods:
                dear = bool(re.search(r"\b(most expensive|priciest|highest|più caro)\b", low))
                p = prods[-1] if dear else prods[0]
                rest = ", ".join(f"{q['name'].split(' (')[0]} {_eur(q['price'])}" for q in (prods[-2::-1][:3] if dear else prods[1:4]))
                mg = (p["price"] - p.get("cost", 0)) / p["price"] * 100 if p["price"] else 0
                return (f"{'Most expensive' if dear else 'Cheapest'}: {p['name']} at {_eur(p['price'])} (cost {_eur(p.get('cost', 0))}, {mg:.0f} % margin, {p['stock']} in stock); then {rest}. " +
                        ("It carries the shop's profit per order — keep it in stock and in every post." if dear else
                         "Under € 15 it only pays as an add-on: show it in the cart (“add a toothbrush set for € 12,90”) and in bundles, not as the hero product."))
        if self.PUSH_Q.search(t):
            return self.push_pick(t)
        if re.match(r"^\W*(?:what|which|cosa|che)\s+(?:should|could|do|can) (?:i|we)\s+post\s+(?:today|now|tomorrow|this week|oggi|domani|questa settimana)\W*$|^\W*cosa (?:posto|pubblico|pubblichiamo) oggi\W*$", t, re.I):
            return self.post_today(t)
        m = self.ORDER_ACT.match(t)
        if m:
            return self.order_action(m.group("act").lower(), int(m.group("n")), (m.group("why") or "").strip(" ,.-—"))
        if self.SHIP_ALL.match(t):
            return {"store_cmd": "shipped_all"}
        if self.LATE_Q.search(t):
            return self.late_orders()
        m = self.WHO_BOUGHT.search(t)
        if m:
            r = self.who_bought(m.group("what"))
            if r:
                return r
        m = self.MARGIN_ON.search(t)
        if m and not re.search(r"\b(black friday|sale|saldi)\b", low):
            r = self.margin_on(m.group("what"))
            if r:
                return r
        m = self.SOLD_WHEN.search(t)
        if m:
            return self.sold_when((m.group("when") or "so far").lower())
        m = self.SOLD_HOW_MANY.search(t)
        if m:
            r = self.sold_how_many(m.group("what") or m.group("what2") or "", (m.group("when") or ("last" if m.group("what2") else "so far")).lower())
            if r:
                return r
        if self.STOCK_VALUE.search(t):
            return self.stock_value(t)
        m = self.OOS_SAY.search(t)
        if m:
            return self.out_of_stock_script(m.group("what") or "")
        if self.BANK_TRANSFER.search(t) and re.search(r"\?|\b(ok|okay|fine|safe|should|accept|posso|conviene|is that|va bene)\b", low) and not self.CUSTOMER.search(t):
            return self.bank_transfer(t)
        m = self.BULK_DISC.search(t)
        if m and not self.CUSTOMER.search(t):
            return self.bulk_discount(int(m.group("n") or m.group("n2")), m.group("what") or m.group("what2") or "")
        if self.FEES_PAID.search(t):
            return self.fees_paid(t)
        m = self.SET_FREE_SHIP.search(t)
        if m:
            return self.set_free_shipping(_num(m.group("amt") or m.group("amt2") or m.group("amt3") or m.group("amt4")))
        m = re.search(r"\b(?:set|make|change|put|charge|lower|raise|update|metti|cambia|porta)\s+(?:the )?(?:shipping|delivery|postage|spedizione)\s+(?:cost |price |fee )?(?:to|for|in|per|verso)\s+(?P<where>[a-zà-ú ]{2,25}?)\s+(?:to|at|a|→|=)\s*" + _MONEY.replace("(\\d", "(?P<v>\\d") +
                      r"|\b(?:shipping|delivery|spedizione)\s+(?:to|for|in|per)\s+(?P<where2>[a-zà-ú ]{2,25}?)\s*(?:should be|becomes|is now|at|=|:|→)\s*" + _MONEY.replace("(\\d", "(?P<v2>\\d") + r"\W*(?:from now on|d'ora in poi)?\W*$"
                      r"|\b(?:open|add|enable|start|offer|apri|aggiungi|attiva)\s+(?:shipping|delivery|deliveries|spedizioni?)\s+(?:to|for|in|per|verso)\s+(?P<where3>[a-zà-ú ]{2,25}?)(?:\s+(?:at|for|a)\s*" + _MONEY.replace("(\\d", "(?P<v3>\\d") + r")?\W*$", t, re.I)
        if m and not re.search(r"\bfree\b", low):
            where = (m.group("where") or m.group("where2") or m.group("where3") or "").strip().lower()
            code = next((c for w, c in (("italy", "IT"), ("italia", "IT"), ("germany", "DE"), ("germania", "DE"), ("france", "FR"), ("francia", "FR"), ("spain", "ES"), ("spagna", "ES"), ("switzerland", "CH"), ("svizzera", "CH"), ("the uk", "GB"), ("uk", "GB"), ("united kingdom", "GB"), ("england", "GB"), ("usa", "US"), ("the usa", "US"), ("america", "US"), ("united states", "US"),
                                         ("austria", "AT"), ("netherlands", "NL"), ("belgium", "BE"), ("portugal", "PT"), ("the rest of the eu", "EU"), ("rest of eu", "EU"), ("other eu", "EU"), ("eu", "EU"), ("europe", "EU"), ("europa", "EU"), ("norway", "NO"), ("canada", "CA")) if re.fullmatch(r"(?:the )?" + re.escape(w), where) or re.search(r"\b" + re.escape(w) + r"\b", where)), None)
            v = m.group("v") or m.group("v2") or m.group("v3")
            if code and v:
                return self.set_ship_price(code, round(_num(v), 2))
            if code and m.group("where3"):
                sug = {"CH": 19.90, "GB": 19.90, "US": 34.90, "NO": 19.90, "CA": 34.90}.get(code, 8.90)
                return (f"Opening shipping to {code}: what should the customer pay? A small parcel costs us about " + {"CH": "€ 20–25 (+ the buyer pays Swiss VAT on delivery)", "GB": "€ 20–25 (+ UK VAT/customs; under £ 135 you should collect UK VAT at checkout)", "US": "€ 40+ (customs form, 7–12 days)", "NO": "€ 20–25 (+ import VAT)", "CA": "€ 35+"}.get(code, "€ 9–13") +
                        f". Say “open shipping to {where} at {sug:.2f}” and I prepare it for your tap (checkout + shipping page).")
        m = self.WHY_NOBODY.search(t)
        if m:
            r = self.why_not_selling(m.group("what") or m.group("what0") or m.group("what00") or "")
            if r:
                return r
        m = self.PAGE_LANG.search(t)
        if m:
            return self.page_language(m.group("page") or "", m.group("lang") or "", t)
        m = self.REORDER_Q.search(t)
        if m:
            r = self.reorder_qty(m.group("what") or m.group("what2") or "")
            if r:
                return r
        m = self.PRICE_OK.search(t)
        if m:
            return self.price_ok(_num(m.group("amt")), m.group("what"), t)
        if self.SALE_Q.search(t) and not re.search(r"https?://|\b(code|codice|coupon|voucher|create|make|generate|crea)\b", low):
            return self.sale_prices(t)
        m = re.search(r"\b(?:how many|quant[ei])\s+(?P<what>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?)\s+(?:do (?:we|i) have|are (?:left|there)|left|in stock|abbiamo|restano|rimangono|ci sono)\b", t, re.I)
        if m and not re.search(r"\b(orders|sales|visitors|visits|customers|emails|messages|ordini|visite|clienti)\b", m.group("what"), re.I):
            p = self.store.find_product(m.group("what"))
            if p:
                flag = " — out of stock ⚠️" if p["stock"] == 0 else " ⚠️ low, reorder soon" if p["stock"] <= 3 else ""
                return f"{p['name']}: {p['stock']} in stock{flag} · {_eur(p['price'])} (cost {_eur(p.get('cost', 0))}). Say “how much should I order of the {m.group('what')}” for a reorder quantity."
        m = self.SELLOUT_Q.search(t)
        if m:
            return self.sell_out(m.group("what") or m.group("what2") or m.group("what3") or m.group("what4") or "")
        if self.SHIP_COST_Q.search(t) and not re.search(r"\b(cheapest|courier|corriere|packlink|poste|which|quale)\b", low):
            return self.ship_cost(t)
        if self.STORE_NUM.search(t) and not re.search(r"\b(what is a|what's a|define|meaning|mean|cos'è|explain)\b", low):
            return self.store_numbers(t)
        m = self.STORE_OPEN.match(t)
        if m:
            return {"store_cmd": "close" if re.match(r"(close|stop|shut|chiudi)", m.group("verb"), re.I) else "open"}
        if self.STORE_LABELS.search(t):
            return {"store_cmd": "labels"}
        if self.STORE_SHIPPED.match(t):
            return {"store_cmd": "shipped_all"}
        if self.STORE_ORDERS.search(t):
            return {"store_cmd": "orders"}
        if self.STORE_STOCK.search(t) and not re.search(r"\b(dead stock|stock photo|stock image|in stock\?? on|amazon|aliexpress|supplier)\b", low):
            return {"store_cmd": "stock"}
        if self.STORE_DAY.search(t):
            n = re.search(r"\b(\d|two|three|five|seven)\s+(?:more )?(?:practice |test )?(?:days|giorni)\b", low)
            words = {"two": "2", "three": "3", "five": "5", "seven": "7"}
            return {"store_cmd": f"day {words.get(n.group(1), n.group(1))}" if n else "day"}
        if self.STORE_REVIEW.search(t):
            return {"store_cmd": "review"}
        if self.STORE_NAME_Q.search(t):
            if re.search(r"\b(sells?|selling|vende|for|per)\b", low) and self.NAME_SHOP.search(t) is None:
                return self.shop_names(t)                                    # "come si chiama il negozio? vende sandali" → name ideas
            return f"The practice shop is called “{self.store.data.get('name', 'Green Nest')}”. Say “name ideas for a shop that sells …” if you want a name for a real one."
        m = self.PRICE_CHANGE.search(t)
        if m:
            what = (m.group("what") or m.group("what2") or m.group("what3") or m.group("what4") or "").strip()
            value = _num(m.group("v1") or m.group("v2") or m.group("v3") or m.group("v4") or "0")
            p = self.store.find_product(what)
            if not p:
                if m.group("what4") or re.search(r"\b(stock|shipping|threshold|budget|temperature|volume|alarm|timer)\b", what.lower()):
                    return None                                                   # "lower the shipping to 3" / "put the alarm at 7" are not price changes
                return f"I don't have a product like “{what}” in the shop. Products: " + ", ".join(x["name"] for x in self.store.products()) + "."
            if value <= 0:
                return None
            return {"store_change": {"kind": "price", "product": p["id"], "value": round(value, 2), "name": p["name"], "old": p["price"], "cost": p.get("cost", 0)}}
        m = re.search(r"\b(?:mark|set|put|flag|show|segna|metti)\s+(?:the |il |la |i |le )?(?P<what>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?)\s+(?:as |come )?(?:sold[- ]out|out of stock|unavailable|esaurit[oi]|non disponibile)\b|\b(?P<what2>[a-zà-ú][a-zà-ú0-9 \-]{2,40}?)\s+(?:is|are|sono|è)\s+(?:now )?(?:sold[- ]out|out of stock|finished|gone|finit[oi]|esaurit[oi])\b.{0,20}?\b(?:update|mark|set|fix|the (?:shop|store|page)|aggiorna)\b", t, re.I)
        if m:
            p = self.store.find_product(m.group("what") or m.group("what2") or "")
            if p:
                if p["stock"] == 0:
                    return f"{p['name']} already shows sold out (0 in stock) — the page takes e-mails for the restock. Say “we received N more …” when it's back."
                return {"store_change": {"kind": "stock", "product": p["id"], "value": 0, "name": p["name"], "old": p["stock"], "text": f"Mark {p['name']} sold out (stock {p['stock']} → 0; the page shows 'sold out' and stops taking orders)"}}
        d_last = getattr(self, "last_design", None)
        if d_last:
            m = re.match(r"^\W*(?:i (?:like|prefer|want|choose|pick|take|'ll take)|let's (?:go with|take|use)|go with|use|keep|choose|take|mi piace|prendo|scelgo|usa|prendiamo)\s+(?:the |number |option |il |la |lo |l')?(?P<pick>wordmark|badge|icon|monogram|circle|symbol|first|second|third|1|2|3|one|two|three|primo|secondo|terzo)\b", t, re.I)
            if m and d_last.get("kind") == "logo":
                pick = {"first": "wordmark", "1": "wordmark", "one": "wordmark", "primo": "wordmark", "second": "badge", "2": "badge", "two": "badge", "secondo": "badge", "monogram": "badge", "circle": "badge",
                        "third": "icon", "3": "icon", "three": "icon", "terzo": "icon", "symbol": "icon"}.get(m.group("pick").lower(), m.group("pick").lower())
                return {"design": {"kind": "logo_pick", "style": pick}}
            m = re.search(r"\b(?:make|do|paint|colou?r|try|fai|fallo|falla|prova)\s+(?:it|them|that|one|the (?:logo|banner|badge|icon|wordmark)|lo|la)?\s*(?:in |di |più )?(?P<col>blue|green|red|black|dark|navy|orange|pink|purple|violet|brown|teal|gold|yellow|grey|gray|terracotta|beige|blu|verde|rosso|nero|arancione|rosa|viola|marrone|oro|giallo|grigio)\b", t, re.I)
            if m:
                return {"design": {**d_last, "colour": m.group("col").lower(), "again": True}}
            m = re.search(r"\b(?:change|replace|swap|set|put|use|cambia|metti|scrivi)\s+(?:the )?(?:text|words|headline|title|wording|line|testo|titolo|scritta)\s+(?:to|with|into|in|con|a|:)\s*[\"“']?(?P<text>[^\"”']{3,120})[\"”']?\W*$", t, re.I)
            if m and d_last.get("kind") == "banner":
                return {"design": {**d_last, "text": m.group("text").strip(" .,:"), "again": True}}
            m = re.search(r"\b(?:make|do|same|one|version|now|fallo|falla|stesso)\b.{0,12}?\b(?:for|per|as (?:a|an)|in|come)\s+(?:the )?(?P<plat>instagram|ig|facebook|fb|story|stories|reel|square|quadrato|storia)\b\W*$", t, re.I)
            if m and d_last.get("kind") == "banner":
                plat = {"ig": "instagram", "fb": "facebook", "stories": "story", "reel": "story", "storia": "story", "square": "instagram", "quadrato": "instagram"}.get(m.group("plat").lower(), m.group("plat").lower())
                return {"design": {**d_last, "platform": plat, "again": True}}
            if re.match(r"^\W*(?:post it|publish it|post that|share it|use it for a post|pubblicalo|postalo)\W*$", t, re.I) and d_last.get("kind") == "banner":
                return {"design": {**d_last, "post": True}}
            if re.match(r"^\W*(?:put|use|show|add|mettilo|usalo|mettila)\b.{0,8}?\b(?:it|that|the logo|lo|la)?\b.{0,8}?\b(?:on|in|to|sul|nel|nello|sullo)\s+(?:the |il |lo )?(?:shop|store|site|website|header|practice shop|negozio|sito)\W*$", t, re.I) and d_last.get("kind") == "logo":
                return {"store_change": {"kind": "logo", "path": d_last.get("chosen") or ""}}
        if re.match(r"^\W*(?:remove|take|drop|togli|rimuovi)\s+(?:the |il )?logo\b.{0,12}?(?:from |dal |dallo |off )?(?:the )?(?:shop|store|site|header|negozio|sito)?\W*$", t, re.I) and self.store is not None:
            if self.store.data.get("logo"):
                return {"store_change": {"kind": "logo", "path": ""}}
            return "There's no logo on the shop header right now — it shows the name in text. Say “make a logo” → “I like the badge” → “put it on the shop” to add one."
        m = self.LOGO_REQ.search(t)
        if m and not re.search(r"\b(how (?:do|can|should) i|where (?:do|can) i|what (?:is|makes)|cost|price of a|hire|freelanc|fiverr|canva)\b", t, re.I):
            what = (m.groupdict().get("what") or "").strip(" ,.")
            return {"design": {"kind": "logo", "what": what}}
        m = self.BANNER_REQ.search(t)
        if m and not re.search(r"\b(how (?:do|can|should) i|what size|dimensions|pixels?)\b", t, re.I):
            plat = (m.group("platform") or m.group("plat0") or "").lower()
            plat = {"ig": "instagram", "fb": "facebook", "story": "story", "stories": "story", "the shop": "facebook", "the site": "facebook", "il sito": "facebook"}.get(plat, plat or "instagram")
            if "stor" in (m.group("kind") or "").lower():
                plat = "story"
            txt = (m.group("text") or "").strip(" ,.:-—")
            if re.fullmatch(r"(?:for |per )?(?:instagram|ig|facebook|fb|the shop|the site|il sito|stories|story)", txt, re.I):
                txt = ""
            return {"design": {"kind": "banner", "platform": plat, "text": txt}}
        m = self.CODE_OFF.search(t)
        if m and self.store.code(m.group("code")):
            return {"store_change": {"kind": "code", "code": m.group("code").upper(), "off": True}}
        m = self.CODE_MAKE.search(t)
        if m and (m.group("pct") or m.group("fixed") or m.group("pct2")):
            code = (m.group("code") or m.group("code2")).upper()
            pct = _num(m.group("pct") or m.group("pct2") or 0)
            fixed = _num(m.group("fixed") or 0)
            mn = _num(m.group("min") or 0)
            uses = int(m.group("uses")) if m.group("uses") else None
            if pct > 50:
                return f"{pct:g} % off is more than the whole margin on most products — I won't prepare that. 10–15 % is the usual size for a code; say “make a code {code} for 15 %”."
            return {"store_change": {"kind": "code", "code": code, "pct": pct, "fixed": fixed, "min": mn, "max_uses": uses}}
        m = self.GIFT_WRAP_OFF.search(t)
        if m:
            return {"store_change": {"kind": "gift_wrap", "active": False}}
        m = self.GIFT_WRAP.search(t)
        if m and not (t.rstrip().endswith("?") or re.match(r"^\s*(should|shall|do you think|is it worth|would it|could we|what if|dovrei|conviene)\b", t, re.I)):
            price = _num(next((g for g in (m.group("price"), m.group("price2"), m.group("price3"), m.group("price4")) if g), 2.9))
            return {"store_change": {"kind": "gift_wrap", "active": True, "price": price}}
        m = self.NOTICE_OFF.search(t)
        if m:
            return {"store_change": {"kind": "notice", "text": ""}}
        m = self.NOTICE_SET.search(t)
        if m:
            return {"store_change": {"kind": "notice", "text": (m.group("text") or m.group("text2")).strip(" :-–—\"“”'")}}
        if self.CODE_Q.search(t):
            codes = self.store.codes()
            if not codes:
                return "No discount codes exist yet. Say “make a code WELCOME10 for 10 % off” and I prepare it — codes show up as a field at checkout only once one is live."
            lines = []
            for c in codes:
                lines.append(f"• {c['code']}: " + (f"{c['pct']:g} % off" if c.get("pct") else f"{_eur(c.get('fixed', 0))} off") + (f" over {_eur(c['min'])}" if c.get("min") else "") +
                             f" — {'live' if c.get('active') else 'off'}, used {c.get('uses', 0)}×" + (f"/{c['max_uses']}" if c.get("max_uses") else ""))
            n = self.store.numbers()
            return "Discount codes:\n" + "\n".join(lines) + (f"\nGiven away so far: {_eur(n.get('discounts', 0))} on {n.get('code_orders', 0)} order(s)." if n.get("code_orders") else "")
        m = self.OFFLINE_STOCK.search(t)
        if m:
            what = (m.group("what") or m.group("what2") or m.group("what3") or "").strip()
            p = self.store.find_product(what)
            if p:
                n = m.group("n") or "1"
                n = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "un": 1, "una": 1, "due": 2, "tre": 3}.get(n.lower(), n)
                n = int(n)
                back = bool(m.group("what3"))
                new = p["stock"] + n if back else max(0, p["stock"] - n)
                why = (f"came back in good condition (stock {p['stock']} → {new}); it goes on the shelf again — if you refunded that customer, say “refund order <number>” so the books match"
                       if back else f"left the shelf outside the shop (sold offline / given away): stock {p['stock']} → {new}" +
                       ("; the money isn't in the shop's ledger, so profit here won't show it — note it for the tax books" if re.search(r"sold|venduto|market|mercatino|fiera|cash", low) else "; a gift costs you the purchase price " + _eur(p.get("cost", 0) * n)))
                return {"store_change": {"kind": "stock", "product": p["id"], "value": new, "name": p["name"], "old": p["stock"], "text": f"{p['name']}: {why}"}}
        m = self.STOCK_CHANGE.search(t)
        if m:
            what = (m.group("what") or m.group("what2") or m.group("what3") or m.group("what4") or "").strip()
            p = self.store.find_product(what)
            if not p:
                return None
            if m.group("what4") and not m.group("n3"):                        # "the lamp is back in stock" without a number → ask for it
                return f"Good — how many {p['name'].split(' (')[0]} came in? Say “the {what} is back in stock, 12 pieces” and I set the stock (it's {p['stock']} now)."
            n = int(m.group("n") or m.group("n2") or m.group("n3"))
            add = bool(m.group("n2")) or (bool(m.group("n3")) and p["stock"] > 0)   # "we received 20 more lamps" adds; "set stock of … to 20" sets; "back in stock, 12 pieces" on a sold-out item sets
            return {"store_change": {"kind": "stock", "product": p["id"], "value": p["stock"] + n if add else n, "name": p["name"], "old": p["stock"]}}
        m = self.ORDER_MORE.match(t)
        if m and not re.search(r"\b(labels?|boxes|tape|cards|samples?|domain|etichette|scatole)\b", low):
            p = self.store.find_product(m.group("what"))
            if p:
                return self.order_more(p, int(m.group("n")))
        m = self.ADD_PRODUCT.match(t)
        if m:
            name = re.sub(r"\s+", " ", m.group("name")).strip(" .,:;-–—\"'“”")
            rest = m.group("rest") or ""
            if len(name) < 3 or self.store.find_product(name) and self.store.find_product(name)["name"].lower() == name.lower():
                return None
            mc = self.COST.search(rest) or re.search(r"\b(?:cost|costs|costo|costa)\b\D{0,12}" + _MONEY, rest, re.I)
            mp = re.search(r"\b(?:sell(?:ing)?(?: it)?(?: at| for)?|price(?:d)?(?: at| of)?|list(?:ed)?(?: at)?|retail(?: at)?|vend(?:o|erlo)(?: a)?|prezzo(?: di)?|at|a)\s*" + _MONEY, rest, re.I)
            cost = _num(mc.group(1)) if mc else 0.0
            price = _num(mp.group(1)) if mp else 0.0
            if price and cost and abs(price - cost) < 0.01:                 # "at 24" matched the cost itself
                price = 0.0
            if not price and cost:
                price = round(cost * 3 + 0.49, 0) - 0.10                    # 3× landed, X,90 style — the owner can change it
                guessed = True
            else:
                guessed = False
            if not price:
                return f"To add “{name}” I need at least the selling price (and the cost, so I can watch the margin): e.g. “add product: {name}, costs me 8, sell at 24”."
            ms = re.search(r"\b(\d{1,4})\s*(?:in stock|pcs|pieces|units|pezzi|in magazzino)\b|\bstock\s*(?:of|:)?\s*(\d{1,4})\b", rest, re.I)
            stock = int(ms.group(1) or ms.group(2)) if ms else 10
            return {"store_change": {"kind": "product", "name": name[:80], "price": round(price, 2), "cost": round(cost, 2), "guessed": guessed, "stock": stock}}
        return None

    # ---- the store's own numbers, in answers -------------------------------------------------------------
    def _period(self, t):
        low = t.lower()
        day = self.store.data.get("day", 0)
        if re.search(r"\b(today|oggi)\b", low):
            return "today", lambda o: o.get("day") == day
        if re.search(r"\b(yesterday|ieri)\b", low):
            return "yesterday", lambda o: o.get("day") == day - 1
        if re.search(r"\b(last week|la settimana scorsa|previous week)\b", low):
            return "last week", lambda o: day - 14 < o.get("day", 0) <= day - 7
        if re.search(r"\b(this week|settimana|weekly|the week)\b", low):
            return "this week", lambda o: o.get("day", 0) > day - 7
        if re.search(r"\b(this month|mese|monthly)\b", low):
            return "this month", lambda o: o.get("day", 0) > day - 30
        return "so far", lambda o: True

    def store_numbers(self, t):
        st = self.store
        label, keep = self._period(t)
        orders = [o for o in st.data["orders"] if keep(o)]
        paid = [o for o in orders if o["status"] in ("paid", "shipped", "delivered")]
        low = t.lower()
        n = st.numbers()
        day = st.data.get("day", 0)
        if not st.data["orders"]:
            return "No orders yet in the practice store — it hasn't had a practice day. Say “run a practice day” and customers come (simulated), then ask me again."
        units = {}
        for o in paid:
            for l in o["lines"]:
                units[l["name"]] = units.get(l["name"], 0) + l["qty"]
        best = sorted(units.items(), key=lambda x: -x[1])
        rev = sum(o["total"] for o in paid)
        cogs = sum(l["qty"] * l.get("cost", 0) for o in paid for l in o["lines"])
        ship = sum(2.9 + 0.35 * sum(l["qty"] for l in o["lines"]) for o in paid)
        fees = sum(0.029 * o["total"] + 0.30 for o in paid)
        profit = rev - cogs - ship - fees
        visits = sum(v for d, v in st.data["visits"].items() if keep({"day": int(d)}))
        conv = (len(paid) / visits * 100) if visits else 0
        if re.search(r"\b(compared|vs\.?|versus|against|rispetto)\b", low):
            return self.week_compare()
        if re.search(r"\b(most (?:money|profit|profitable|margin)|highest[- ]margin|biggest earner|earns (?:the )?most|makes (?:the )?most)\b", low):
            gain = {}
            for o in paid:
                for l in o["lines"]:
                    gain[l["name"]] = gain.get(l["name"], 0) + l["qty"] * (l.get("price", 0) - l.get("cost", 0))
            rank = sorted(gain.items(), key=lambda x: -x[1])
            per_unit = sorted(((p["name"], p["price"] - p.get("cost", 0), (p["price"] - p.get("cost", 0)) / p["price"] * 100) for p in st.products() if p["price"]), key=lambda x: -x[1])
            if rank:
                k, v = rank[0]
                u = units.get(k, 0)
                return (f"Most money {label}: {k} — {_eur(v)} gross margin from {u} sold" + ((", then " + ", ".join(f"{a} {_eur(b)}" for a, b in rank[1:3])) if len(rank) > 1 else "") +
                        f". Per unit the best is {per_unit[0][0]} ({_eur(per_unit[0][1])} each, {per_unit[0][2]:.0f} %)" + (" — so pushing it is the fastest way to more profit." if per_unit[0][0] != k else " — same one; keep it in stock and on the feed.") )
            return ("No sales yet, so by margin per unit: " + ", ".join(f"{a} {_eur(b)} ({c:.0f} %)" for a, b, c in per_unit[:3]) +
                    f". {per_unit[0][0]} is the one to push once orders start.")
        if re.search(r"\b(spend|spent|pay|paid|speso|spendiamo)\b.{0,12}\b(shipping|postage|spedizion)", low):
            n_p = sum(sum(l["qty"] for l in o["lines"]) for o in paid)
            charged = sum(o.get("shipping", 0) for o in paid)
            return (f"Shipping {label}: we paid about {_eur(ship)} to the courier for {len(paid)} parcels ({n_p} items; practice figure € 2,90 + € 0,35 per item), customers paid {_eur(charged)} of it" +
                    (f" — so shipping cost us net {_eur(ship - charged)}" if ship > charged else " — covered") +
                    ((lambda k: f"; {k} order{'s' if k != 1 else ''} had free shipping.")(len([o for o in paid if o.get('shipping', 0) == 0])) if any(o.get("shipping", 0) == 0 for o in paid) else "."))
        if re.search(r"\b(spend|spent|pay|paid)\b.{0,12}\b(goods|stock|the goods|fees|payment fees)", low):
            return f"{label.capitalize()}: goods {_eur(cogs)}, payment fees {_eur(fees)}, shipping {_eur(ship)} — against {_eur(rev)} of sales from {len(paid)} orders."
        if re.search(r"\bhow many (?:customers|buyers|clients|clienti)\b|\bquanti clienti\b", low):
            emails = {}
            for o in paid:
                key = (o.get("customer") or {}).get("email") or (o.get("customer") or {}).get("name") or str(o["n"])
                emails[key] = emails.get(key, 0) + 1
            rep = sum(1 for v in emails.values() if v > 1)
            return (f"Customers {label}: {len(emails)} different people placed {len(paid)} orders" + (f"; {rep} came back for a second order — " + ("good sign." if rep else "") if rep else "; no repeat buyers yet — the thank-you card with a code is the cheapest fix.") +
                    (f" Countries: " + ", ".join(f"{c} {n}" for c, n in sorted(((c, sum(1 for o in paid if o.get('country') == c)) for c in {o.get('country') for o in paid}), key=lambda x: -x[1])[:4]) + "." if paid else ""))
        if re.search(r"\b(average (?:order|basket)|aov|scontrino medio)\b", low):
            if not paid:
                return f"No paid orders {label}, so no average basket yet."
            aov = rev / len(paid)
            items = sum(l["qty"] for o in paid for l in o["lines"]) / len(paid)
            return (f"Average order {label}: {_eur(aov)} ({items:.1f} items per order, {len(paid)} orders). "
                    + (f"Free shipping over {_eur(round(aov * 1.3 + 0.5) - 0.01)} would nudge it up; " if aov else "")
                    + "bundles (“mug + wraps”) are the other lever — say “should I offer free shipping?” for the threshold maths.")
        if re.search(r"\b(best[- ]?seller|top (?:product|seller)|più venduto)\b", low):
            if not best:
                return f"Nothing sold {label} yet."
            k, v = best[0]
            p = st.find_product(k)
            return (f"Best seller {label}: {k} — {v} sold" + (f" ({_eur(p['price'])}, {(p['price'] - p.get('cost', 0)) / p['price'] * 100:.0f} % margin, {p['stock']} left)" if p else "") +
                    (("; then " + ", ".join(f"{a} ×{b}" for a, b in best[1:3])) if len(best) > 1 else "") + ".")
        if re.search(r"\b(visitors|visits|visite)\b", low) and not re.search(r"orders|ordini", low):
            return f"Visitors {label}: {visits} — {len(paid)} of them bought ({conv:.1f} % conversion; 1–3 % is normal for a small shop)."
        if re.search(r"\bconversion\b", low):
            return (f"Conversion {label}: {conv:.1f} % ({len(paid)} orders from {visits} visits). Normal for a small shop is 1–3 %; " +
                    ("that's healthy." if conv >= 1.5 else "below 1 % usually means the product page or the shipping cost scares people off — check the price shown before checkout."))
        if re.search(r"\b(profit|profitable|money|earn|earned|guadagnato|margin|utile|perdita|black|red)\b", low) and not re.search(r"\bsummary|riepilogo\b", low):
            head = ""
            if re.search(r"\b(profitable|making money|in profit|losing money|make (?:any )?money|utile|perdita|black|red)\b", low):
                head = ("Yes — " if profit > 0 else "Not yet — ") if paid else "No sales yet, so neither — "
            return (head + f"Profit {label}: {_eur(profit)} on {_eur(rev)} of sales from {len(paid)} orders " +
                    f"(goods {_eur(cogs)}, shipping {_eur(ship)}, payment fees {_eur(fees)})" + (f" — {profit / rev * 100:.0f} % net margin." if rev else ".") +
                    (" That's before your time, boxes (~€ 1/parcel), the domain and any ads — real profit needs those off too." if head.startswith("Yes") else ""))
        if re.search(r"\b(how ?many|quanti)\b.*\b(orders|sales|ordini|customers)\b", low):
            return (f"Orders {label}: {len(paid)}" + (f" ({_eur(rev)} in sales, average basket {_eur(rev / len(paid))})" if paid else "") +
                    (f"; {len([o for o in orders if o['status'] == 'refunded'])} refunded" if any(o["status"] == "refunded" for o in orders) else "") + ".")
        # summary
        open_ = [o for o in st.data["orders"] if o["status"] == "paid"]
        lowst = [p for p in st.products() if p["stock"] <= 3]
        lines = [f"Practice store — {label} (day {day}):",
                 f"• {len(paid)} orders, {_eur(rev)} sales, profit {_eur(profit)}" + (f" ({profit / rev * 100:.0f} %)" if rev else ""),
                 f"• {visits} visits → {conv:.1f} % conversion"]
        if best:
            lines.append("• best sellers: " + ", ".join(f"{a} ×{b}" for a, b in best[:3]))
        if open_:
            lines.append(f"• to ship: {len(open_)} order(s) — say “print the shipping labels”")
        if lowst:
            lines.append("• low stock: " + ", ".join(f"{p['name']} ({p['stock']})" for p in lowst) + " — say “what do you propose for the store?”")
        return "\n".join(lines)

    def ship_cost(self, t):
        """'how much is shipping to germany?' — from the store's own shipping rules (the practice store), not a web search."""
        from . import store as _s
        low = t.lower()
        code = next((c for w, c in (("germany", "DE"), ("germania", "DE"), ("france", "FR"), ("francia", "FR"), ("spain", "ES"), ("spagna", "ES"), ("italy", "IT"), ("italia", "IT"),
                                     ("austria", "AT"), ("netherlands", "NL"), ("olanda", "NL"), ("belgium", "BE"), ("portugal", "PT"), ("poland", "PL"), ("uk", "GB"), ("united kingdom", "GB"), ("england", "GB"), ("switzerland", "CH"), ("svizzera", "CH"), ("usa", "US"), ("america", "US"), ("stati uniti", "US"), ("united states", "US"),
                                     ("ireland", "IE"), ("greece", "GR"), ("grecia", "GR"), ("sweden", "SE"), ("denmark", "DK"), ("finland", "FI"), ("czech", "CZ"), ("croatia", "HR"), ("hungary", "HU"), ("romania", "RO"), ("slovenia", "SI"), ("slovakia", "SK"), ("luxembourg", "LU"), ("norway", "NO"), ("canada", "CA"), ("australia", "AU"), ("japan", "JP"), ("china", "CN"), ("brazil", "BR"), ("turkey", "TR"), ("russia", "RU"), ("san marino", "SM"), ("sicily", "IT"), ("sardinia", "IT"), ("sicilia", "IT"), ("sardegna", "IT")) if re.search(r"\b" + w + r"\b", low)), None)
        try:
            rules = self.store.ship_rules_text() + " · elsewhere: not offered yet"
        except Exception:
            rules = "Italy € 3,90 (free over € 39) · Germany/France/Spain € 6,90 · other EU € 8,90 · outside the EU: not offered yet"
        if not code:
            return f"Our shipping prices (practice store): {rules}. Orders ship within 1 business day with GLS from Bergamo."
        cost = self.store.shipping_for(code, 0)
        if cost is None:
            names = {"CH": "Switzerland", "GB": "the UK", "US": "the USA", "NO": "Norway", "CA": "Canada", "AU": "Australia", "JP": "Japan", "CN": "China", "BR": "Brazil", "TR": "Turkey", "RU": "Russia"}
            why = {"CH": "customs: the buyer pays Swiss VAT + a courier handling fee (CHF 15–30) on delivery, which causes refused parcels — doable later with DDP labels via Packlink/DHL (~€ 20–25 for 2 kg)",
                   "GB": "post-Brexit customs: UK VAT is due at checkout for orders under £ 135 (needs a UK VAT number), plus a customs declaration per parcel (~€ 20–25 shipping)",
                   "US": "customs paperwork + € 40 shipping for 2 kg: the maths doesn't work under ~€ 60 orders"}.get(code, "outside the EU every parcel needs a customs declaration and the buyer may pay import VAT on delivery")
            return f"Not yet — we don't ship to {names.get(code, code)}: {why}. The shop covers the EU: {rules}. If a customer asks, say “not yet, we're working on it — leave your e-mail and we tell you when”; say “open shipping to {names.get(code, code)}” when you want me to prepare the rule and prices for your tap."
        days = {"IT": "2–3 business days", "DE": "4–6 business days", "FR": "4–6 business days", "ES": "4–6 business days"}.get(code, "5–7 business days")
        _row = next((r for r in self.store.ship_rules() if r[0] == code), None)
        free = f" (free over {_eur(_row[2])})" if _row and _row[2] else ""
        if re.search(r"\b(how long|how many days|quanto ci mette|tempi|when (?:does|will) it arrive)\b", low):
            return (f"To {code}: {days} door to door with GLS (we hand it over within 1 business day, so order Monday → delivered by about {'Thursday' if code == 'IT' else 'the following Monday' if code in ('DE', 'FR', 'ES') else 'the middle of the following week'}); "
                    f"tracked; the customer pays {_eur(cost)}{free}. Tell them the range, not the best case — a day early delights, a day late gets a complaint.")
        if code in ("CH", "GB", "US", "NO", "CA"):
            days = {"CH": "4–7 business days", "GB": "5–8 business days", "NO": "5–8 business days"}.get(code, "7–12 business days")
            return f"Shipping to {code}: {_eur(cost)}{free}, {days}, tracked. That's what the customer pays; a small parcel costs us about " + {"CH": "€ 20–25", "GB": "€ 20–25", "NO": "€ 20–25"}.get(code, "€ 40+") + " plus a customs declaration — the buyer may pay import VAT on delivery, say so on the shipping page."
        return f"Shipping to {code}: {_eur(cost)}{free}, {days}, GLS with tracking. That's what the customer pays; it costs us about € 6–9 for a small EU parcel, so on a € 12,90 item the margin gets thin — a free-shipping threshold for the EU (~€ 60) helps."

    def sell_out(self, what):
        p = self.store.find_product(what)
        if not p:
            return None
        day = self.store.data.get("day", 0)
        sold = sum(l["qty"] for o in self.store.data["orders"] if o["status"] in ("paid", "shipped", "delivered") and o.get("day", 0) > day - 7 for l in o["lines"] if l["id"] == p["id"])
        if p["stock"] == 0:
            return f"{p['name']} is already sold out (0 left). Say “we received N more {p['name'].split(' (')[0].lower()}” when the goods arrive."
        if not sold:
            return f"{p['name']}: {p['stock']} left and nothing sold in the last 7 practice days, so no sell-out in sight — at 1 a day it would last {p['stock']} days."
        per_day = sold / 7
        days = p["stock"] / per_day
        return (f"{p['name']}: {p['stock']} left, selling {sold} a week ({per_day:.1f} a day) → about {days:.0f} days of stock. " +
                ("Reorder now — supplier lead times are usually 1–3 weeks." if days < 21 else "Fine for now; reorder when it drops below ~3 weeks of sales."))

    def what_if(self, m):
        n = int(m.group("n") or m.group("n2"))
        what = (m.group("what") or m.group("what2") or "").strip()
        per = (m.group("per") or m.group("per2") or "month").lower()
        per_en = {"mese": "month", "settimana": "week", "giorno": "day"}.get(per, per)
        p = self.store.find_product(what) if self.store is not None else None
        price = _num(m.group("price")) if m.group("price") else (p["price"] if p else None)
        cost = _num(m.group("cost")) if m.group("cost") else (p.get("cost", 0) if p else None)
        if price is None:
            return f"Tell me the selling price and the cost (“if I sell {n} {what} a {per_en} at 14.90 with cost 5.60”) and I do the maths."
        ship_cost = 3.25                                                             # what the carrier charges us, average
        fee = price * 0.029 + 0.30
        unit = price - (cost or 0) - fee
        unit_ship = unit - ship_cost
        gross = n * unit
        net = n * unit_ship
        mult = {"month": 12, "week": 52, "day": 365}[per_en]
        return (f"{n} × {p['name'] if p else what} a {per_en} at {_eur(price)} (cost {_eur(cost or 0)}):\n"
                f"• per sale: {_eur(price)} − cost {_eur(cost or 0)} − payment fee {_eur(fee)} = {_eur(unit)}; if you pay the shipping (free-shipping orders) another −{_eur(ship_cost)} → {_eur(unit_ship)}\n"
                f"• per {per_en}: {_eur(gross)} (customer pays shipping) to {_eur(net)} (you pay it) · sales {_eur(n * price)}\n"
                f"• per year at this pace: {_eur(gross * mult)} to {_eur(net * mult)} — before ads, returns, tax and your time.\n"
                f"Rule of thumb: keep 1–2 refunds per 100 orders and ~10–20 % of sales for ads in the plan; ask “tax on {round(gross * mult):.0f} €” for the Italian forfettario maths.")

    def _week_stats(self, lo, hi):
        """Orders with lo < day <= hi → (orders, sales, profit, visits)."""
        st = self.store
        paid = [o for o in st.data["orders"] if o["status"] in ("paid", "shipped", "delivered") and lo < o.get("day", 0) <= hi]
        rev = sum(o["total"] for o in paid)
        cogs = sum(l["qty"] * l.get("cost", 0) for o in paid for l in o["lines"])
        ship = sum(2.9 + 0.35 * sum(l["qty"] for l in o["lines"]) for o in paid)
        fees = sum(0.029 * o["total"] + 0.30 for o in paid)
        visits = sum(v for d, v in st.data["visits"].items() if lo < int(d) <= hi)
        return len(paid), rev, rev - cogs - ship - fees, visits

    def order_more(self, p, n):
        """'order 20 more lamps' — I can't buy (your money), so: the purchase line, the money, and a to-do + a stock note for when it lands."""
        cost = p.get("cost", 0) * n
        weekly = 0
        try:
            day = self.store.data.get("day", 0)
            weekly = sum(l["qty"] for o in self.store.data["orders"] if o["status"] in ("paid", "shipped", "delivered") and o.get("day", 0) > day - 7 for l in o["lines"] if l["id"] == p["id"])
        except Exception:
            pass
        cover = f" — about {n / weekly:.0f} weeks of sales at {weekly}/week" if weekly else ""
        sup, sup_note = "the supplier", ""
        try:                                                                    # 'remember that the mug supplier is called Terra Ceramics' → the name goes on the line
            key = p["name"].split(" (")[0].lower().split()
            for r in (self.memory.notes(" ".join(key), limit=8) if self.memory else []):
                txt = (r.get("topic", "") + " " + r.get("text", "")).lower()
                if r.get("kind") == "owner" and re.search(r"supplier|fornitore|vendor|factory", txt) and any(k in txt for k in key if len(k) >= 3 and not k.isdigit()):
                    mm = re.search(r"\b(?:is called|is named|si chiama|called|named|is|are|=|:)\s+([A-Za-z][\w&'\-]*(?: [A-Za-z][\w&'\-]*){0,3})", r["text"])
                    if mm and not re.match(r"^(?:the|a|an|closed|open|not|in|on|at|going|very|also)\b", mm.group(1).lower()):
                        sup = mm.group(1).strip().rstrip(".")
                    if re.search(r"clos|holiday|chiuso|ferie|vacation|august|agosto|lead time|weeks? to ship|min(?:imum)? order", txt):
                        sup_note = f" (your note: “{r['text'][:80]}”)"
                    break
        except Exception:
            pass
        i = None
        try:
            i = self.memory.add(f"Order {n} × {p['name'].split(' (')[0]} from {sup} ({_eur(cost)} at {_eur(p.get('cost', 0))} each)") if self.memory else None
        except Exception:
            pass
        return (f"Ordering is your money, so I don't place it — but here's the line ready to send to {sup}{sup_note}: “{n} × {p['name'].split(' (')[0]} at {_eur(p.get('cost', 0))} = {_eur(cost)}”{cover}. "
                + (f"It's #{i} on your to-do list. " if i else "") +
                f"When the parcel arrives say “we received {n} more {p['name'].split(' (')[0].lower()}” and I update the stock (now {p['stock']}). "
                + ("Meanwhile the product is sold out on the site — say “mark it back in 2 weeks” and I put a 'ships in 2 weeks' note on the page instead of hiding it." if p["stock"] == 0 else ""))

    def week_compare(self):
        day = self.store.data.get("day", 0)
        if day < 8:
            return f"The practice store is only on day {day} — there's no previous week to compare with yet. Ask again after day 14 (say “run 7 practice days”)."
        a = self._week_stats(day - 7, day)
        b = self._week_stats(day - 14, day - 7)
        def d(x, y, money=False):
            if not y:
                return "(no data last week)"
            ch = (x - y) / y * 100
            return f"{'▲' if ch >= 0 else '▼'} {abs(ch):.0f} % vs {_eur(y) if money else y} last week"
        conv_a = a[0] / a[3] * 100 if a[3] else 0
        conv_b = b[0] / b[3] * 100 if b[3] else 0
        verdict = ("Better week: keep doing what you did (same posts, same prices)." if a[2] > b[2] * 1.05 else
                   "Weaker week: check stock-outs first (a sold-out best seller kills a week), then what changed in posts or prices." if a[2] < b[2] * 0.95 else "Flat week — steady, no alarm.")
        return (f"This week vs last week (days {day - 6}–{day} vs {day - 13}–{day - 7}):\n"
                f"• orders {a[0]} {d(a[0], b[0])}\n• sales {_eur(a[1])} {d(a[1], b[1], True)}\n• profit {_eur(a[2])} {d(a[2], b[2], True)}\n"
                f"• visits {a[3]} {d(a[3], b[3])} · conversion {conv_a:.1f} % (was {conv_b:.1f} %)\n{verdict}")

    def push_pick(self, t):
        """'which product should I push this week?' — margin × stock × recent sales, from the store's own data."""
        st = self.store
        day = st.data.get("day", 0)
        sold7 = {}
        for o in st.data["orders"]:
            if o["status"] in ("paid", "shipped", "delivered") and o.get("day", 0) > day - 7:
                for l in o["lines"]:
                    sold7[l["id"]] = sold7.get(l["id"], 0) + l["qty"]
        rows = []
        for p in st.products():
            margin = p["price"] - p.get("cost", 0) - (0.029 * p["price"] + 0.30)
            rows.append((p, margin, sold7.get(p["id"], 0)))
        ok = [r for r in rows if r[0]["stock"] >= 5]
        if not ok:
            return "Nothing is worth pushing right now — every product is out of stock or nearly (≤ 4 left). Reorder first: say “what do you propose for the store?”."
        ok.sort(key=lambda r: -(r[1] * (1 + r[2]) * min(1.0, r[0]["stock"] / 15)))
        p, margin, sold = ok[0]
        skip = [r[0]["name"] for r in rows if r[0]["stock"] < 5]
        it = bool(re.search(r"\b(quale|che|conviene|spingere)\b", t.lower()))
        head = (f"Spingi {p['name']} questa settimana" if it else f"Push {p['name']} this week") + f": {_eur(margin)} margin per sale after fees ({margin / p['price'] * 100:.0f} %), {p['stock']} in stock, {sold} sold in the last 7 days."
        lines = [head]
        if len(ok) > 1:
            q, m2, s2 = ok[1]
            lines.append(f"Runner-up: {q['name']} ({_eur(m2)} per sale, {q['stock']} in stock, {s2} sold).")
        if skip:
            lines.append("Don't push " + ", ".join(skip) + " — too little stock; a sold-out ad is money burned.")
        lines.append(f"Say “5 captions for the {p['name'].split(' ')[0].lower()}” or “tiktok ideas for {p['name'].split(' (')[0].lower()}” and I write them.")
        return "\n".join(lines)

    def post_today(self, t):
        """'what should I post today?' — one concrete idea for one product, from the store's data; the post itself only after the owner picks."""
        st = self.store
        day = st.data.get("day", 0)
        sold7 = {}
        for o in st.data["orders"]:
            if o["status"] in ("paid", "shipped", "delivered") and o.get("day", 0) > day - 7:
                for l in o["lines"]:
                    sold7[l["id"]] = sold7.get(l["id"], 0) + l["qty"]
        ps = [p for p in st.products() if p["stock"] >= 5]
        if not ps:
            return "Don't post a product today — everything is out of stock or nearly. Post the shop's story instead (who you are, why you started) and say “we received N more …” when stock lands."
        p = max(ps, key=lambda x: (x["price"] - x.get("cost", 0)) * (1 + sold7.get(x["id"], 0)))
        name = p["name"].split(" (")[0]
        detail = (p.get("details") or [p.get("short", "")])[0].rstrip(".")
        wd = _dt.date.today().weekday()
        angles = ["the product in someone's hand, 7 seconds, no talking — caption: one honest detail",
                  "packing an order: box, paper, the card — people love seeing the parcel being made",
                  f"the 'why' — one line on why you picked {name.lower()} over the cheap version",
                  "a mistake or a lesson from this week (e.g. a parcel that came back) — honesty gets saved and shared",
                  f"{name} next to the thing it replaces (the plastic one) — no text, just the two",
                  "answer a real customer question on camera (from the inbox) — 15 seconds",
                  "behind the numbers: how many orders this week, what surprised you"]
        return (f"Post today: {name} — {angles[wd]}.\nCaption: “{detail}.” + one question to the viewer. Best time 12:30 or 19:00–21:00.\n"
                f"Why this product: {p['stock']} in stock, {sold7.get(p['id'], 0)} sold this week, {(p['price'] - p.get('cost', 0)) / p['price'] * 100:.0f} % margin.\n"
                f"Say “write the instagram post for {name.lower()}” and I draft it for your approval, or “5 captions for the {name.split(' ')[-1].lower()}”.")

    def reorder_qty(self, what):
        p = self.store.find_product(what)
        if not p:
            return None
        day = self.store.data.get("day", 0)
        sold14 = sum(l["qty"] for o in self.store.data["orders"] if o["status"] in ("paid", "shipped", "delivered") and o.get("day", 0) > day - 14 for l in o["lines"] if l["id"] == p["id"])
        weekly = sold14 / 2
        lead_weeks, cover_weeks = 3, 4                                            # supplier lead time + the stock you want to hold after it lands
        if weekly == 0:
            qty = 10 if p["stock"] < 10 else 0
            why = "no sales in the last 14 practice days, so order small"
        else:
            need = weekly * (lead_weeks + cover_weeks) - p["stock"]
            qty = int(max(0, round(need / 5.0) * 5))
            why = f"you sell ~{weekly:.1f} a week; {lead_weeks} weeks of lead time + {cover_weeks} weeks of cover = {weekly * (lead_weeks + cover_weeks):.0f} units, minus {p['stock']} on hand"
        if qty == 0:
            return f"{p['name']}: no reorder needed now — {p['stock']} in stock covers more than {lead_weeks + cover_weeks} weeks at the current pace ({weekly:.1f} a week). Check again in two weeks."
        cash = qty * p.get("cost", 0)
        return (f"{p['name']}: order about {qty} units ({why}). That's {_eur(cash)} of stock at {_eur(p.get('cost', 0))} each. "
                f"Ask the supplier for the price break at {qty * 2} — if the unit cost drops 15 % or more it's worth it, otherwise don't tie up the cash.")

    def price_ok(self, amount, what, t):
        p = self.store.find_product(what) if self.store is not None else None
        low = t.lower()
        if p:
            cost = p.get("cost", 0)
            fee = 0.029 * amount + 0.30
            margin = (amount - cost - fee) / amount * 100 if amount else 0
            cur = f" (it's {_eur(p['price'])} in the shop now)" if abs(p["price"] - amount) > 0.01 else " (that's the shop price now)"
            verdict = ("that's thin: below ~45 % the shipping and one refund eat the profit." if margin < 45 else
                       "healthy — room for a 15–20 % promo when you need one." if margin < 65 else "a fat margin — fine if the market pays it; check a comparison before pushing it.")
            return (f"{_eur(amount)} for {p['name']}{cur}: cost {_eur(cost)} + payment fee {_eur(fee)} → {margin:.0f} % margin, {verdict} "
                    f"The customer decides by comparison, not by your cost: say “compare prices for {what}” and I check what others charge before we touch it.")
        return (f"For {what} at {_eur(amount)} I can't judge without two numbers: your cost (2.5–4× cost is the usual band) and what others charge. "
                f"Tell me the cost (“it costs me 6”) for the margin, and say “compare prices for {what}” for the market check.")

    def sale_prices(self, t):
        """Black Friday / sale: the biggest discount per product that keeps ~45 % gross margin, plus the EU price rule."""
        st = self.store
        floor = 0.45
        lines = []
        for p in st.products():
            if p["stock"] <= 0:
                continue
            cost = p.get("cost", 0)
            maxd = max(0.0, 1 - cost / ((1 - floor) * p["price"])) if p["price"] else 0
            d = min(0.30, int(maxd * 20) / 20)                                             # steps of 5 %, never more than 30 %
            if d < 0.10:
                lines.append(f"• {p['name']} {_eur(p['price'])}: no discount — the margin can't take it (bundle it instead)")
            else:
                newp = round(p["price"] * (1 - d) + 0.09, 0) - 0.10 if p["price"] * (1 - d) > 5 else round(p["price"] * (1 - d), 2)
                lines.append(f"• {p['name']} {_eur(p['price'])} → −{d * 100:.0f} % = {_eur(newp)} (keeps ≥ {floor * 100:.0f} % gross margin){' — low stock, don\'t advertise it' if p['stock'] <= 3 else ''}")
        head = "Sale prices that don't lose money (rule: never below cost + shipping + fee, keep ~45 % gross margin):"
        rules = ("Rules: (1) EU/Italy Omnibus rule — a “was € X” must be the lowest price of the last 30 days, so don't raise prices the week before; "
                 "(2) one clear offer beats five (“−20 % on everything” or a bundle), (3) the free-shipping threshold stays, (4) set an end date and stick to it, "
                 "(5) stock: a sold-out sale item is a lost customer, so push the deep ones. Say “lower the price of the mug to 11.90” and I prepare the change for your tap.")
        return head + "\n" + "\n".join(lines) + "\n" + rules

    def free_returns(self, t):
        it = bool(re.search(r"\b(resi|conviene|gratuit)\b", t.lower()))
        rate = "2–5 %" if self.store is not None else "5–10 %"
        txt = (f"Free returns — my advice: 30 days, easy, but the customer pays the return postage (€ 4,90 flat) unless the item is faulty or wrong; then it's on you, always.\n"
               f"Why: the law (EU) already gives 14 days to return; free return postage adds ~€ 5–7 per return, and returns run {rate} of orders for home goods (20–30 % in fashion). "
               f"On a € 15 item one free return eats the profit of 3 sales.\nDo offer: free returns on faulty/wrong items (no discussion), a printable label so it's easy, refund within 5 days of getting it back. "
               f"Say ‘the returns page’ shows the current rule; “change the returns page to …” and I prepare it.")
        if it:
            txt = ("Resi gratuiti — il mio consiglio: 30 giorni, procedura facile, ma la spedizione del reso la paga il cliente (€ 4,90 fissi), tranne se il prodotto è difettoso o sbagliato: lì paghi sempre tu.\n"
                   "Perché: la legge UE dà già 14 giorni di recesso; il reso gratis costa € 5–7 a pezzo e i resi sono il 2–5 % degli ordini nella casa (20–30 % nella moda). Su un articolo da € 15 un reso gratis mangia il margine di 3 vendite.\n"
                   "Offri: reso gratis su difetti/errori senza discutere, etichetta stampabile, rimborso entro 5 giorni dal rientro.")
        return txt

    def captions(self, what, n, t):
        """'give me 5 captions for the mug' — from the facts I have on the product; no invented claims."""
        n = int(n) if n and n.isdigit() else {"three": 3, "tre": 3, "four": 4, "five": 5, "cinque": 5, "six": 6}.get((n or "").lower(), 5)
        n = max(1, min(n, 8))
        p = self.store.find_product(what) if self.store is not None else None
        name = p["name"].split(" (")[0] if p else what.strip()
        facts = [f.rstrip(".") for f in ([p.get("short", "")] + p.get("details", [])) if f] if p else []
        short = facts[0] if facts else ""
        detail = facts[1] if len(facts) > 1 else ""
        pool = [f"{name}. {short}." if short else f"{name} — small batch, honest price.",
                f"The little upgrade you'll use every day: {name.lower()}." + (f" {detail}." if detail else ""),
                f"Made to last, not to be replaced. {name}." + (f" {short}." if short else ""),
                f"Which one would you pick? 👇 {name}" + (f" — {p['options'][next(iter(p['options']))][0]} or {p['options'][next(iter(p['options']))][1]}?" if p and p.get("options") and len(next(iter(p["options"].values()))) > 1 else ""),
                f"Ships in 1 business day from Bergamo 📦 {name}, free shipping in Italy over € 39." if self.store is not None else f"{name} — link in bio.",
                f"Behind this parcel there's a small shop, not a warehouse. {name} — thank you for choosing small.",
                f"Real talk: {detail or short or name}. That's the whole pitch.",
                f"Gift idea that doesn't end up in a drawer: {name}."]
        out = pool[:n]
        tags = self.hashtags(f"hashtags for {name}")
        first = tags.split("\n")[1] if "\n" in tags else ""
        return (f"{n} captions for {name} (from the facts I have; edit freely):\n" + "\n".join(f"{i + 1}. {c}" for i, c in enumerate(out)) +
                (f"\nHashtags: {first}" if first.startswith("#") or "#" in first else "") + "\nSay “post the first one on instagram” and I prepare it for your approval.")

    def write_page(self, kind, t):
        """'write the shipping policy page' — from the shop's real rules; templates with blanks where I don't know."""
        st = self.store
        name = st.data.get("name", "the shop") if st is not None else "the shop"
        pages = st.data.get("pages", {}) if st is not None else {}
        k = ("shipping" if re.match(r"(shipping|delivery|spedizion)", kind) else "returns" if re.match(r"(return|refund|resi)", kind) else
             "faq" if re.match(r"(faq|domande)", kind) else "about" if re.match(r"(about|chi siamo)", kind) else "privacy" if kind.startswith("privacy") else
             "terms" if re.match(r"(terms|termini)", kind) else "contact")
        if k in ("shipping", "returns", "faq", "contact") and pages.get(k):
            body = pages[k]
            return (f"{k.capitalize()} page — the text the practice store shows now (it's built from the shop's real rules):\n{body}\n"
                    f"Tell me the change in plain words (“shipping to Germany is now € 5,90”, “returns 14 days”) and I prepare the new page for your tap.")
        if k == "about":
            return (f"About page for {name} — fill the three blanks, the rest is ready:\n\n"
                    f"{name} started in [year] in [city] with one idea: [the one thing you believe — e.g. everyday objects should last].\n"
                    f"We're a small team — [your name] and [who else] — and we pick every product ourselves: [how you choose — materials, makers, tests].\n"
                    f"What you get from us: honest descriptions, shipping within 1 business day, and a real person answering your e-mails within 24 hours.\n"
                    f"If something isn't right, tell us — we fix it first and ask questions later.\n\nTip: one real photo of you or the workshop beats any stock image; shoppers open About to check there's a person behind the shop.")
        if k == "privacy":
            return ("Privacy policy — a plain-language skeleton (GDPR; have it checked before a real launch):\n"
                    f"1. Who we are: {name}, [legal name, address, e-mail]. 2. What we collect: name, address, e-mail, order details, payment status (never card numbers — the payment provider keeps those), site analytics.\n"
                    "3. Why: to deliver orders, answer messages, send order e-mails, and — only if you tick the box — our newsletter. 4. Who sees it: the courier (address), the payment provider, our e-mail and hosting providers; nobody else, never sold.\n"
                    "5. How long: order data 10 years (tax law), newsletter until you unsubscribe, analytics 14 months. 6. Your rights: see, correct, delete, export your data, object — write to [e-mail]; complaints to the Garante Privacy.\n"
                    "7. Cookies: essential ones always; analytics/marketing only after consent (banner). Generators like iubenda or Shopify's built-in policy do the legal wording for free/cheap.")
        if k == "terms":
            return ("Terms & conditions — the sections a small EU shop needs (skeleton, check with a professional):\n"
                    f"1. Seller: {name}, [legal name, VAT/P.IVA, address]. 2. Orders: the contract is made when we confirm shipment; prices include VAT; obvious price errors may be cancelled.\n"
                    "3. Payment: [methods]. 4. Delivery: times per the shipping page; risk passes on delivery. 5. Right of withdrawal: 14 days from delivery, no reason needed, refund within 14 days of return; exceptions (personalised, sealed hygiene goods).\n"
                    "6. Legal guarantee: 2 years (EU) — repair, replace or refund for faults. 7. Complaints: [e-mail]; EU ODR platform link. 8. Law and court: Italian law, consumer's home court.")
        return f"Contact page for {name}:\n{name} · [e-mail] · we answer within 24 hours on working days · [city, country] · [P.IVA]."

    def complaints(self, t):
        """'what did customers complain about?' — from the inbox, grouped by kind."""
        items = self.inbox.items()
        if not items:
            return "No customer messages yet, so no complaints. (Practice days bring simulated customers — say “run a practice day”.)"
        cutoff = (_dt.datetime.now() - _dt.timedelta(days=7)).isoformat() if re.search(r"\b(week|today|settimana|oggi)\b", t.lower()) else ""
        kinds = {}
        for r in items:
            if cutoff and r.get("t", "") < cutoff:
                continue
            try:
                k = self.inbox.classify(r["text"])["kind"]
            except Exception:
                k = "other"
            kinds.setdefault(k, []).append(r)
        bad = {"damaged_or_wrong": "arrived damaged / wrong item", "where_is_my_order": "where is my order (no tracking yet)", "return_or_refund": "returns and refunds",
               "complaint": "complaints", "cancel_or_change": "cancel or change the order"}
        total = sum(len(v) for v in kinds.values())
        rows = [(bad[k], len(kinds[k]), kinds[k][-1]["text"]) for k in bad if k in kinds]
        if not rows:
            return f"{total} customer message(s) and none is a complaint — questions, discount requests and compliments only. Nice."
        rows.sort(key=lambda x: -x[1])
        fix = {"arrived damaged / wrong item": "→ check the packaging of the top product (bubble wrap + a stiffer box) and photograph every parcel before it leaves",
               "where is my order (no tracking yet)": "→ send the tracking number the moment you print the label; put the real delivery time on the product page",
               "returns and refunds": "→ make the returns page answer 'who pays' and 'how long' in the first line",
               "complaints": "→ answer within the hour with a fix and a date",
               "cancel or change the order": "→ a 'change my order' button in the order e-mail for the first 2 hours stops most of these"}
        return (f"Complaints in the inbox ({sum(r[1] for r in rows)} of {total} messages" + (", last 7 days" if cutoff else "") + "):\n" +
                "\n".join(f"• {lab} ×{n} — e.g. “{ex[:90]}” {fix[lab]}" for lab, n, ex in rows[:4]) + "\n(/inbox to answer the open ones.)")

    def inbox_waiting(self):
        new = self.inbox.items("new")
        if not new:
            return "Nothing waiting — every customer message has an answer. I'll ping you when one comes in."
        rows = [f"• {r.get('from', '?')} — {(r.get('subject') or r['text'])[:70]}" for r in new[:5]]
        return f"{len(new)} customer message(s) waiting:\n" + "\n".join(rows) + (f"\n…and {len(new) - 5} more" if len(new) > 5 else "") + "\nSay “/inbox” and I show each one with my draft reply for your tap."

    def check_in(self, t):
        """'how are we doing?', 'everything ok?', 'update me', 'anything I should know?' — the shop's state in four lines: what happened, what waits, what's wrong."""
        low = t.lower()
        it = bool(re.search(r"\b(come|tutto|novità|aggiornami|problemi|sapere|attesa)\b", low))
        lines, problems = [], []
        if self.mind and self.mind.job:
            lines.append("• " + self.mind.status_line())
        try:
            if self.store is not None and self.store.data.get("orders"):
                st = self.store
                day = st.data.get("day", 0)
                today = [o for o in st.data["orders"] if o.get("day") == day and o["status"] in ("paid", "shipped", "delivered")]
                week = [o for o in st.data["orders"] if o.get("day", 0) > day - 7 and o["status"] in ("paid", "shipped", "delivered")]
                lines.append(f"• shop: {len(today)} order(s) today ({_eur(sum(o['total'] for o in today))}), {len(week)} this week ({_eur(sum(o['total'] for o in week))}), practice day {day}")
                open_ = [o for o in st.data["orders"] if o["status"] == "paid"]
                late = [o for o in open_ if day - o.get("day", day) >= 1]
                if open_:
                    (problems if late else lines).append(f"• 📦 {len(open_)} order(s) to ship" + (f" — {len(late)} already late (promised next-day)" if late else "") + " — say “print the shipping labels”")
                lowst = [p for p in st.products() if p["stock"] <= 3]
                if lowst:
                    problems.append("• ⚠️ low/out of stock: " + ", ".join(f"{p['name'].split(' (')[0]} ({p['stock']})" for p in lowst))
                props = [p for p in st.data.get("proposals", []) if p["status"] == "open"]
                if props:
                    lines.append(f"• {len(props)} store proposal(s) waiting for your tap")
            elif self.store is not None:
                lines.append("• shop: no practice day yet — say “run a practice day”")
        except Exception:
            pass
        try:
            if self.inbox is not None:
                new = self.inbox.items("new")
                if new:
                    problems.append(f"• 💬 {len(new)} customer message(s) waiting — /inbox")
        except Exception:
            pass
        try:
            items = self.memory.open_items() if self.memory else []
            today = _dt.date.today().isoformat()
            due = [x for x in items if x.get("due") and x["due"][:10] <= today]
            if due:
                problems.append(f"• ⏰ {len(due)} reminder(s) due: " + "; ".join(re.sub(r" \(⏰ .*\)$", "", x["text"])[:40] for x in due[:3]))
            elif items:
                lines.append(f"• {len(items)} thing(s) on your to-do list")
        except Exception:
            pass
        asked_stock = bool(re.search(r"\b(stock|low|out)\b", low))
        asked_ship = bool(re.search(r"\bship\b", low))
        asked_wait = bool(re.search(r"\b(waiting|reply|attesa)\b", low))
        if asked_stock:
            return next((p for p in problems if "stock" in p), "Stock is fine — nothing at or below 3 pieces." if self.store is not None else "I have no stock to watch yet.").lstrip("• ")
        if asked_ship:
            return next((p for p in problems + lines if "to ship" in p), "Nothing to ship — every paid order is already on its way.").lstrip("• ")
        if asked_wait:
            return next((p for p in problems if "customer message" in p), "Nobody is waiting — the inbox is clear.").lstrip("• ")
        if not lines and not problems:
            return "Tutto tranquillo: niente da spedire, nessun messaggio in attesa, niente in corso." if it else "All quiet: nothing to ship, nobody waiting, nothing running. Give me a job or I'll study."
        head = ("Situazione:" if it else ("All fine, here's where we are:" if not problems else f"{len(problems)} thing(s) need you, rest is fine:"))
        return head + "\n" + "\n".join(problems + lines)

    def sold_how_many(self, what, when):
        p = self.store.find_product(what)
        if not p:
            return None
        st = self.store
        day = st.data.get("day", 0)
        keep = {"today": lambda o: o.get("day") == day, "oggi": lambda o: o.get("day") == day, "yesterday": lambda o: o.get("day") == day - 1, "ieri": lambda o: o.get("day") == day - 1,
                "this week": lambda o: o.get("day", 0) > day - 7, "questa settimana": lambda o: o.get("day", 0) > day - 7}.get(when, lambda o: True)
        rows = [(o, sum(l["qty"] for l in o["lines"] if l["id"] == p["id"])) for o in st.data["orders"] if o["status"] in ("paid", "shipped", "delivered") and keep(o) and any(l["id"] == p["id"] for l in o["lines"])]
        if when == "last":
            if not rows:
                return f"We haven't sold {p['name']} yet."
            o, q = rows[-1]
            ago = day - o.get("day", day)
            return f"Last {p['name']} sale: order #{o['n']} on practice day {o.get('day')} ({'today' if ago == 0 else 'yesterday' if ago == 1 else f'{ago} days ago'}), ×{q} to {o['country']}. {p['stock']} left."
        n = sum(q for _, q in rows)
        label = {"today": "today", "oggi": "today", "yesterday": "yesterday", "ieri": "yesterday", "this week": "this week", "questa settimana": "this week"}.get(when, "so far")
        return f"{p['name']}: {n} sold {label} in {len(rows)} order(s)" + (f" = {_eur(sum(q * p['price'] for _, q in rows))}" if n else "") + f"; {p['stock']} left."

    def plate(self):
        """'what's on my plate today?' — to-dos (dated first), orders to ship, messages waiting, low stock — one list."""
        lines, n = [], 0
        try:
            items = self.memory.open_items() if self.memory else []
            due = sorted([x for x in items if x.get("due")], key=lambda x: x["due"])
            today = _dt.date.today().isoformat()
            for x in due:
                if x["due"][:10] <= today:
                    n += 1
                    lines.append(f"• ⏰ {x['due'][11:16]} {re.sub(r' \\(⏰ .*\\)$', '', x['text'])}")
            rest = [x for x in items if not x.get("due")][:5]
            for x in rest:
                n += 1
                lines.append(f"• {x['text']}")
            if len(items) > len(rest) + len([x for x in due if x['due'][:10] <= today]):
                lines.append(f"• …{len(items) - len(rest) - len([x for x in due if x['due'][:10] <= today])} more on the to-do list")
        except Exception:
            pass
        try:
            if self.store is not None:
                open_ = [o for o in self.store.data["orders"] if o["status"] == "paid"]
                if open_:
                    n += 1
                    lines.append(f"• 📦 ship {len(open_)} order(s) — say “print the shipping labels”")
                lowst = [p for p in self.store.products() if p["stock"] <= 3]
                if lowst:
                    n += 1
                    lines.append("• ⚠️ low stock: " + ", ".join(f"{p['name']} ({p['stock']})" for p in lowst))
        except Exception:
            pass
        try:
            if self.inbox is not None:
                new = self.inbox.items("new")
                if new:
                    n += 1
                    lines.append(f"• 💬 {len(new)} customer message(s) waiting — /inbox")
        except Exception:
            pass
        if not lines:
            return "Nothing urgent today: no orders to ship, no messages waiting, to-do list empty. Good day to work on the next product or a post — say “tiktok ideas” or “which product should I push?”."
        return f"Today ({_dt.date.today().strftime('%a %d %b')}) — {n} thing(s):\n" + "\n".join(lines) + "\nTell me “done <what>” as you go."

    # ---- orders by number, late ones, who bought what, margins, stock value ---------------------------------
    def order_action(self, act, n, why):
        st = self.store
        o = st.order(n)
        if not o:
            return f"There's no order #{n} in the practice store. Say “which orders” to see the recent ones."
        act = "ship" if act.startswith(("ship", "mark", "spedisci")) else "cancel" if act.startswith(("cancel", "annulla")) else "refund"
        who = f"{o['customer'].get('name', '')} ({o['country']})"
        items = ", ".join(f"{l['name']} ×{l['qty']}" for l in o["lines"])
        if act == "ship":
            if o["status"] != "paid":
                return f"Order #{n} is already {o['status']} — nothing to ship."
            return {"store_change": {"kind": "ship", "order": n, "text": f"Mark order #{n} shipped — {who}, {items}, {_eur(o['total'])}"}}
        if act == "cancel":
            if o["status"] != "paid":
                return (f"Order #{n} is {o['status']}, so it can't be cancelled any more" + (" — a shipped order is refunded when it comes back (say “refund order " + str(n) + "” once it's returned)." if o["status"] in ("shipped", "delivered") else "."))
            return {"store_change": {"kind": "cancel", "order": n, "text": f"Cancel order #{n} — {who}, {items}, refund {_eur(o['total'])} to the customer, stock goes back" + (f"; reason: {why}" if why else "")}}
        if o["status"] not in ("paid", "shipped", "delivered", "return_requested"):
            return f"Order #{n} is {o['status']} — it can't be refunded (again)."
        note = " Faulty item → no need to ask for it back, a photo is enough; you can claim the parcel damage from the courier." if re.search(r"\b(broken|damaged|crack|faulty|rotto|danneggiato)\b", why.lower()) else ""
        return {"store_change": {"kind": "refund", "order": n, "text": f"Refund order #{n} — {who}, {items}, {_eur(o['total'])} back to the customer" + (f"; reason: {why}" if why else "") + note}}

    # ---- round 7: orders, catalogue facts, availability, quotes ------------------------------------------
    def order_info(self, n, t=""):
        st = self.store
        o = st.order(n)
        if not o:
            recent = [x["n"] for x in st.data["orders"][-5:]]
            return f"There's no order #{n} in the practice store" + (f" — the last ones are {', '.join('#' + str(x) for x in recent)}." if recent else ".")
        day = st.data.get("day", 0)
        items = ", ".join(f"{l['name']} ×{l['qty']}" + (f" ({l['option']})" if l.get("option") else "") for l in o["lines"])
        age = day - o.get("day", day)
        when = "today" if age == 0 else f"{age} day(s) ago (practice day {o.get('day')})"
        status = {"paid": "PAID, not shipped yet" + (" — ⚠️ late, it should have left within 1 business day" if age >= 1 else " — ship it today"),
                  "shipped": f"SHIPPED with GLS, tracking {o.get('tracking', '—')}" + (" — 7+ days in transit, open a trace" if age >= 7 else ""),
                  "delivered": "DELIVERED", "refunded": "REFUNDED", "cancelled": "CANCELLED", "return_requested": "RETURN REQUESTED"}.get(o["status"], o["status"].upper())
        c = o.get("customer") or {}
        low = t.lower()
        if re.search(r"\b(did we ship|have we shipped|shipped|spedito|is .* out|gone|partito)\b", low) and not re.search(r"\b(status|total|details)\b", low):
            if o["status"] == "paid":
                return f"No — order #{n} ({c.get('name', '')}, {o['country']}; {items}) is paid and still here, placed {when}. Say “ship order {n}” when GLS has it."
            if o["status"] == "shipped":
                return f"Yes — order #{n} shipped, tracking {o.get('tracking', '—')} (GLS), placed {when}; {items} to {c.get('name', '')} ({o['country']})."
            return f"Order #{n} is {o['status']} ({items}, {c.get('name', '')} {o['country']}) — placed {when}."
        if re.search(r"\b(total|totale|how much)\b", low):
            return (f"Order #{n}: total {_eur(o['total'])} = {_eur(o.get('subtotal', o['total'] - o.get('shipping', 0)))} goods + {_eur(o.get('shipping', 0))} shipping to {o['country']}; {items}; status {o['status']}. "
                    f"Our side: goods cost {_eur(sum(l['qty'] * l.get('cost', 0) for l in o['lines']))}, courier ~{_eur(2.9 + 0.35 * sum(l['qty'] for l in o['lines']))}, fees {_eur(0.029 * o['total'] + 0.30)}.")
        ev = (o.get("events") or [])[-2:]
        evs = ("; last events: " + " → ".join(e.get("what", "") for e in ev)) if ev else ""
        return (f"Order #{n} — {status}.\n• {c.get('name', '')}{' · ' + c['email'] if c.get('email') else ''} · {o['country']}\n• {items} · {_eur(o['total'])} (incl. {_eur(o.get('shipping', 0))} shipping)\n• placed {when}{evs}" +
                ("\nSay “ship order " + str(n) + "”, “cancel order " + str(n) + "” or “refund order " + str(n) + "” and I prepare it for your tap." if o["status"] in ("paid", "shipped") else ""))

    def available(self, what, back=False):
        p = self.store.find_product(what)
        if not p:
            return None
        day = self.store.data.get("day", 0)
        week = sum(l["qty"] for o in self.store.data["orders"] if o["status"] in ("paid", "shipped", "delivered") and o.get("day", 0) > day - 7 for l in o["lines"] if l["id"] == p["id"])
        pend = [x for x in self.store.data.get("proposals", []) if x.get("status") == "open" and x.get("kind") == "stock" and x.get("target") == p["id"]]
        if p["stock"] == 0:
            return (f"{p['name']}: sold out (0 in stock)" + (f", selling {week} a week before it ran out" if week else "") + ". " +
                    ("A restock proposal is already waiting for your tap. " if pend else "I don't know a restock date — the supplier's lead time is usually 1–3 weeks. ") +
                    f"Tell me “we received N more {p['name'].split(' (')[0].lower()}” when the goods land and it goes back on sale; meanwhile the page shows 'sold out' and takes e-mails." if not back else
                    f"{p['name']} is out (0 left) and I have no delivery date from a supplier yet. Say “order 20 more {p['name'].split(' (')[0].lower()}” to put the reorder on the plan, or “we received N more …” when they arrive — then it's back online the same minute.")
        if back:
            return f"{p['name']} isn't out — {p['stock']} in stock" + (f", ~{p['stock'] / max(week, 1) * 7:.0f} days at the current pace" if week else "") + "."
        flag = " ⚠️ low — reorder soon" if p["stock"] <= 3 else ""
        return f"Yes — {p['name']}: {p['stock']} in stock{flag}, {_eur(p['price'])}" + (f", selling {week} a week" if week else "") + "."

    def price_with_shipping(self, qty, what, where):
        p = self.store.find_product(what)
        if not p:
            return None
        low = where.lower().strip()
        code = next((c for w, c in (("germany", "DE"), ("germania", "DE"), ("france", "FR"), ("francia", "FR"), ("spain", "ES"), ("spagna", "ES"), ("italy", "IT"), ("italia", "IT"), ("austria", "AT"), ("netherlands", "NL"), ("olanda", "NL"),
                                     ("belgium", "BE"), ("portugal", "PT"), ("poland", "PL"), ("ireland", "IE"), ("greece", "GR"), ("sweden", "SE"), ("denmark", "DK"), ("finland", "FI"), ("uk", "GB"), ("switzerland", "CH"), ("svizzera", "CH"), ("usa", "US"), ("milan", "IT"), ("milano", "IT"), ("rome", "IT"), ("roma", "IT"), ("bergamo", "IT"), ("sicily", "IT"), ("sardinia", "IT"))
                     if re.search(r"\b" + w + r"\b", low)), None)
        if not code:
            return None
        sub = round(qty * p["price"], 2)
        ship = self.store.shipping_for(code, sub)
        if ship is None:
            return f"{qty} × {p['name']} = {_eur(sub)}, but we don't ship to {where.strip()} yet (EU only for now)."
        total = round(sub + ship, 2)
        free_note = " (free shipping — over € 39)" if ship == 0 else ""
        gap = ""
        if code == "IT" and ship > 0 and 39 - sub <= 15:
            gap = f" Tip: {_eur(39 - sub + 0.01)} more and shipping is free — the cart says so."
        cost = qty * p.get("cost", 0) + 2.9 + 0.35 * qty + 0.029 * total + 0.30
        return f"{qty} × {p['name']} to {code}: {_eur(sub)} + {_eur(ship)} shipping{free_note} = {_eur(total)} for the customer. Our side: ~{_eur(cost)} all-in, so about {_eur(total - cost)} stays.{gap}"

    def parcel_weight(self, qty, what):
        p = self.store.find_product(what)
        if not p:
            return None
        w = p.get("weight_g") or 300
        box = 150 if w * qty < 1000 else 300
        total = w * qty + box + 60
        band = "≤ 1 kg" if total <= 1000 else "≤ 2 kg" if total <= 2000 else "≤ 3 kg" if total <= 3000 else "≤ 5 kg"
        price = {"≤ 1 kg": "€ 5,65", "≤ 2 kg": "€ 5,90", "≤ 3 kg": "€ 6,70", "≤ 5 kg": "€ 7,30"}[band]
        return (f"{qty} × {p['name']}: {w * qty} g of product + box and padding ~{box + 60} g ≈ {total / 1000:.2f} kg → the {band} band (Poste Delivery Web {price} in Italy; Packlink similar). "
                + ("Keep it under 2 kg and it's the cheap band everywhere in the EU." if total <= 2000 else "Above 2 kg the EU price jumps — split into two parcels only if the customer pays for both."))

    def refunds_list(self, t):
        st = self.store
        label, keep = self._period(t)
        os_ = [o for o in st.data["orders"] if keep(o)]
        bad = [o for o in os_ if o["status"] in ("refunded", "cancelled", "return_requested")]
        lose = bool(re.search(r"\b(lose|lost|losing|money)\b", t.lower()))
        if not st.data["orders"]:
            return "No orders yet, so no refunds either. Say “run a practice day” and customers come."
        if not bad:
            return f"None {label} — no refunds, returns or cancellations" + (f" across {len(os_)} orders." if os_ else ".") + (" So no order lost money: every one covered goods, postage and fees." if lose else "")
        rows = []
        loss_total = 0.0
        for o in bad:
            fee = 0.029 * o["total"] + 0.30
            loss = fee + ((2.9 + 0.35 * sum(l["qty"] for l in o["lines"]) + sum(l["qty"] * l.get("cost", 0) for l in o["lines"])) if (o["status"] == "refunded" and o.get("tracking")) else 0)
            loss_total += loss
            rows.append(f"• #{o['n']} {o['customer'].get('name', '')} ({o['country']}) — {o['status']}, {_eur(o['total'])}" + (f", cost us {_eur(loss)}" if lose or loss > 1 else ""))
        rate = len([o for o in bad if o["status"] == "refunded"]) / max(1, len(os_)) * 100
        return (f"{len(bad)} {label}:\n" + "\n".join(rows[:8]) + f"\nThat's {rate:.0f} % of orders refunded" + (f"; total loss {_eur(loss_total)} (gateway fees stay paid; a shipped refund also loses goods + postage)" if lose or loss_total else "") +
                (" — under 3 % is normal for home goods." if rate < 3 else " — above 3 %: look at the reasons (packaging? photos vs reality?)."))

    def sold_today(self, when):
        st = self.store
        day = st.data.get("day", 0)
        if not st.data["orders"]:
            return "Nothing yet — the practice store hasn't had a practice day. Say “run a practice day” and customers come."
        d = day - 1 if when in ("yesterday", "ieri") else None
        if when in ("this week", "questa settimana"):
            os_ = [o for o in st.data["orders"] if o.get("day", 0) > day - 7 and o["status"] != "cancelled"]
            lab = "this week"
        else:
            os_ = [o for o in st.data["orders"] if o.get("day") == (d if d is not None else day) and o["status"] != "cancelled"]
            lab = "yesterday" if d is not None else "today"
        if not os_:
            return f"Nothing sold {lab}" + (f" (practice day {day}); {sum(v for k, v in st.data.get('visits', {}).items() if int(k) == day)} visits though — the shop was seen, nobody bought. A post or a small bundle usually moves it." if lab == "today" else ".")
        units = {}
        for o in os_:
            for l in o["lines"]:
                units[l["name"].split(" (")[0]] = units.get(l["name"].split(" (")[0], 0) + l["qty"]
        rev = sum(o["total"] for o in os_)
        return f"Yes — {len(os_)} order(s) {lab}, {_eur(rev)}: " + ", ".join(f"{k} ×{v}" for k, v in sorted(units.items(), key=lambda x: -x[1])) + f". {len([o for o in os_ if o['status'] == 'paid'])} still to ship."

    def items_total(self, t):
        st = self.store
        label, keep = self._period(t)
        paid = [o for o in st.data["orders"] if keep(o) and o["status"] in ("paid", "shipped", "delivered")]
        if not st.data["orders"]:
            return "No sales yet — the practice store hasn't had a practice day."
        n = sum(l["qty"] for o in paid for l in o["lines"])
        units = {}
        for o in paid:
            for l in o["lines"]:
                units[l["name"].split(" (")[0]] = units.get(l["name"].split(" (")[0], 0) + l["qty"]
        return f"Items sold {label}: {n} in {len(paid)} orders ({n / max(1, len(paid)):.1f} per order) — " + ", ".join(f"{k} {v}" for k, v in sorted(units.items(), key=lambda x: -x[1])) + "."

    def reorder_list(self):
        st = self.store
        day = st.data.get("day", 0)
        rows = []
        for p in st.products():
            sold14 = sum(l["qty"] for o in st.data["orders"] if o["status"] in ("paid", "shipped", "delivered") and o.get("day", 0) > day - 14 for l in o["lines"] if l["id"] == p["id"])
            weekly = sold14 / 2
            weeks = (p["stock"] / weekly) if weekly else None
            if p["stock"] == 0 or (weeks is not None and weeks < 3) or p["stock"] <= 3:
                need = int(max(10, round((weekly * 7 - p["stock"]) / 5.0) * 5)) if weekly else 10
                rows.append((p, weekly, weeks, need))
        if not rows:
            return "Nothing to reorder: every product has more than 3 weeks of stock at the current pace. Check again next week (say “what do I need to reorder?”)."
        lines = [f"• {p['name']}: {p['stock']} left" + (f", ~{weeks:.0f} week(s) at {weekly:.1f}/week" if weeks is not None else ", no recent sales") + f" → order ~{need} ({_eur(need * p.get('cost', 0))})" for p, weekly, weeks, need in rows]
        total = sum(need * p.get("cost", 0) for p, _, _, need in rows)
        return "Reorder list (3 weeks lead time + 4 weeks cover):\n" + "\n".join(lines) + f"\nCash needed: {_eur(total)}. Say “order 20 more <product>” for each and I put it on the plan; “we received N more <product>” when it lands."

    def top3(self, t):
        st = self.store
        day = st.data.get("day", 0)
        items = []
        try:
            late = [o for o in st.data["orders"] if o["status"] == "paid" and day - o.get("day", day) >= 1]
            open_ = [o for o in st.data["orders"] if o["status"] == "paid"]
            if late:
                items.append((0, f"Ship the {len(late)} late order(s) (#" + ", #".join(str(o['n']) for o in late[:4]) + ") — promised next-day. Say “print the shipping labels”."))
            elif open_:
                items.append((1, f"Ship today's {len(open_)} order(s) — say “print the shipping labels”, then “all shipped”."))
        except Exception:
            pass
        try:
            new = self.inbox.items("new") if self.inbox is not None else []
            if new:
                items.append((0, f"Answer the {len(new)} customer message(s) waiting — /inbox (drafts are ready for your tap)."))
        except Exception:
            pass
        try:
            out = [p for p in st.products() if p["stock"] == 0]
            low = [p for p in st.products() if 0 < p["stock"] <= 3]
            if out:
                items.append((1, "Reorder " + ", ".join(p["name"].split(" (")[0] for p in out) + " (sold out) — say “what do I need to reorder?”."))
            elif low:
                items.append((2, "Reorder " + ", ".join(p["name"].split(" (")[0] for p in low) + " (≤ 3 left)."))
        except Exception:
            pass
        try:
            props = [p for p in st.data.get("proposals", []) if p["status"] == "open"]
            if props:
                items.append((2, f"Decide on {len(props)} store proposal(s) waiting for your tap — /store."))
        except Exception:
            pass
        try:
            due = [x for x in (self.memory.open_items() if self.memory else []) if x.get("due") and x["due"][:10] <= _dt.date.today().isoformat()]
            for x in due[:2]:
                items.append((1, re.sub(r" \(⏰ .*\)$", "", x["text"])[:80] + " (your reminder)."))
        except Exception:
            pass
        items.append((3, "Post once today — say “what should I post today?” and I give you the photo + caption."))
        items.append((4, "Look at the week's numbers for 2 minutes — say “how's the week going?”."))
        items.sort(key=lambda x: x[0])
        return "Top 3 for today:\n" + "\n".join(f"{i + 1}. {txt}" for i, (_, txt) in enumerate(items[:3])) + ("\n(then: " + items[3][1] + ")" if len(items) > 3 else "")

    def best_customer(self):
        st = self.store
        paid = [o for o in st.data["orders"] if o["status"] in ("paid", "shipped", "delivered")]
        if not paid:
            return "No customers yet — the practice store hasn't sold anything. Say “run a practice day”."
        agg = {}
        for o in paid:
            c = o.get("customer") or {}
            key = (c.get("email") or c.get("name") or str(o["n"])).lower()
            a = agg.setdefault(key, {"name": c.get("name", key), "country": o.get("country", ""), "n": 0, "total": 0.0})
            a["n"] += 1
            a["total"] += o["total"]
        top = sorted(agg.values(), key=lambda a: (-a["n"], -a["total"]))[:3]
        rep = [a for a in agg.values() if a["n"] > 1]
        return (f"Best customers so far ({len(agg)} people, {len(paid)} orders):\n" + "\n".join(f"• {a['name']} ({a['country']}) — {a['n']} order(s), {_eur(a['total'])}" for a in top) +
                (f"\n{len(rep)} came back for a second order — send them a thank-you note with COMEBACK10; repeat buyers are worth 3× a new one." if rep else
                 "\nNo repeat buyers yet — normal in the first weeks; the card in the parcel and one e-mail after 3 weeks are what bring them back.") +
                "\n(Names stay here between us — never in posts or documents.)")

    def product_fact(self, t):
        """'does the lamp come with a charger?', 'is the mug dishwasher safe?' — answered from the product's own detail lines."""
        p = self.store.find_product(t)
        if not p:
            return None
        low = t.lower()
        details = list(p.get("details") or [])
        if p.get("short"):
            details.insert(0, p["short"])
        if p.get("options"):
            for k, v in p["options"].items():
                details.append(f"{k}: " + ", ".join(v))
        if p.get("weight_g"):
            details.append(f"Weight: {p['weight_g']} g")
        keys = {"dishwasher": ["dishwasher"], "lavastoviglie": ["dishwasher"], "microwave": ["microwave"], "charger": ["charging", "adapter", "cable"], "adapter": ["adapter", "charging"], "cable": ["cable", "charging"],
                "battery": ["battery"], "charge": ["charging", "battery"], "charging": ["charging", "battery"], "hours": ["battery", "hours"], "last": ["battery", "lasts", "year"], "warranty": ["warranty"], "garanzia": ["warranty"],
                "waterproof": ["waterproof", "water-resistant", "water"], "material": ["material", "made", "cotton", "bamboo", "cork", "stoneware", "beech", "aluminium", "nylon", "tpu"], "made of": ["material", "made", "cotton", "bamboo", "cork", "stoneware", "beech", "aluminium"],
                "made in": ["made in"], "size": ["size", "cm", "capacity", "ml"], "dimensions": ["size", "cm"], "dimension": ["size", "cm"], "big": ["size", "cm", "capacity"], "weigh": ["weight"], "weight": ["weight"], "heavy": ["weight"], "capacity": ["capacity", "ml"], "ml": ["capacity", "ml"],
                "colour": ["colour"], "color": ["colour"], "colours": ["colour"], "colors": ["colour"], "model": ["model", "iphone", "samsung"], "models": ["model", "iphone", "samsung"], "iphone": ["iphone"], "samsung": ["samsung"], "fit": ["iphone", "samsung", "model", "size"], "fits": ["iphone", "samsung", "model", "size"],
                "bristles": ["bristles"], "plastic": ["plastic", "bpa", "packaging"], "lead": ["lead-free"], "vegan": ["beeswax", "cotton"], "safe": ["safe", "bpa", "lead-free"], "include": ["included", "set of", "cable"], "included": ["included", "set of", "cable"], "box": ["included", "cable", "packaging"], "come with": ["included", "cable"], "comes with": ["included", "cable"],
                "meat": ["meat"], "wash": ["wash", "dishwasher"], "washable": ["wash", "dishwasher"], "light": ["light", "brightness", "k"], "bright": ["brightness"], "usb": ["usb"], "wireless": ["wireless"], "sizes": ["set of", "size"], "replace": ["replace"]}
        wanted = []
        for k, v in keys.items():
            if re.search(r"\b" + re.escape(k) + r"\b", low):
                wanted.extend(v)
        if not wanted:
            return None
        hits = [d for d in details if any(w in d.lower() for w in wanted)]
        neg = re.search(r"\b(not|no|never|non)\b", " ".join(hits).lower()) if hits else None
        if not hits:
            return (f"The {p['name']} page doesn't say — I only answer customers from what's written there. What I have: " + "; ".join(details[:4]) +
                    ". Tell me the fact (“the lamp comes with a cable, no adapter”) and I add it to the page for your tap.")
        yesno = ""
        if re.match(r"^\W*(is|are|does|do|can|will|has|have|comes?)\b", low):
            yesno = ("Yes — " if not neg else "Careful — ")
        ans = yesno + "; ".join(hits[:3]) + "."
        if re.search(r"\bcustomer|cliente|say|tell|answer|reply|rispond", low):
            ans += f"\nFor the customer: “{hits[0].rstrip('.')} — it's in the product details on the page. Anything else I can help with?”"
        return f"{p['name']}: {ans}"

    def late_orders(self):
        st = self.store
        day = st.data.get("day", 0)
        late = [o for o in st.data["orders"] if o["status"] == "paid" and day - o.get("day", day) >= 1]
        stuck = [o for o in st.data["orders"] if o["status"] == "shipped" and day - o.get("day", day) >= 7]
        if not st.data["orders"]:
            return "No orders yet, so nothing can be late. Say “run a practice day” and customers come."
        if not late and not stuck:
            return "Nothing is late: every paid order left within a day and no shipped parcel is older than a week. 👍"
        lines = []
        if late:
            lines.append(f"Late to ship ({len(late)} — promised 'ships within 1 business day'):\n" + "\n".join(f"• #{o['n']} {o['customer'].get('name', '')} ({o['country']}) — paid on day {o.get('day')}, {day - o.get('day', day)} day(s) ago — {', '.join(l['name'] + ' ×' + str(l['qty']) for l in o['lines'])}" for o in late[:8]))
        if stuck:
            lines.append(f"Shipped but not delivered after 7+ days ({len(stuck)}): " + ", ".join(f"#{o['n']} → {o.get('tracking', 'no tracking')}" for o in stuck[:6]) + " — open a trace with GLS and tell the customers you did.")
        lines.append("Say “print the shipping labels” then “all shipped”, or “ship order <number>” one by one.")
        return "\n".join(lines)

    def who_bought(self, what):
        p = self.store.find_product(what)
        if not p:
            return None
        buyers = [(o, sum(l["qty"] for l in o["lines"] if l["id"] == p["id"])) for o in self.store.data["orders"] if any(l["id"] == p["id"] for l in o["lines"]) and o["status"] != "cancelled"]
        if not buyers:
            return f"Nobody has bought {p['name']} yet."
        rows = [f"• #{o['n']} {o['customer'].get('name', '')} ({o['country']}) — ×{q}, day {o.get('day')}, {o['status']}" for o, q in buyers[-8:]]
        return f"{p['name']} — {len(buyers)} order(s), {sum(q for _, q in buyers)} unit(s):\n" + "\n".join(rows) + "\n(Customer details stay in the store; I never put names in posts or documents.)"

    def margin_on(self, what):
        p = self.store.find_product(what)
        if not p:
            return None
        price, cost = p["price"], p.get("cost", 0)
        fee = 0.029 * price + 0.30
        gross = price - cost
        net = gross - fee
        net_ship = net - 3.25
        return (f"{p['name']} at {_eur(price)}: cost {_eur(cost)} → gross margin {_eur(gross)} ({gross / price * 100:.0f} %); after the payment fee {_eur(fee)} → {_eur(net)} ({net / price * 100:.0f} %); "
                f"if the order gets free shipping another −€ 3,25 → {_eur(net_ship)} ({net_ship / price * 100:.0f} %). "
                + ("Thin: below ~45 % one refund wipes out three sales — consider " + _eur(round(cost / 0.4 + 0.09, 0) - 0.10) + "." if net / price < 0.45 else "Healthy — enough room for a promo and the odd refund."))

    def sold_when(self, when):
        st = self.store
        day = st.data.get("day", 0)
        it = when in ("ieri", "oggi", "questa settimana", "la settimana scorsa")
        when_en = {"ieri": "yesterday", "oggi": "today", "questa settimana": "this week", "la settimana scorsa": "last week"}.get(when, when)
        if when_en == "yesterday":
            keep = lambda o: o.get("day") == day - 1
        elif when_en == "today":
            keep = lambda o: o.get("day") == day
        elif when_en == "this week":
            keep = lambda o: o.get("day", 0) > day - 7
        elif when_en == "last week":
            keep = lambda o: day - 14 < o.get("day", 0) <= day - 7
        else:
            keep = lambda o: True
        paid = [o for o in st.data["orders"] if o["status"] in ("paid", "shipped", "delivered") and keep(o)]
        if not paid:
            return (f"Ieri non abbiamo venduto nulla" if it and when_en == "yesterday" else f"Nothing sold {when_en}") + (f" (practice day {day - 1})." if when_en == "yesterday" else ".")
        units = {}
        for o in paid:
            for l in o["lines"]:
                units[l["name"]] = units.get(l["name"], 0) + l["qty"]
        rev = sum(o["total"] for o in paid)
        return f"Sold {when_en}: {len(paid)} order(s), {_eur(rev)} — " + ", ".join(f"{k} ×{v}" for k, v in sorted(units.items(), key=lambda x: -x[1])) + "."

    def stock_value(self, t):
        st = self.store
        day = st.data.get("day", 0)
        rows, total_cost, total_retail = [], 0.0, 0.0
        sold14 = {}
        for o in st.data["orders"]:
            if o["status"] in ("paid", "shipped", "delivered") and o.get("day", 0) > day - 14:
                for l in o["lines"]:
                    sold14[l["id"]] = sold14.get(l["id"], 0) + l["qty"]
        for p in st.products():
            c = p["stock"] * p.get("cost", 0)
            total_cost += c
            total_retail += p["stock"] * p["price"]
            daily = sold14.get(p["id"], 0) / 14
            days = f"{p['stock'] / daily:.0f} days" if daily else ("out" if p["stock"] == 0 else "no sales in 14 days")
            rows.append(f"• {p['name']}: {p['stock']} pcs = {_eur(c)} at cost · {days} of stock")
        return (f"Stock: {_eur(total_cost)} tied up at cost (worth {_eur(total_retail)} at retail):\n" + "\n".join(rows) +
                "\nRule of thumb: 4–8 weeks of stock per product; more than 12 weeks is cash asleep — discount or bundle it; less than 3 is a reorder.")

    def out_of_stock_script(self, what):
        p = self.store.find_product(what) if what else None
        name = p["name"] if p else (what or "the product")
        return (f"When someone asks for {name} while it's out of stock — three lines, never “soon”:\n"
                f"“Hi <name>, thanks for asking! {name} is sold out right now; the next batch is due on <date> (say the real date, or 'in about 2 weeks'). "
                f"I can e-mail you the moment it's back — want me to? Meanwhile <similar product> is in stock if you need one sooner.”\n"
                "On the product page: keep it visible with a 'notify me' button (those e-mails convert 20–30 %), show the restock date, and never take money for stock you don't have."
                + (f"\nSay “we received 20 more {name.split(' (')[0].lower()}” when the goods arrive and I put it back on sale." if p else ""))

    def bank_transfer(self, t):
        it = bool(re.search(r"\b(bonifico|contrassegno|va bene|posso)\b", t.lower()))
        if re.search(r"\b(cash on delivery|contrassegno|pay (?:on|at) delivery)\b", t, re.I):
            return ("Cash on delivery (contrassegno): possible in Italy but I'd say no for a small shop — the courier charges € 3–5 extra, 10–20 % of COD parcels are refused and come back at your cost, and you get the money 2–3 weeks later. "
                    "If you really want it: charge the COD fee to the customer, only for Italy, only under € 100.")
        if re.search(r"\b(crypto|bitcoin|friends|family)\b", t, re.I):
            return "No — crypto and PayPal 'friends & family' have no buyer or seller protection and no paper trail for the accountant. Cards / PayPal goods & services / bank transfer only."
        txt = ("Bank transfer — yes, it's fine and common in Italy/Germany, with three rules: (1) ship only when the money is on the account (1–2 business days SEPA), never on a screenshot; "
               "(2) put the order number in the payment reference so you can match it; (3) if nothing arrives in 5 days, cancel and release the stock. "
               "It costs you no fee (cards take 2,9 % + € 0,30), but there's no chargeback protection for the customer either — so keep it as an option next to cards, not instead of them. "
               "Tell the customer: “Sure — IBAN <…>, reference <order number>; we ship the day the transfer lands and e-mail you the tracking.”")
        if it:
            txt = ("Bonifico — sì, va benissimo (in Italia e Germania è normale), con tre regole: (1) spedisci solo quando i soldi sono sul conto (1–2 giorni SEPA), mai su uno screenshot; "
                   "(2) numero d'ordine nella causale; (3) se in 5 giorni non arriva nulla, annulla e libera la scorta. Nessuna commissione (le carte costano 2,9 % + € 0,30), ma niente protezione chargeback per il cliente: tienilo come opzione accanto alle carte, non al posto.")
        return txt

    def bulk_discount(self, n, what):
        p = self.store.find_product(what) if self.store is not None else None
        if p:
            price, cost = p["price"], p.get("cost", 0)
            fee = 0.029 * price + 0.30
            unit = price - cost - fee
            disc = 0.10 if n >= 10 else 0.05 if n >= 5 else 0.0
            newp = round(price * (1 - disc), 2)
            saved_ship = 3.25 * (n - 1) * 0.5                                             # one parcel instead of many — rough
            return (f"{n} × {p['name']}: at full price you make {_eur(unit * n)} ({_eur(unit)} each after fees). "
                    + (f"Yes, offer −{disc * 100:.0f} % ({_eur(newp)} each): you still make {_eur((newp - cost - 0.029 * newp - 0.30) * n)}, one parcel instead of {n}, and a bulk buyer is often a repeat buyer (a café, an office). "
                       f"Say it as “{disc * 100:.0f} % off from {10 if n >= 10 else 5} pieces” so it looks like a rule, not a favour. Do check stock first: {p['stock']} in stock." if disc else
                       f"Under 5 pieces I wouldn't discount — free shipping is a better gift (costs you ~€ 3–4, feels like more)."))
        return (f"{n} pieces of {what}: as a rule −5 % from 5 pieces, −10 % from 10, −15 % from 25, never below 2× your cost; or free shipping instead of a discount for small lots. "
                "State it as a rule (“10 % off from 10 pieces”), invoice it properly, and check the stock before you promise.")

    def fees_paid(self, t):
        st = self.store
        label, keep = self._period(t)
        paid = [o for o in st.data["orders"] if o["status"] in ("paid", "shipped", "delivered") and keep(o)]
        if not paid:
            return f"No paid orders {label}, so no payment fees yet."
        rev = sum(o["total"] for o in paid)
        fees = sum(0.029 * o["total"] + 0.30 for o in paid)
        return (f"Payment fees {label}: {_eur(fees)} on {_eur(rev)} of sales ({fees / rev * 100:.1f} %, {len(paid)} orders at 2,9 % + € 0,30 each). "
                f"The fixed € 0,30 hurts on small baskets — a higher average order (bundles, free-shipping threshold) lowers the percentage. "
                f"Above ~€ 5.000 a month ask the provider for a lower rate; European cards via a local acquirer often cost 1,4–1,8 %.")

    def set_free_shipping(self, amt, code="IT"):
        st = self.store
        row = next((r for r in st.ship_rules() if r[0] == code), None)
        if row is None:
            return f"We don't ship to {code} yet — say “open shipping to {code} at <price>” first."
        old = row[2]
        if old and abs(old - amt) < 0.01:
            return f"Free shipping over {_eur(amt)} is already the rule for {code}."
        paid = [o for o in st.data["orders"] if o["status"] in ("paid", "shipped", "delivered") and o.get("country") == code]
        aov = sum(o["total"] for o in paid) / len(paid) if paid else None
        note = ""
        if aov:
            hit = len([o for o in paid if o.get("subtotal", o["total"]) >= amt]) / len(paid) * 100
            note = f" With the orders so far ({code} average basket {_eur(aov)}), {hit:.0f} % of them would have shipped free"
            note += " — it eats margin without changing behaviour." if hit > 60 else " — fine: it's reachable but not a giveaway." if hit >= 20 else " — almost nobody reaches it; it won't move baskets."
        return {"store_change": {"kind": "shipping", "code": code, "cost": row[1], "free_over": amt,
                                 "text": f"Free shipping in {code} over {_eur(amt)}" + (f" (was over {_eur(old)})" if old else " (was: never free)") + f"; the cart, checkout and shipping page follow.{note}"}}

    def set_ship_price(self, code, cost, free_over=None):
        st = self.store
        row = next((r for r in st.ship_rules() if r[0] == code), None)
        if row is not None and abs(row[1] - cost) < 0.01 and free_over is None:
            return f"Shipping to {code} is already {_eur(cost)}."
        real = {"IT": "€ 5–7", "DE": "€ 8–10", "FR": "€ 9–11", "ES": "€ 9–11", "EU": "€ 9–13", "CH": "€ 20–25 + customs", "GB": "€ 20–25 + customs", "US": "€ 40+"}.get(code, "€ 9–13")
        return {"store_change": {"kind": "shipping", "code": code, "cost": cost, "free_over": free_over,
                                 "text": (f"Shipping to {code}: {_eur(row[1])} → {_eur(cost)}" if row is not None else f"Open shipping to {code} at {_eur(cost)}") +
                                         (f", free over {_eur(free_over)}" if free_over else "") + f" — live at checkout and on the shipping page. (A real courier costs about {real} for a small parcel there; the difference is yours to absorb or not.)"}}

    def why_not_selling(self, what):
        st = self.store
        p = st.find_product(what) if what else None
        if not p:
            return None
        day = st.data.get("day", 0)
        views = None
        sold = sum(l["qty"] for o in st.data["orders"] if o["status"] in ("paid", "shipped", "delivered") for l in o["lines"] if l["id"] == p["id"])
        reasons = []
        if p["stock"] == 0:
            reasons.append("it's OUT OF STOCK — nobody can buy it; the page shows 'sold out'. That's the whole reason until you restock (say “we received 20 more …”).")
        if p["price"] and (p["price"] - p.get("cost", 0)) / p["price"] > 0.72:
            reasons.append(f"the price ({_eur(p['price'])}) is high for the category — compare it: say “compare prices for {p['name'].split(' (')[0].lower()}”.")
        if not p.get("short"):
            reasons.append("the page has no description — a bare name doesn't sell; say “write a description for …”.")
        if len(p.get("details", [])) < 3:
            reasons.append("few details on the page (size, material, care) — buyers leave when a question isn't answered.")
        if day < 7:
            reasons.append(f"it's only day {day} — with ~40 visits a day a product at 2 % conversion sells about one every 1–2 days; too early to judge.")
        if not reasons:
            reasons.append("the page looks fine, so it's traffic: nobody sees it. Put it in a post this week and in the 'you may also like' of the best seller, then judge after 14 days.")
        return (f"{p['name']} — {sold} sold so far, {p['stock']} in stock. Why it isn't moving:\n" + "\n".join(f"• {r}" for r in reasons) +
                "\nOrder of fixes: stock → price vs market → page (photo, first sentence, details) → traffic (posts, bundles). One change at a time, a week each.")

    def page_language(self, page, lang, t):
        key = ("shipping" if re.match(r"(shipping|spedizion)", page) else "returns" if re.match(r"(return|resi)", page) else "faq" if page.startswith("faq") else
               "contact" if re.match(r"(contact|contatti)", page) else "")
        lang = self.LANGS.get(lang.lower(), lang.title()) if lang else ""
        if key and lang:
            body = self.store.data.get("pages", {}).get(key, "")
            if not body:
                return f"The store has no {key} page yet."
            return {"translate": body, "to": lang, "page": key}
        return ("Bilingual shop — the practice store speaks one language per page for now. Two ways: (1) I translate the four help pages (say “translate the shipping page into English”) and the product descriptions one by one, and you tap Apply on each; "
                "(2) for the real shop, most platforms (Shopify Translate & Adapt, WooCommerce + Polylang) hold both languages properly — pick the platform first. Product names, prices and legal pages must be identical in both languages.")

    # ---- growth questions: first customers, ads money, VAT, bio -------------------------------------------
    def first_customers(self, t):
        it = bool(re.search(r"\b(come|primi|clienti)\b", t.lower()))
        name = self.store.data.get("name", "the shop").split(" —")[0] if self.store is not None else "the shop"
        en = ("First customers — in this order, cheapest first (weeks 1–4):\n"
              "1. People who already know you: one honest message to friends/family/colleagues with the link and 'tell me what's confusing'. Aim: 5 orders and 5 pieces of feedback, not profit.\n"
              "2. One channel, daily: pick TikTok or Instagram Reels (not both), 1 short video a day for 30 days — the product in use, the packing, a mistake you made. Say “tiktok ideas for <product>” and I write them.\n"
              "3. Marketplaces as a side door: the same product on Etsy/eBay/Vinted brings buyers who would never find your site; move them to your shop with a card in the parcel (say “write a thank-you note”).\n"
              "4. Local: 2–3 shops or cafés that match the product, 10 pieces on consignment; a market stall one Saturday = 50 real conversations.\n"
              "5. Only then paid ads: € 5–10 a day on the one video that already worked organically (say “I have 200 euros for ads”).\n"
              "What NOT to do: giveaways for followers, buying followers, 10 % discount pop-ups on day one, five platforms at once.\n"
              f"Measure: visits, add-to-carts and orders per week — say “how are we doing compared to last week” and I read them from {name}.")
        itx = ("Primi clienti — in quest'ordine, prima le cose gratis (settimane 1–4):\n"
               "1. Chi già ti conosce: un messaggio onesto ad amici/colleghi con il link e 'dimmi cosa non è chiaro'. Obiettivo: 5 ordini e 5 feedback, non il profitto.\n"
               "2. Un canale solo, ogni giorno: TikTok o Reels (non entrambi), 1 video breve al giorno per 30 giorni — il prodotto in uso, l'imballaggio, un errore che hai fatto. Dimmi “idee tiktok per <prodotto>” e li scrivo.\n"
               "3. Marketplace come porta laterale: lo stesso prodotto su Etsy/eBay/Vinted porta compratori che non troverebbero mai il sito; portali nel tuo shop con un biglietto nel pacco.\n"
               "4. Locale: 2–3 negozi o bar in tema, 10 pezzi in conto vendita; un mercatino di sabato = 50 conversazioni vere.\n"
               "5. Solo dopo le ads: € 5–10 al giorno sul video che ha già funzionato da solo.\n"
               "Da NON fare: giveaway per follower, follower comprati, pop-up −10 % il primo giorno, cinque piattaforme insieme.")
        return itx if it else en

    def ads_budget(self, amt, t):
        assumed = amt is None
        amt = amt or 200.0
        per_month = bool(re.search(r"\b(a month|per month|al mese|monthly)\b", t, re.I))
        daily = amt / 30 if per_month else amt / 20
        test = min(amt, max(30.0, amt * 0.4))
        best = None
        if self.store is not None:
            try:
                ps = [p for p in self.store.products() if p["stock"] >= 5]
                best = max(ps, key=lambda p: p["price"] - p.get("cost", 0)) if ps else None
            except Exception:
                best = None
        prod = best["name"].split(" (")[0] if best else "your best-margin product with stock"
        return ((f"Start small — I'd put {_eur(amt)} on the table for a first test, not more (tell me your real figure and I redo the plan). " if assumed else "") +
                f"{_eur(amt)}{' a month' if per_month else ''} for ads — my plan (small budgets die when spread thin):\n"
                f"1. Spend € 0 for the first week: post 5–7 organic short videos of {prod}; the one with the best watch-time is your ad. Paying to promote an untested video is the classic way to lose {_eur(amt)}.\n"
                f"2. Then ONE platform (Meta = Instagram+Facebook for home/gift products 25–55; TikTok for under-35 impulse buys), ONE product ({prod}), ONE goal (sales/conversions, never 'engagement' or 'followers').\n"
                f"3. Test: {_eur(test)} over 5–7 days at ~{_eur(daily)} a day, 2–3 versions of the video, broad targeting (Italy, 25–55) — let the algorithm find the buyers.\n"
                f"4. Read the numbers on day 7: cost per purchase must be under a third of the margin ({_eur((best['price'] - best.get('cost', 0)) / 3) if best else '~€ 3–4'}). Under → put the rest of the money on that video; over → stop, fix the page or the price, don't add budget.\n"
                f"5. Keep {_eur(amt - test)} in reserve for the winner; never top up a loser.\n"
                "Before the first euro: the pixel/tracking installed, a product page that loads in 2 s on a phone, shipping cost visible, and stock for 30+ orders. I'll prepare the ad text and the shot list when you say “write the ad for {0}”.".format(prod))

    def ad_test(self):
        """'prepare the ad test' — the concrete first campaign: product, video, text, targeting, budget, stop rules. Nothing spent — the owner sets it up in Ads Manager."""
        st = self.store
        best, n = None, {}
        try:
            n = st.numbers()
            units = n.get("units", {})
            ps = [p for p in st.products() if p["stock"] >= 5]
            best = max(ps, key=lambda p: (units.get(p["name"], 0), p["price"] - p.get("cost", 0))) if ps else None
        except Exception:
            pass
        if not best:
            return "No product with enough stock for an ad test (I want 5+ units, ideally 30) — restock first; an ad that sells out on day 2 teaches nothing."
        name = best["name"].split(" (")[0]
        margin = best["price"] - best.get("cost", 0) - 0.029 * best["price"] - 0.30 - 3.25
        target_cpa = margin / 3
        facts = (best.get("details") or [])[:2]
        return (f"Ad test, ready to set up (Meta Ads Manager, ~15 minutes; nothing spent until you press Publish there):\n"
                f"• Product: {name} at {_eur(best['price'])} — {best['stock']} in stock, net margin about {_eur(margin)} per sale after goods, fees and shipping.\n"
                f"• Creative: the vertical video that got the best watch-time in the last week (if none yet: 15 s, {name} in a real room, hand in frame, text on screen “{facts[0][:40] if facts else 'made to last'}”, no music rights issues — use Meta's library).\n"
                f"• Primary text: “{name} — {facts[0][:60] if facts else 'the small upgrade you notice every day'}. Ships from Bergamo in 1 day, free over {_eur(39)}. 30-day returns.”  Headline: “{name} · {_eur(best['price'])}”  Button: Shop now → the product page.\n"
                "• Campaign: objective Sales (conversions), 1 campaign, 1 ad set, 2–3 ads (same video, different first line). Advantage+ audience, Italy, 25–55, all placements. Pixel installed and the Purchase event tested first.\n"
                "• Budget: € 6 a day for 7 days (€ 42), then decide. Not more — small budgets need 7 days to learn.\n"
                f"• Stop rules on day 7: cost per purchase under {_eur(target_cpa)} → double the budget for 7 more days; between {_eur(target_cpa)} and {_eur(margin)} → change the video, keep the rest; above {_eur(margin)} (losing money per sale) → stop, fix the page, back to organic.\n"
                "• Watch daily but don't touch it: CTR (link) above 1 %, cost per click under € 0,60, add-to-carts. Under 300 impressions nothing means anything.\n"
                "Say “write 3 ad texts” for variants, or “what should I post today?” for the organic side. Report back the day-7 numbers and I read them with you.")

    def show_drafts(self):
        new = self.inbox.items("new")
        if not new:
            return "No drafts waiting — every customer message has an answer. When one comes in you get it here with Approve / Edit / Reject."
        rows = []
        for r in new[:5]:
            try:
                k = self.inbox.classify(r["text"])["kind"].replace("_", " ")
            except Exception:
                k = "message"
            rows.append(f"• {r.get('from', '?')} — {k}: “{r['text'][:80]}”")
        return (f"{len(new)} draft(s) waiting:\n" + "\n".join(rows) + (f"\n…and {len(new) - 5} more" if len(new) > 5 else "") +
                "\nSay /inbox and each one arrives as a card with my draft and the buttons — or “send routine replies yourself” and the simple ones stop needing you.")

    def make_bundle(self, a, b, price):
        """'add the bundle' / 'add a bundle: mug + wraps at 24.90' → a new-product proposal from two real products (price default 10 % off the pair)."""
        st = self.store
        units = {}
        try:
            units = st.numbers().get("units", {})
        except Exception:
            pass
        pa = st.find_product(a) if a else None
        pb = st.find_product(b) if b else None
        if not (pa and pb):
            instock = [p for p in st.products() if p["stock"] > 0]
            if len(instock) < 2:
                return "A bundle needs two products in stock — right now there aren't two."
            best = max(instock, key=lambda p: units.get(p["name"], 0))
            slow = min([p for p in instock if p is not best], key=lambda p: units.get(p["name"], 0))
            pa, pb = best, slow
        if pa["id"] == pb["id"]:
            return "Both halves are the same product — name two different ones: “add a bundle: mug + wraps”."
        pair = pa["price"] + pb["price"]
        price = price or (round(pair * 0.9) - 0.10)                          # 10 % off, X,90 ending
        price = float(f"{price:.2f}")
        cost = pa.get("cost", 0) + pb.get("cost", 0)
        name = f"{pa['name'].split(' (')[0]} + {pb['name'].split(' (')[0]} Bundle"
        stock = min(pa["stock"], pb["stock"])
        return {"store_change": {"kind": "product", "name": name[:80], "price": price, "cost": round(cost, 2), "guessed": False, "stock": stock,
                                 "note": f"pair price {_eur(pair)} → bundle {_eur(price)} ({(1 - price / pair) * 100:.0f} % off), {(price - cost) / price * 100:.0f} % gross margin; stock follows the scarcer half ({stock})"}}

    def vat_on(self, amt, what, t):
        rate = 0.22
        if re.search(r"\b(book|libro|food|cibo|bread|pane|pasta|pasta|baby|infant|medic)\b", (what or "") + " " + t, re.I):
            rate = 0.04 if re.search(r"\b(book|libro|bread|pane|pasta|milk|latte)\b", (what or "") + " " + t, re.I) else 0.10
        net = amt / (1 + rate)
        vat = amt - net
        it = bool(re.search(r"\b(iva|quanto)\b", t.lower()))
        core = (f"IVA su {_eur(amt)} (prezzo al pubblico, IVA inclusa al {rate * 100:.0f} %): {_eur(vat)} di IVA, {_eur(net)} netto." if it else
                f"VAT on {_eur(amt)} (consumer price, VAT included at {rate * 100:.0f} %): {_eur(vat)} is VAT, {_eur(net)} is yours before costs.")
        return core + ("\nIn Italy consumer prices always include VAT. Regime forfettario: you don't charge VAT at all (and can't deduct it), so the {0} stays whole but your supplier's VAT is a cost. "
                       "Ordinary regime: you pay the state the {1} minus the VAT you paid suppliers. Selling to consumers in other EU countries above € 10.000/year → their VAT rate via OSS.").format(_eur(amt), _eur(vat)) if not it else \
               "\nIn forfettario l'IVA non si applica (e non si scarica): il prezzo resta intero ma l'IVA del fornitore è un costo. In regime ordinario versi l'IVA incassata meno quella pagata ai fornitori. Sopra € 10.000/anno di vendite UE → IVA del paese del cliente (OSS)."

    def shop_bio(self, t):
        st = self.store
        name = st.data.get("name", "Green Nest").split(" —")[0] if st is not None else "Your shop"
        prods = [p["name"].split(" (")[0].lower() for p in st.products()[:3]] if st is not None else ["products"]
        it = bool(re.search(r"\b(scrivi|profilo|negozio)\b", t.lower()))
        cats = ", ".join(prods[:2]) + (f" & {prods[2]}" if len(prods) > 2 else "")
        en = (f"Instagram bio for {name} (150 characters max — pick one, edit the city):\n"
              f"1. 🌿 {name} · everyday things that last\n📦 ships from Bergamo in 1 day · 🇮🇹 free shipping over € 39\n👇 shop\n"
              f"2. {name} — {cats}, chosen by hand, no plastic.\nSmall shop, real people. Orders ship next day 📦\n"
              f"3. Less stuff, better stuff. {cats}.\nQuestions? DM us — we answer within 24 h. 👇 shop\n"
              "Rules: what you sell + why you're different + one proof (ships in 1 day / made in …) + the link. No hashtags in the bio, no 'welcome to my page'. Put the link to the shop, not to a link tree, until you have 3+ things to link.")
        itx = (f"Bio Instagram per {name} (max 150 caratteri — scegline una):\n"
               f"1. 🌿 {name} · oggetti di tutti i giorni che durano\n📦 spediamo da Bergamo in 1 giorno · spedizione gratis da € 39\n👇 shop\n"
               f"2. {name} — {cats}, scelti a mano, zero plastica.\nPiccolo negozio, persone vere. Spedizione il giorno dopo 📦\n"
               f"3. Meno cose, cose migliori. {cats}.\nDomande? Scrivici in DM — rispondiamo entro 24 h. 👇 shop\n"
               "Regole: cosa vendi + perché sei diverso + una prova (spedito in 1 giorno / fatto in …) + il link. Niente hashtag in bio, niente 'benvenuti'.")
        return itx if it else en

    # ---- small maths, reminders, notes, guidance -------------------------------------------------------
    def maths(self, m):
        try:
            if m.group("a"):
                a, b = _num(m.group("a")), _num(m.group("b"))
                return f"{a:g} % of {b:g} = {a * b / 100:.2f}".replace(".00", "")
            if m.group("c"):
                c, d = _num(m.group("c")), _num(m.group("d"))
                return f"{c:g} + {d:g} % = {c * (1 + d / 100):.2f} (the {d:g} % is {c * d / 100:.2f})"
            if m.group("e"):
                e, f = _num(m.group("e")), _num(m.group("f"))
                return f"{e:g} − {f:g} % = {e * (1 - f / 100):.2f} (the {f:g} % is {e * f / 100:.2f})"
            expr = m.group("expr").replace(",", ".").replace("x", "*").replace("×", "*").replace("÷", "/").replace(":", "/")
            if not re.fullmatch(r"[\d.\s+\-*/()]+", expr):
                return None
            val = eval(expr, {"__builtins__": {}}, {})                            # digits and operators only (checked above)
            return f"{m.group('expr').strip()} = {val:.2f}".rstrip("0").rstrip(".") if isinstance(val, float) and val != int(val) else f"{m.group('expr').strip()} = {int(val)}"
        except Exception:
            return None

    def remind_at(self, when, what):
        """'remind me tomorrow at 9 to call the supplier' → a dated to-do; the daily check pings it when due."""
        import datetime as dt
        now = dt.datetime.now()
        low = when.lower()
        day = now.date()
        if re.search(r"\b(tomorrow|domani)\b", low):
            day = day + dt.timedelta(days=1)
        elif re.search(r"\b(next week|la settimana prossima)\b", low):
            day = day + dt.timedelta(days=(7 - now.weekday()) % 7 or 7)       # next Monday
        wd = {"monday": 0, "lunedì": 0, "tuesday": 1, "martedì": 1, "wednesday": 2, "mercoledì": 2, "thursday": 3, "giovedì": 3, "friday": 4, "venerdì": 4, "saturday": 5, "sabato": 5, "sunday": 6, "domenica": 6}
        for k, v in wd.items():
            if re.search(r"\b" + k + r"\b", low):
                ahead = (v - now.weekday()) % 7 or 7
                day = now.date() + dt.timedelta(days=ahead)
        mi = re.search(r"in (\d+) (hours?|minutes?|days?|ore|minuti|giorni)", low)
        hour, minute = 9, 0
        mt = re.search(r"(?:at|alle|alle ore)\s+(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)?", low)
        if mt:
            hour = int(mt.group(1)); minute = int(mt.group(2) or 0)
            if mt.group(3) == "pm" and hour < 12:
                hour += 12
        elif re.search(r"\b(tonight|stasera)\b", low):
            hour = 20
        due = dt.datetime.combine(day, dt.time(hour, minute))
        if mi:
            n, unit = int(mi.group(1)), mi.group(2)
            due = now + (dt.timedelta(hours=n) if unit.startswith(("hour", "ore")) else dt.timedelta(minutes=n) if unit.startswith("min") else dt.timedelta(days=n))
        if due <= now and not mi and not mt and not re.search(r"tomorrow|domani", low):
            due = due + dt.timedelta(days=1)
        what = what.strip(" .")
        n = self.memory.add(f"{what[0].upper() + what[1:]} (⏰ {due:%a %d %b %H:%M})")
        try:
            items = self.memory.todo["items"]
            items[-1]["due"] = due.isoformat(timespec="minutes")
            self.memory._save()
        except Exception:
            pass
        return f"Reminder set for {due:%A %d %B at %H:%M}: {what}. It's #{n} on your to-do list; I'll ping you here when it's time."

    def thank_note(self, t):
        it = bool(re.search(r"\b(italian|italiano|in italiano|scrivi|biglietto)\b", t, re.I)) and not re.search(r"\bin english\b", t, re.I)
        shop = (self.store.data.get("name", "the shop").split(" — ")[0] if self.store is not None else "the shop")
        if it:
            return (f"Biglietto per i pacchi (stampalo su un cartoncino 10×7 cm, firmalo a mano):\n\n"
                    f"Grazie per aver scelto {shop}!\nDietro questo pacco c'è una piccola attività: ogni ordine conta davvero.\n"
                    f"Se qualcosa non va, scrivici prima di tutto — sistemiamo tutto entro 24 ore.\nSe invece sei contento, una recensione o una foto con @{shop.lower().replace(' ', '')} ci aiuta più di qualsiasi pubblicità.\n"
                    f"— <il tuo nome>\n\n(Facoltativo: “-10 % sul prossimo ordine con il codice GRAZIE10” — fa tornare 1 cliente su 10.)")
        return (f"Thank-you card for the parcels (print on a 10×7 cm card, sign it by hand):\n\n"
                f"Thank you for choosing {shop}!\nThere's a small business behind this parcel — every order truly matters.\n"
                f"If anything isn't right, write to us first: we fix it within 24 hours.\nIf you're happy, a review or a photo tagging @{shop.lower().replace(' ', '')} helps us more than any ad.\n"
                f"— <your name>\n\n(Optional: “10 % off your next order with code THANKS10” — brings about 1 in 10 customers back. Say “in Italian” for the Italian version.)")

    def cancel_how(self, t):
        low = t.lower()
        if re.search(r"\b(refund|money back|rimborso)\b", low):
            return ("A customer who wants a refund — the rule first, then the tone:\n"
                    "• Not shipped yet → refund at once, no questions (EU right of withdrawal, and it saves the postage).\n"
                    "• Shipped, within 14 days of delivery → they can return it; refund within 14 days of getting it back (you may charge the return postage only if your returns page says so).\n"
                    "• Faulty/wrong item → refund or replace immediately, photo is enough, no return needed for cheap items.\n"
                    "Tone: one line of sorry, one line of what happens now, one line of when — no arguing. Forward me the message and I draft the reply for your approval.")
        if re.search(r"\b(where|tracking|arrived|late|dov'è)\b", low):
            return ("A customer asking where the order is — answer the same day, with facts from the order:\n"
                    "• Not shipped yet → “Your order ships on <date>; you'll get the tracking number by e-mail the moment it leaves.” Never say “soon”.\n"
                    "• Shipped → paste the tracking link and the expected delivery day; if it's late by 3+ days, open a trace with the courier yourself and tell them you did.\n"
                    "• Lost (no scan for 7+ days) → resend or refund at once; you claim from the courier, not the customer.\n"
                    "Forward me the message with the order number and I draft the exact reply from the store's ledger.")
        if re.search(r"\b(complain|angry|si lamenta)\b", low):
            return ("An angry customer: answer within the hour if you can, even just “I've seen it, I'm on it — answer by 17:00”. Then: facts (order, tracking, photo), the fix (resend/refund/replace), the date. "
                    "Never argue about who's right in writing; give the fix and move on. Forward me the message and I draft it.")
        return ("A customer who wants to cancel:\n"
                "• Order not shipped → cancel and refund right away; say so in one line with the refund timing (3–5 business days on card).\n"
                "• Already shipped → they can refuse the parcel or return it within 14 days of delivery (EU withdrawal); refund when it's back.\n"
                "• Custom/personalised items → no withdrawal right, but say it kindly and offer a discount code instead.\n"
                "Forward me the customer's message and I draft the exact reply (with the order status from the store) for your approval.")

    # ---- shop sense: things every shop owner asks -------------------------------------------------
    def shop_sense(self, t):
        low = t.lower()
        if self.BAD_REVIEW.search(t) and not self.CUSTOMER.search(t):
            return self.bad_review(t)
        if self.FREE_SHIP.search(t):
            return self.free_shipping()
        if self.COURIER.search(t) and not re.search(r"https?://|\b(compare|research|find|cerca|trova)\b", low):
            return self.couriers(t)
        if self.HASHTAGS.search(t):
            return self.hashtags(t)
        m = self.VIDEO_IDEAS.search(t)
        if m and not re.search(r"https?://|youtu|\b(watch|guarda)\b", low):
            return self.video_ideas(t, m.group("n"))
        return None

    def bad_review(self, t):
        """'a customer left a 1-star review saying the mug broke, what do I do?' → the three moves + a public reply draft."""
        product = None
        if self.store is not None:
            product = self.store.find_product(t)
        broke = re.search(r"\b(broke|broken|damaged|cracked|arrived (?:in pieces|broken)|rotto|rotta|danneggiato)\b", t, re.I)
        late = re.search(r"\b(late|slow|never arrived|still waiting|took (?:two|three|\d+) weeks|in ritardo|lenta|mai arrivato)\b", t, re.I)
        prod = product["name"] if product else ("slow shipping" if late else "the item")
        rude = re.search(r"\b(rude|ignored|no (?:answer|reply)|maleducat)", t, re.I)
        cause = "a broken item" if broke else "a late or missing delivery" if late else "bad service" if rude else "the problem"
        fix = ("we replace or refund faulty items at once — no return needed for a broken piece, a photo is enough" if broke else
               "we track the parcel with the courier today and refund or resend if it's lost" if late else
               "we look into what happened and make it right")
        draft = (f"Hi <name>, I'm sorry — {cause} is not what we want for you. We {fix.split(' — ')[0]}. "
                 f"I've written to you privately to sort it out today; please answer with your order number so I can send the replacement/refund right away. — <your name>, {self.store.data.get('name', 'the shop').split(' — ')[0] if self.store is not None else 'the shop'}")
        lesson = ("check the packaging for that product (double-wall box, bubble wrap around the item, nothing rattling) and the courier's damage rate" if broke else
                  "check the delivery promise on the product page against the real times, and send tracking numbers automatically" if late else
                  "answer every message within 24 hours; set a template for the common ones")
        return (f"A bad review about {prod} — three moves, in this order:\n"
                f"1. Fix it privately first (today): write to the customer, {fix}. Ask for a photo and the order number; don't argue about fault.\n"
                f"2. Answer publicly, short and calm, so the next 100 readers see how you handle problems. Draft:\n“{draft}”\n"
                f"3. Learn from it: {lesson}.\n"
                "Never offer money for deleting the review — most platforms ban it and it reads badly. If you forward me the customer's message I draft the private reply for your approval.")

    def free_shipping(self):
        avg, n, cat = None, 0, []
        if self.store is not None:
            try:
                paid = [o for o in self.store.data["orders"] if o["status"] in ("paid", "shipped", "delivered")]
                n = len(paid)
                avg = sum(o["subtotal"] for o in paid) / n if n else None
                cat = [p["price"] for p in self.store.products()]
            except Exception:
                pass
        base = avg if avg and n >= 3 else (sorted(cat)[len(cat) // 2] if cat else 25.0)
        thr = round(base * 1.3 + 0.5) - 0.01                                    # a bit above the average basket, X,99
        thr = max(19.99, min(thr, 99.99))
        why = f"your average basket (goods only, before shipping) so far is {_eur(avg)} over {n} orders" if avg and n >= 3 else (f"your typical product costs {_eur(base)}" if cat else "a typical small-shop basket is ~€ 25")
        return (f"Free shipping — yes, but as a threshold, not on everything. {why.capitalize()}, so I'd set “free shipping over {_eur(thr)}”: "
                f"shoppers add a second item to reach it (basket size usually rises 15–30 %), and you never pay € 4–7 of postage on a single € 12 item.\n"
                "Rules of thumb: (1) show the shipping cost before checkout and the “€ X to free shipping” bar in the cart; (2) below the threshold charge your real cost, rounded (€ 3,90 / 4,90 in Italy); "
                "(3) 'free' isn't free — either the margin covers it (2.5× cost or more) or the price already includes ~€ 3; (4) EU orders keep a fee (€ 6,90–9,90) or a higher threshold.\n"
                f"Say “set free shipping over {thr:.0f}” and I write it into the shipping page of the practice store.")

    def couriers(self, t):
        """'which courier is cheapest in italy for small parcels?' — public list prices (2026), the way a small shop starts, and when to get a contract."""
        eu = re.search(r"\b(europe|eu|germany|france|spain|abroad|estero|europa|germania|francia|international|internazionale)\b", t, re.I)
        lines = ["Cheapest way to ship small parcels from Italy (public prices, 2026 — check the live quote before you promise a fee):",
                 "• Poste Delivery Web (online, pickup at home included): € 5,65 up to 1 kg, € 5,90 up to 2 kg, € 6,70 up to 3 kg, € 7,30 up to 5 kg; 24–48 h with Express (+€ 1). From the post office counter it starts at € 10,30 — never pay counter prices.",
                 "• Comparators (Packlink, Spedire.com, SpedireSubito…): from € 5,48 up to 2 kg with GLS/BRT/SDA/TNT, pickup or drop-off; good for choosing per parcel, prices change weekly.",
                 "• Lockers/pickup points (InPost, GLS ParcelShop, Poste Punto Poste): usually the cheapest 1–2 kg option and customers like them; ask the price for your size in the app.",
                 "• Direct contract with GLS / BRT / SDA: list price ~€ 15 for 3 kg, but from ~10 parcels a month they give 30–60 % off and a pickup every day — that's when you switch (a national parcel lands at € 4–6).",
                 "• Envelopes ≤ 2 cm (phone case, wraps): Posta Raccomandata/Posta 4 Pro is cheaper than any parcel — ask the exact price at Poste Business."]
        if eu:
            lines.append("• Abroad: Germany from € 14,93 and France from € 17,56 via comparators; Poste Crono Internazionale from ~€ 20 up to 2 kg, 3 working days in the EU. That's why EU orders need a € 6,90–9,90 fee or a higher free-shipping threshold, and why heavy items should stay national at first.")
        lines.append("What decides the price: weight AND size (volumetric weight = L×W×H cm / 5000 or /4000), so use the smallest box; print labels at home; always send the tracking number.")
        lines.append("My advice for the start: Poste Delivery Web or a comparator for the first months (no contract, pay per parcel), weigh every product now so the shipping page is honest, then negotiate a contract once you ship 10+ parcels a month.")
        return "\n".join(lines)

    TAG_FAMILIES = {
        "eco": ["ecofriendly", "sustainableliving", "zerowaste", "plasticfree", "ecosostenibile", "greenliving", "consciousconsumer"],
        "home": ["homedecor", "casa", "interiorinspo", "cozyhome", "homestyle", "arredamento"],
        "kitchen": ["kitchenessentials", "cucina", "foodie", "mealprep", "homecooking"],
        "coffee": ["coffeelover", "coffeetime", "caffè", "espresso", "morningritual"],
        "phone": ["phonecase", "phoneaccessories", "iphonecase", "techaccessories", "cover"],
        "bamboo": ["bamboo", "bambootoothbrush", "plasticfreebathroom", "zerowastebathroom"],
        "candle": ["candles", "candlelover", "homefragrance", "candele", "cozyvibes"],
        "pet": ["dogsofinstagram", "petlovers", "doglife", "catsofinstagram", "petaccessories"],
        "baby": ["babyessentials", "newmom", "momlife", "babyshower", "neonato"],
        "fitness": ["fitnessmotivation", "homeworkout", "gymlife", "healthylifestyle", "allenamento"],
        "beauty": ["skincare", "cleanbeauty", "selfcare", "beautyroutine", "skincareroutine"],
        "fashion": ["ootd", "slowfashion", "outfitinspo", "madeinitaly", "styleinspo"],
        "jewel": ["jewelry", "handmadejewelry", "gioielli", "minimaljewelry", "earrings"],
        "garden": ["gardening", "plantsofinstagram", "urbangarden", "giardino", "plantlover"],
        "gift": ["giftideas", "giftsforher", "giftsforhim", "regali", "regaloperfetto"],
        "desk": ["desksetup", "workfromhome", "homeoffice", "studygram", "deskinspo"],
        "lamp": ["lighting", "lampdesign", "homelighting", "interiordesign"],
        "cork": ["cork", "sughero", "naturalmaterials", "veganleather"],
        "food": ["foodwraps", "mealprep", "lunchbox", "zerowastekitchen"],
    }

    def hashtags(self, t):
        """'what hashtags should I use for eco products?' → 12 tags in three sizes + the rules; built from the words, no browsing."""
        low = t.lower()
        topic = re.search(r"\b(?:for|per|about|su|on)\s+(?:my |our |the |a |an |i |le |gli |il |la )?(?P<x>[a-zà-ú][a-zà-ú0-9 \-']{2,50}?)(?:\s+(?:posts?|videos?|reels?|content|shop|store|brand)\b|\s*[?.!,]|$)", t, re.I)
        topic = (topic.group("x") if topic else "").strip()
        words = [w for w in re.findall(r"[a-zà-ú]{3,}", topic.lower()) if w not in ("the", "and", "our", "for", "with", "products", "product", "shop", "store", "items", "stuff", "things", "posts", "post")]
        fam = []
        for w in words + re.findall(r"[a-zà-ú]{4,}", low):
            for k, v in self.TAG_FAMILIES.items():
                if (k in w or w in k) and v not in fam:
                    fam.append(v)
        italian = bool(re.search(r"\b(ital(?:y|ia|ian)|milano|roma|negozio|per il|prodotti)\b", low))
        def clean(seq):
            out = []
            for x in seq:
                x = re.sub(r"[^a-z0-9à-ú]", "", x.lower())
                if x and x not in out:
                    out.append(x)
            return out
        big = clean(["smallbusiness", "shopsmall", "handmade" if re.search(r"hand|artigian", low) else "onlineshop"])
        medium = []
        for v in fam[:3]:                                                  # family tags: the first family gives 3, the others fill up to 5
            medium += v[:3] if not medium else v[:2]
        medium = [x for x in clean(medium) if x not in big][:5]
        if len(medium) < 3 and words:
            medium += clean([w.rstrip("s") + "life" for w in words[:2]])[:3 - len(medium)]
        niche = []
        for w in words[:2]:
            base = w.rstrip("s")
            niche += [base + "lover", base + "gift", base + "shop"]
        if italian:
            niche += ["madeinitaly", "negozionline", "piccoleimprese"]
        small = [x for x in clean(niche) if x not in big + medium][:4]
        brand = "#<yourshopname>"
        return (f"Hashtags for {topic or 'your posts'} — mix three sizes, 8–10 on Instagram, 3–5 on TikTok, always your own brand tag:\n"
                f"• broad (millions of posts, reach): " + " ".join("#" + x for x in big) + "\n"
                f"• medium (10k–500k, where you can actually rank): " + " ".join("#" + x for x in medium) + "\n"
                f"• niche/buyer intent (your people): " + " ".join("#" + x for x in small) + f" {brand}\n"
                "Rules: put them in the caption (not the first comment), never the same block on every post, no banned/junk tags (#followforfollow #like4like), "
                "check each tag once — if the top posts are nothing like yours, drop it. Every 2 weeks look at which posts reached non-followers (Insights → Reach) and keep the tags from those.")

    def video_ideas(self, t, n=None):
        """'write 3 tiktok video ideas for the cork phone case' → hooks + shots + text on screen + caption, from the product facts."""
        n = {"three": 3, "tre": 3, "four": 4, "five": 5, "cinque": 5, "six": 6, "a few": 3, "some": 3, "un paio di": 2, "qualche": 3}.get((n or "").lower(), None) or (int(n) if n and n.isdigit() else 3)
        n = max(1, min(n, 6))
        product = self.store.find_product(t) if self.store is not None else None
        m = re.search(r"\b(?:for|about|per|su|di)\s+(?:my |our |the |a |an |il |la |le |i )?(?P<x>[a-zà-ú][a-zà-ú0-9 \-']{2,50}?)(?:\s*[?.!,]|$)", t, re.I)
        what = product["name"] if product else ((m.group("x").strip() if m else "the product"))
        facts = (product.get("details") or [])[:4] if product else []
        material = next((f for f in facts if re.search(r"\b(material|made|cork|bamboo|stoneware|cotton|wood|beech|aluminium|glaze|organic)\b", f, re.I)), None)
        detail = next((f for f in facts if f != material), None) or "one concrete detail people don't expect"
        platform = "TikTok" if re.search(r"tiktok", t, re.I) else "Reels" if re.search(r"reel|instagram", t, re.I) else "short video"
        short = what.split(" (")[0]
        ideas = [
            ("The 3-second swap", f"Hook (text on screen, 0–2 s): “Still using the usual one?” — cut to {short} in hand.",
             f"Shots: the ordinary version → yours, extreme close-up of the surface{' (' + material.split(':')[-1].split(';')[0].strip().lower()[:50] + ')' if material else ''}, one real use (15–20 s total).",
             f"Caption: “Small change, every day. {detail[:70]}” + 4 tags."),
            ("What arrives at your door", f"Hook: hands opening the parcel, no talking, natural sound (paper, no plastic).",
             f"Shots: label → box → {short} lifted out → one detail shot; end frame: price and the shipping line from your shipping page.",
             "Caption: “Unboxing, honestly filmed. Ships in 1 business day.” — the calm ASMR kind performs well without ads."),
            ("3 things you didn't know", f"Hook: “3 things about {short} nobody tells you” — count on screen 1-2-3.",
             f"Shots: one 4-second clip per fact — use your real product facts (e.g. {facts[0][:60] if facts else 'where it is made'}; {facts[1][:60] if len(facts) > 1 else 'how long it lasts'}).",
             "Caption: the same 3 facts as bullets; ask “which one surprised you?” to get comments."),
            ("Packing your order", f"Hook: “Packing order #{'51042' if product else '12'} — going to <city>”.",
             "Shots: pick, wrap, seal, label, drop at the courier; 12–18 s, upbeat but not salesy. People trust shops they see working.",
             "Caption: “Every order is packed by hand in <city>. Yours next?”"),
            ("The honest answer", f"Hook: read a real customer question out loud (“Does it survive the dishwasher?” / “Is it really plastic-free?”).",
             f"Shots: you answering in one take + the proof shot ({detail[:60]}).",
             "Caption: the question + the short answer; pin the video as an FAQ."),
            ("Before / after", f"Hook: split screen — the messy/ugly/wasteful before, {short} after.",
             "Shots: 2 s before, 2 s after, 8 s of the result in daily life; add the trending sound quietly under it.",
             "Caption: one line on why you chose this product for the shop."),
        ]
        out = [f"{n} {platform} ideas for {what} — each is 15–25 s, hook in the first 2 seconds, film vertical in daylight:"]
        for i, (title, hook, shots, cap) in enumerate(ideas[:n], 1):
            out.append(f"{i}. {title}\n   {hook}\n   {shots}\n   {cap}")
        out.append("Post 3–4 a week for a month before judging; keep the ones with the best watch time (Analytics → average watch time), not the most likes. Say “write the caption for idea 2” and I'll draft it within the platform's limits for your approval.")
        return "\n".join(out)

    def pricing(self, text):
        m = self.COST.search(text)
        if not m:
            return None
        cost = _num(m.group(1))
        if cost <= 0:
            return None
        ship = 0.0
        ms = re.search(r"(?:shipping|delivery|postage|spedizione)\D{0,20}" + _MONEY, text, re.I)
        if ms:
            ship = _num(ms.group(1))
        landed = cost + ship
        rows = []
        for mult, label in ((2.5, "safe minimum for handmade / dropshipping"), (3.0, "typical"), (4.0, "premium / strong brand")):
            price = round(landed * mult + 0.49, 0) - 0.10          # X,90 style
            fee = price * 0.029 + 0.30
            profit = price - landed - fee
            rows.append(f"• {label}: sell at {_eur(price)} → after the ~2.9 % + € 0,30 payment fee you keep {_eur(profit)} per sale ({profit / price * 100:.0f} % margin)")
        item = re.search(r"\bfor (?:a |an |the )?([a-z][a-z \-]{2,40}?)(?: that| which| costing| cost| at| for|\?|$)", text, re.I)
        name = item.group(1).strip() if item else "it"
        return (f"Pricing {name} at a cost of {_eur(cost)}" + (f" + {_eur(ship)} shipping" if ship else "") + f" ({_eur(landed)} landed):\n" + "\n".join(rows) +
                "\n\nRule of thumb: 2.5–4× the landed cost; below 2× you can't absorb ads, returns and a discount. If competitors sell far below "
                f"{_eur(landed * 2.5)}, the product is the problem, not the price. Want me to check what others charge? Say “compare prices for {name}”.")

    def shipping_ok(self, amount, text):
        low = text.lower()
        it = re.search(r"\b(italy|italia|it)\b", low)
        eu = re.search(r"\b(eu|europe|germany|france|spain|europa|germania|francia|spagna)\b", low)
        if it or not eu:
            verdict = ("that's in the normal range — Italian shops typically charge € 3,90–6,90 for a parcel and go free above € 39–49." if 3 <= amount <= 7
                       else "that's cheap — most Italian shops charge € 3,90–6,90 (you may be subsidising it)." if amount < 3
                       else "that's on the high side — Italian shoppers expect € 3,90–6,90, or free above a threshold (€ 39–49 is common).")
        else:
            verdict = ("that's normal for EU delivery — € 6,90–9,90 is typical for a small parcel to Germany/France/Spain." if 5 <= amount <= 10
                       else "that's cheap for EU delivery — small parcels usually cost the shop € 6–9." if amount < 5
                       else "that's high for the EU — shoppers expect € 6,90–9,90 or free above ~€ 60.")
        return (f"{_eur(amount)} shipping: {verdict}\nWhat matters more than the number: show it before checkout, and offer a free-shipping threshold "
                "a bit above your average order — it lifts the basket size.")

    def start_plan(self, text):
        m = re.search(r"\b(?:sell|selling|vendere)\s+(?:my |our )?([a-z][a-z \-]{2,50}?)(?:\s+online|\s+on\b|\s*[,.?!]|$)", text, re.I)
        what = (m.group(1).strip() if m else "products")
        if what in ("products", "things", "stuff", "online"):
            what = "products"
        todo = [f"Pick 3–5 {what} to start with (not 30) and write one honest sentence per product" if what != "products" else "Pick one niche and 3–5 products to start with (not 30) — say “research product ideas for <niche>”",
                f"Find out what similar {what} sell for — say “compare prices for {what}”",
                f"Work out your prices: cost + shipping × 2.5–4 — say “how much should I charge for {what} that costs me …”",
                "Take clear photos on a plain background (phone is fine, daylight, 3 angles)",
                "Choose where to sell: your own shop (Shopify/WooCommerce/Etsy for handmade) — I can build the website",
                "Write the shipping + returns rules once (EU: 14-day withdrawal, 2-year guarantee) — I draft them",
                "Open the social pages and rehearse a first post with me before going live"]
        head = f"Starting to sell {what} online" if what != "products" else "Starting an online shop"
        return {"todo": todo, "text": f"{head} — here's the order I'd do it in, and I've put it on our to-do list:\n" +
                "\n".join(f"{i + 1}. {s}" for i, s in enumerate(todo)) + "\n\nTell me which step you want me to do first."}

    # ---- helpers -------------------------------------------------------------------------------
    def _customer_text(self, text, m):
        """Pull the customer's words out of 'a customer says the parcel arrived broken, what do I answer?'."""
        inner = m.group("inner").strip(" :,-–—\"“”'")
        quoted = re.search(r"[\"“«](.{8,400}?)[\"”»]", text)
        if quoted:
            return quoted.group(1).strip()
        inner = re.sub(r"^(that|me|us)\s+", "", inner, flags=re.I)
        return inner or text
