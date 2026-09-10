# Marketplace handbook — how the sites work for a buyer (and for me), 2026-09

Dense, verified-by-visiting notes. One section per site: what it is, how to search, what a listing shows, what a good seller
looks like, the walls I meet, the traps. Written for the brain pack (each paragraph is a passage) and for me before I open a site.

## Vinted (vinted.it) — second-hand from private people, buyer protection built in
Vinted Buyer Protection (help/262, help/550): it is charged on every purchase paid through Vinted and covers the buyer if the
item never arrives, arrives damaged, or is significantly not as described; the buyer must report the problem in the app within
2 days of delivery, then the money is held and a refund (including shipping) is issued when the claim is upheld; the fee is
€0.70 plus 5 % of the item price; paying or arranging delivery outside Vinted voids the protection.
Vinted is a peer-to-peer marketplace for used clothes, shoes, accessories, and since 2023 also electronics, books, toys, home
items and video games. Sellers are private people; there are no shop returns, only the platform's Buyer Protection. Every
purchase adds a Buyer Protection fee (about 5 % + €0.70) shown as the "total" next to the price; the listed price is what the
seller gets. Shipping is paid by the buyer and chosen at checkout (InPost lockers, Poste, BRT, UPS, DHL points, home delivery);
the seller prints a prepaid label — sellers never set a shipping price on Vinted.
Vinted search: https://www.vinted.it/catalog?search_text=WORDS with order=newest_first | price_low_to_high | relevance, and
price_to=N&currency=EUR to cap the price. The catalog page loads its own JSON (api/v2/catalog/items) which gives per item: title,
price, total with protection, condition (new with tags / new without tags / very good / good / satisfactory), brand, size, seller
login, seller id, favourite count, view count, photo thumbnails. The item page (/items/ID-slug) shows condition, brand, upload
date, description, shipping "from €X", and the seller's feedback count, rating, location, item count, last active, verifications.
Vinted seller signals: feedback count and % positive (the platform shows both), "verified" badges (e-mail, phone, Google/Facebook),
last-active date, number of items for sale, location. A seller with 0 feedback is not a scam by default — most people start there —
but a 0-feedback seller with a high-value item at a low price is the classic risk. Vinted Pro accounts are businesses (VAT number,
legal right of withdrawal applies).
Vinted traps for a buyer: prices of €1–3 are "make me an offer" placeholders; "bundle" listings hide the per-item price; titles
copy the console/phone name for games, cases and cables; "reserved" items are still visible; some sellers ask to pay outside the
app (never — that is the only way to lose Buyer Protection). Vinted rules: the buyer has 2 days after delivery to report "not as
described" or the money is released to the seller; disputes are handled in-app with photos.
What I meet on Vinted: a "Dove vivi?" country modal on the first visit (choose Italia), a cookie banner (reject), otherwise no
login wall for browsing and search. Offers and messages need an account. Vinted rate-limits fast repeated API calls (a 429 →
back off). The search API respects the same cookies as the page.

## Subito (subito.it) — Italy's classifieds, mostly local pick-up, TuttoSubito for shipping
The Postepay scam on Subito: a "buyer" or "seller" asks for a ricarica Postepay (a top-up to a prepaid card) or a bank transfer
before anything ships, often with a story of urgency or a fake courier; a variant sends a fake "Subito Pay" / "TuttoSubito"
link or QR code that actually takes money. Subito itself never asks to pay outside TuttoSubito; a request to pay in advance
by Postepay, bonifico, gift cards or a link is the scam signal — stop and report the ad.
Subito is Italy's biggest classifieds site (Adevinta): private and business sellers, every category from cars to phones.
Traditionally hand-to-hand and cash; "TuttoSubito" is the shipped-with-protection option: the seller ships with a prepaid label
(Poste/InPost/BRT), the buyer pays in-app and the money is released after delivery; only listings marked "spedizione disponibile"
can be bought that way. Everything else is contact-the-seller (phone/message) and pay in person.
Subito search: https://www.subito.it/annunci-italia/vendita/usato/?q=WORDS with order=priceasc for cheapest first and o=N for
page N; a region or city can be part of the path (annunci-puglia, annunci-lombardia) or the q can carry a town. The result page
embeds __NEXT_DATA__ with the full ad list: subject, price, urls, geo (town, city, region), features (item condition, shippable,
shipping cost), advertiser name + company flag, date, images (cdn base url + ?rule=vertical-mini-card-1x-auto for a thumbnail).
Subito seller signals: private vs company ("azienda"), how long the ad has been up, whether shipping is enabled (a seller who
accepts TuttoSubito accepts platform protection), the town. Subito shows no ratings for private sellers; a phone number and a
willingness to use TuttoSubito are the practical trust signals.
Subito traps: "spedizione disponibile" without TuttoSubito means the seller ships privately — no protection; requests to pay by
ricarica Postepay, bank transfer before shipping, or through fake "Subito Pay" links are the known scams; prices of €1 mean
"contattami"; the same photo in many towns is a scam ring. Cars, houses and jobs are separate sections with their own rules.
What I meet on Subito: a Didomi cookie popup ("Continua senza accettare" is the right button), otherwise no wall for browsing;
messaging and TuttoSubito need an account (SPID/e-mail); the help centre (assistenza.subito.it) blocks plain HTTP but opens in
the browser.

## Wallapop (wallapop.com) — Spanish classifieds, Italy since 2021, strong on local
Wallapop is a Spanish peer-to-peer app (also web) for used goods, big in Spain, present in Italy and Portugal. Two ways to buy:
in person (default; the app shows distance from you) or "Envíos / Spedizioni Wallapop" with buyer protection (the seller ships
with a label, the buyer confirms on receipt). Sellers have public ratings (stars) and review counts; Wallapop Pro are businesses.
Wallapop search: https://it.wallapop.com/app/search?keywords=WORDS with order_by=price_low_to_high | newest; latitude/longitude
and distance parameters filter by location (the app is location-first). The web app is a single-page app: search results come from
api.wallapop.com/api/v3/general/search — that API and the site refuse datacenter addresses with a CloudFront 403 ("The request
could not be satisfied"); from a home connection it works.
Wallapop traps: prices with "cambio" (swap) or "regalo"; sellers who push WhatsApp and a bank transfer; "spedizione" only when the
Wallapop shipping option is on the listing itself. Wallapop shows seller response time and "last connection" — good signals.

## Temu (temu.com) — new goods shipped from China, aggressive prices, login-first
Temu (PDD Holdings, 2022) sells new goods from Chinese factories and traders directly to consumers: home, gadgets, clothing,
tools, toys. Prices are low because goods ship as small parcels from China with subsidised shipping; delivery to Italy takes
about 5–15 days (sometimes up to 3 weeks), tracked; orders are often split. Payment on the site; buyer protection: full refund
if the item does not arrive, arrives damaged or is not as described, usually without returning cheap items; return window 90
days for most items; the first return per order is free.
Temu walls: the site shows almost nothing to a visitor without an account — search, category and even policy pages redirect
to /login.html ("Accedi / Registrati"). After typing an e-mail the site shows a picture puzzle ("Verifica di sicurezza — clicca su
tutti gli oggetti duplicati") in an iframe (bgn_verification.html) before the password/code step. With an account and a
logged-in session, search is https://www.temu.com/it/search_result.html?search_key=WORDS; product pages are /it/…-g-ID.html.
Temu traps and judgment: sizes run small (Asian sizing) — check the size table; the "€0.99 / gratis" items are hooks that need a
minimum order; countdown timers and "quasi esaurito" are permanent; reviews are real but concentrated on cheap items; brand
names are often generic ("compatible with"); electronics carry no Italian warranty service in practice (refund, not repair).
Customs: parcels under €150 pay VAT at checkout (IOSS) — no surprise fees; above €150 duties may apply.

## Shein (shein.com) — fast fashion from China, own brand plus marketplace sellers
Shein return policy (it.shein.com/Return-Policy-a-281.html): the return window is 30 days from the delivery date; the first return
on each order is free (a prepaid label), further returns from the same order cost a fee taken from the refund; underwear,
swimwear bottoms, bodysuits, jewellery, cosmetics and customised items cannot be returned; the refund goes to the Shein wallet
or the original payment method. Shein shipping (Shipping-Info-a-280.html): standard shipping is free above a small basket
(€19 in Italy in 2026), otherwise a flat fee; standard delivery 7–14 days, express 5–9 days; orders are tracked; "Magazzino
UE" items ship from the EU warehouse in a few days with no customs.
Shein sells its own-brand clothing plus, since 2023, third-party sellers in a marketplace section. Prices are low, delivery to
Italy 7–14 days (express faster), free shipping over a threshold, a 30-day return window (first return per order free, others
with a fee), refunds to card or Shein wallet. Sizes: use the size chart per item and the reviews' photos; quality varies by
seller. Italian site it.shein.com prices in EUR with tax included.
Shein walls: it.shein.com serves search pages (/pdsearch/WORDS/) and category pages to visitors, but a headless/datacenter
browser gets /risk/challenge?captcha_type=909 — a picture-grid puzzle ("Seleziona tutte le immagini corrispondenti") inside a
modal; repeated attempts lead to /risk/action/limit (a time-out on the address). Entering through the home page first and
keeping the session helps; a home connection is challenged far less. Help pages (Return-Policy-a-281.html etc.) are static and
readable.
Shein judgment: "new with tags" second-hand Shein on Vinted is often cheaper than Shein itself after shipping; Shein's own
reviews with photos are the size/quality signal; the "marketplace" label on a listing means a third-party seller with its own
shipping time.

## AliExpress (aliexpress.com) — the original China marketplace; Choice = faster, bundled shipping
AliExpress Choice is AliExpress's own fulfilment programme: Choice items are shipped together from consolidated warehouses,
with free shipping above a small minimum (about €10), delivery to Italy in 5–10 days, free returns within 15 days and a
delivery-time guarantee with a coupon if late — the closest AliExpress gets to Temu's model.
AliExpress (Alibaba) is a marketplace of Chinese sellers; buyer protection (refund if not received or not as described) with
disputes; delivery to Italy 10–30 days standard, "Choice" items 5–10 days with free shipping over a small minimum and free
returns; prices in EUR with VAT at checkout under €150. Search: https://it.aliexpress.com/w/wholesale-WORDS.html (works for
visitors from Italy; sort by price is a parameter). Seller signals: store age, positive feedback %, followers, "Choice" badge,
number of orders on the item, review photos. Traps: the headline price is often the cheapest variant (a cable, not the device);
"€1.99" first-order deals; sizes; brand names that are close copies (counterfeits are removed but reappear).

## DHgate (dhgate.com) — wholesale-style China marketplace, small MOQs, known for replicas
DHgate is a Chinese B2B/B2C marketplace: sellers list with tiered prices by quantity (1 piece is usually allowed), shipping 10–25
days, buyer protection with escrow (money released after confirmation). It is notorious for branded replicas ("reps") — those
are counterfeit; the project rule is never to source or list them. Search: https://www.dhgate.com/wholesale/search.do?searchkey=WORDS.
Walls: Cloudflare "Just a moment…" for a few seconds (it clears by itself on a normal browser), then the page loads; prices show
in the cookie currency (set currency=EUR).

## Banggood (banggood.com) — China gadgets/RC/tools shop, EU warehouses
Banggood ships from the China warehouse (10–25 days) or from its EU warehouses in Czechia, Spain and Poland (3–8 days, no
customs, prices already VAT-inclusive); the warehouse is shown on the product page ("Ship from: CZ / ES / CN") and can be a
search filter; Banggood is a retailer with its own returns (7 days for most items, 30 for defective ones).
Banggood is a Chinese retailer (not a marketplace): electronics, RC, tools, home; ships from China or EU warehouses (faster,
no customs); prices in the cookie currency (currency=EUR); reviews with photos; 7-day return for most items. Search:
https://www.banggood.com/search/WORDS.html. No wall for visitors; a cookie banner.

## Facebook Marketplace — local, needs a Facebook login; never automated here
Facebook Marketplace is inside Facebook: listings are local (radius from a city), contact is via Messenger, no payment or
protection in Italy (cash on pick-up). It needs a logged-in Facebook account; automating Facebook is against its terms and the
project rule — the owner opens it on the phone with the city filter (e.g. Barletta) when a local deal matters.

## Judging a second-hand deal (what "best" means)
The best deal is the cheapest listing that is really the item: same model (a model number in the name must be in the title —
iPhone 13 is not iPhone 12; Air Max 90 is not 97), a working unit (not "per ricambi", "non funziona", "schermo rotto"), not an
accessory or a game titled with the device name, not a placeholder price (€1–3, €99/999 patterns), and a plausible price (a
working Xbox Series X is never €30 second-hand; below a family's floor price it is a part or a scam). Then the seller: feedback
count and percentage, account age, verified contacts, location, willingness to use the platform's protected shipping. Then the
total: price + protection fee + shipping, compared across sites. Details like storage, colour or size narrow, they do not
disqualify. A typical price is the median of the clean matches; a listing far below it needs a look at the photos before anyone pays.

## Being a good visitor (how I browse marketplaces from the owner's home address)
The owner's home IP is shared with their own browsing and every sign-up they will ever make. Reputation networks (Cloudflare,
Arkose, hCaptcha) share signals across sites: a burst of visits to many shops in a minute from a residential address earns a
"verify you are human" loop everywhere for a day. Rules: 12 seconds between hits on one host, one browser session kept (cookies
saved), never repeat a probe of all sites within 6 hours, back off exponentially after any wall, never retry a CAPTCHA blindly,
enter shops through the home page like a person, Italian locale and language headers, and stop a site for the day after 5
failed security checks. A closed cookie banner and a kept session make the next visit look like the same person coming back.
