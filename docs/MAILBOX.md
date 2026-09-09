# Gmail as a tool (owner's item G)

The app's own mailbox (busynessai001@gmail.com) is where sign-up codes, platform notices and the odd real
person land. `agent/mailbox.py` keeps it sorted and uses it — official Gmail API, scope `gmail.modify`
(already granted), **nothing is ever deleted or sent from here**: labels, archive (remove INBOX) and mark-read only.

## The four piles (labels created once, visible in the Gmail sidebar)

| label | what lands there | what happens |
|---|---|---|
| **Verification** | codes, confirm links, password resets, welcome mails from sign-ups | kept unread until used; archived after 1 day |
| **Leads** | real people writing to us — suppliers answering a quote, customers, partners | stays in the inbox, unread; you get one line ("📩 New lead … tell me what to reply and I draft it for your approval"). I never answer a lead myself. |
| **Alerts** | order / shipping / payment / security / policy notices from platforms | marked read; archived after 3 days |
| **Newsletters** | list mail (List-Unsubscribe), promos, digests | marked read and archived at once |

Your own addresses (the fallback allow-list) and the bot's own sent mail are never touched — the fallback
channel answers you. Classification is pure rules (sender, headers, subject/snippet words, EN + IT), testable offline.

## How it runs
- **Every 15 min** when idle (`Mailbox.due()` in the idle loop): one light listing (`format=metadata`, no bodies),
  label what is new, archive what is old enough. Idempotent: a mail already sorted is not touched again.
- **Codes** — "check my email for the vinted code" and the sign-up skill (`accounts.enter_code`) now look in the
  *Verification* pile first (one cheap query), then fall back to the general search; the used mail is marked read.
- **Owner words** — `/mail` (summary of the day: leads waiting, counts, rules) · `tidy the inbox` (now, one report line)
  · `any leads?` (last 7 days) · `/mail labels`. `/status` has a `mail:` line.
- A label deleted by hand in Gmail → the ids are refreshed once and the tidy goes on (no permanent 400s).
- Google off → silent no-op; API errors → logged, returned in `tidy()["error"]`, never raised.

Proof: `python3 engine/scripts/score_mailbox.py` → 43/43 offline (rules on 8 sample mails, label helpers, the tidy and
its archive-by-age, idempotence, persistence, code fast path + fallback, owner commands, stale ids, broken API, the agent
end-to-end); `--live` creates the labels in the real mailbox and runs one tidy (2026-09-09: 3 Google notices → Alerts,
owner/bot mail untouched).

Still open under G: sign-up training on the local fake sites (accounts 18/18 already covers the flow with a fake mailbox);
real sign-ups stay owner-approved (`/accounts allow <site>`).
