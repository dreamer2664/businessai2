# My own accounts (sign-ups)

I keep one identity of my own (`BAI_ACCOUNT_EMAIL` / `BAI_ACCOUNT_PASSWORD` in
`.secrets/env`) and sign up on sites when a task needs it — marketplaces to read
reviews, tools, forums. Every account is remembered (`state/accounts.json`).

## The safety rule (item 6)

- **Fakes first**: my rehearsal stages and test sites (localhost) never need
  permission — that is where I practice.
- **Real sites need your approval**: the first time I want to sign up somewhere
  new, I ask — *Allow once*, *Always allow*, or *Never*. No answer, no sign-up.
- **Never list** (no asking, always refused): money (PayPal, banks, Revolut,
  crypto), Apple/Google/Microsoft logins, the big social sign-up pages.
- Your own accounts, money moves and customer messages stay owner-in-the-loop,
  always.

Commands: `/accounts` (list) · `/accounts allow <site>` ·
`/accounts forget <site>`.

## Training

`python3 engine/scripts/score_accounts.py --drill 4` runs 4 fresh practice
sign-ups against throwaway fake sites (alternating plain / CAPTCHA) and reports
the pass rate + median time. Train any time; it touches nothing real.

## Gmail half

Verification codes and confirmation links come through my own Gmail
(`agent/google.py`): server-side `from:` search, replies land in the same
thread, and mail I have answered is marked read + archived so the inbox stays
clean.

Offline proof: `python3 engine/scripts/score_accounts.py` (18/18 on a machine
with a browser) · `python3 engine/scripts/score_gmail.py` (8/8).
