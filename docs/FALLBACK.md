# Fallback contact (when Telegram fails)

Two spare lines between you and the bot. Both are optional, both are off until you set them up.

## 1. Gmail two-way (talk to the bot by email)

The bot reads its **own mailbox** every 5 minutes. Mail **from your addresses**
is run through the normal brain and answered by email. Approvals (money, posts,
customers) still need your tap on Telegram — the email tells you when one is waiting.

Setup:

1. In Telegram: `/fallback allow you@gmail.com` (repeat for each address you own).
2. In Telegram: `/fallback test send` — you get a test mail within a minute.
3. Reply to that mail with something like `status` — the answer comes back by email.

Rules: strangers are silently ignored, the bot's own sent mail is never answered
(no loops), each mail is answered once even after restarts, quoted history is stripped.

You can also put `OWNER_EMAILS=you@gmail.com,other@home.com` in `.secrets/env`.

## 2. Backup Telegram bot (spare phone line)

1. Message `@BotFather` on Telegram: `/newbot`, pick a name, copy the token.
2. Add to `.secrets/env`: `FALLBACK_BOT_TOKEN=123456:ABCDEF...`, then restart the bot.
3. Open the new bot and say `status`.

The backup bot sends critical alerts (e.g. "main Telegram line down") and answers
`/status` plus quick questions — text only, never buttons. Everything else lives
on the main bot.

## How the watchdog works

If the main Telegram line fails to authenticate 5 times in a row, the bot emails you
("main Telegram line down — reply to this mail") and pings the backup bot, once per
outage. When the line recovers, you get one "Telegram is back" mail.

Commands: `/fallback` (state) · `/fallback allow <email>` · `/fallback forget <email>` ·
`/fallback test` (check mail now) · `/fallback test send`.

Offline proof: `python3 engine/scripts/score_fallback.py` (14/14).
