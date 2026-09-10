#!/bin/sh
# Set the bot's identity mailbox (plain IMAP, read-only) in .secrets/env — never in git.
#   sh scripts/set_mail.sh <address> <base64 of the IMAP/app password> [imap host]
# The password is passed base64-encoded so it survives PowerShell / wsl quoting. Then: systemctl --user restart businessai
set -e
cd "$(dirname "$0")/.."
ADDR="$1"; B64="$2"; HOST="$3"
[ -n "$ADDR" ] && [ -n "$B64" ] || { echo "usage: sh scripts/set_mail.sh <address> <base64-password> [imap-host]"; exit 1; }
PW=$(printf '%s' "$B64" | base64 -d 2>/dev/null | tr -d '\r\n ') || { echo "bad base64"; exit 1; }   # spaces dropped: Gmail app passwords are shown in groups of 4
mkdir -p .secrets; touch .secrets/env; cp .secrets/env ".secrets/env.bak.$(date +%Y%m%d-%H%M%S)"
setk() { V=$(printf '%s' "$2" | sed "s/'/'\\\\''/g"); if grep -q "^$1=" .secrets/env; then sed -i "s|^$1=.*|$1='$V'|" .secrets/env; else echo "$1='$V'" >> .secrets/env; fi; }
setk BAI_ACCOUNT_EMAIL "$ADDR"
setk BAI_MAIL_PASSWORD "$PW"
[ -n "$HOST" ] && setk BAI_MAIL_IMAP_HOST "$HOST"
chmod 600 .secrets/env
echo "identity mailbox set: $ADDR (password length ${#PW})"
set -a; . ./.secrets/env; set +a
python3 -m agent.selfcheck 2>/dev/null | grep -i "identity mailbox" || true
if systemctl --user is-active businessai >/dev/null 2>&1; then systemctl --user restart businessai && echo "bot restarted"; fi
