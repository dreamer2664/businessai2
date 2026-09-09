# Install the Business AI on a Windows PC (free, ~10 minutes)

The agent runs inside **WSL** (Windows Subsystem for Linux) — a small Linux
that Windows 10/11 ships for free. It uses about 100 MB of RAM at this stage.
The bot answers whenever the PC is on and connected.

## 1. Turn on WSL (once)
Open **PowerShell as Administrator** (right-click Start → "Terminal (Admin)" or
"Windows PowerShell (Admin)") and run:
```powershell
wsl --install -d Ubuntu
```
Reboot when asked. A window "Ubuntu" opens and asks for a username and a
password (anything you like — you'll need the password for `sudo`).
If it doesn't open by itself: Start menu → "Ubuntu".

## 2. Get the code (inside the Ubuntu window)
```sh
sudo apt update && sudo apt install -y git python3
git clone https://github.com/dreamer2664/businessai2
cd businessai
sh scripts/install.sh
```
`install.sh` creates `.secrets/env`. Open it with `nano .secrets/env` and fill in:
```
TELEGRAM_BOT_TOKEN=<the bot token from @BotFather>
TELEGRAM_OWNER_USERNAME=<your Telegram username, without @>
```
Save with Ctrl-O, Enter, then Ctrl-X. (The GitHub lines are optional on the PC.)

## 3. Start it
Try it once in the foreground:
```sh
sh scripts/run.sh
```
Send `/status` to the bot on your phone — it should answer within seconds.
Stop it with Ctrl-C, then install it as a service so it starts by itself:
```sh
sh scripts/service.sh
```
From now on it runs whenever Ubuntu is running. Check / control it with:
```sh
systemctl --user status businessai     # is it running?
journalctl --user -u businessai -f     # live log (Ctrl-C to leave)
systemctl --user restart businessai    # restart after an update
```

## 4. Keep it running when the PC is on (the #1 cause of "the bot doesn't answer")
Windows switches the whole Linux VM **off 60 seconds after the last `wsl` window closes** — the bot's own service and
its auto-restart can do nothing about that, because the computer it runs on is gone. Symptom: the bot answers only
while someone has a terminal open, and `wsl -l -v` shows `Ubuntu Stopped`. The journal shows `Stopping businessai.service`
right after each command window closes and a `-- Boot --` line when the next command wakes Linux up.

Proven fix (2026-09-09, WSL 2.7): two settings + a keeper task. Paste this whole block into **PowerShell** once:
```powershell
@"
[wsl2]
vmIdleTimeout=-1
"@ | Set-Content "$env:USERPROFILE\.wslconfig" -Encoding ASCII
wsl --shutdown
$a = New-ScheduledTaskAction -Execute "C:\Windows\System32\wsl.exe" -Argument '-d Ubuntu -u dreamer2664 -- bash -c "while true; do sleep 300; done"'
$t = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$s = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "BusinessAI-WSL" -Action $a -Trigger $t -Settings $s -Force | Out-Null
Start-ScheduledTask -TaskName "BusinessAI-WSL"
```
(replace `dreamer2664` with your Ubuntu user name if different.) `vmIdleTimeout=-1` = never stop Linux for being idle;
the task opens Linux at every Windows logon and holds it open. Linger for the user must be on (`loginctl enable-linger`,
`service.sh` does it) so the service survives without a login session.

Check (all three must hold): `Get-ScheduledTask BusinessAI-WSL` → **Running** (Ready = the keeper died);
`wsl -l -v` → **Running**; `wsl bash -lc "systemctl --user is-active businessai"` → **active**.
Real proof: close every terminal, wait 10 minutes, send `hello` on Telegram.
Note: a PowerShell wrapper around wsl.exe (`powershell -WindowStyle Hidden -Command "wsl … sleep infinity"`) did NOT
survive — the task went back to Ready within seconds. Run wsl.exe directly.

Also, in Windows **Settings → System → Power**, set "sleep" to Never while plugged in, otherwise the bot naps with the PC.

## 5. Updating
```sh
cd ~/businessai && git pull && sh scripts/install_desktop.sh && sh scripts/service.sh
```
(`install_desktop.sh` adds the screen tools — tesseract, Xvfb, xdotool, scrot — once; harmless to repeat.)
Then, once, in Telegram: `/eyes install` (downloads the 310 MB vision model). Check with `/status` — it should say
`Business AI 1.1 …` and `/eyes` should list the vision model and the screen tools as present.

## 6. Letting it work a page for you (`/do`)
- `/do https://en.wikipedia.org/wiki/Etsy | in which year was Etsy founded?` — its own browser, exact and fast.
- `/do desktop <goal>` — its own virtual screen (on WSL it draws one itself); whatever window is open there.
- `/do <url1> <url2> <url3> | which supplier is cheapest per pack?` — several pages compared (cheapest / fastest / lowest … ranked for you).
- `/do <url> | fill in the contact form: name = …, email = …, message = …` — it types everything in and stops; you press Send.
It reports each result with a short "What I did" list. When it wants to press a button that spends money, publishes, signs in or
deletes, your phone gets a question with **Yes, click it / No** — nothing happens until you tap.

## 7. Your real customer messages (e-mail, Facebook, Instagram)
Once you want it to handle real messages, follow [CHANNELS.md](CHANNELS.md): a few lines in `.secrets/env` (mailbox address,
an app password, the mail servers — there is a table for Gmail, Outlook, Aruba, Libero…), restart, then `/channels check`.
From then on every customer mail arrives on your phone with a drafted answer and **Approve & send / Edit / Reject**.

## Troubleshooting
- `python3 -m agent.selfcheck` (in the businessai folder) tells you whether the
  token and owner name are right.
- Bot answers "Sorry, I only work for my owner": the username in `.secrets/env`
  doesn't match your Telegram username exactly (Telegram → Settings → Username).
- Log lines with `409 Conflict`: two copies are running (e.g. sandbox + PC).
  Only one can poll Telegram at a time — stop the other one.

## Seeing the AI work (milestone 2+)
* **Live page:** while the service runs, open http://localhost:8765 in your normal Windows browser (WSL ports are shared).
* **Real window:** Windows 11 WSL has a display (WSLg) built in, so the agent's Chrome opens as a normal window automatically.
  On Windows 10 (no WSLg) it stays invisible — use the live page or `/screen` instead. Force invisible with `BAI_HEADED=0`.
  The window needs the full Chromium once: `python3 -m playwright install chromium` (install_browser.sh does it).
* **Phone:** `/screen` for one screenshot, `/watch on` for a photo after every step.

## Thinking model (milestone 3)
`sh scripts/get_model.sh` downloads llama.cpp and a 940 MB open model once. Needs ~1.3 GB free RAM while the agent is
thinking (it frees it after 10 idle minutes). Bigger/better models: set `BAI_MODEL_URL` to any GGUF file before running the
script (e.g. Qwen2.5-3B-Instruct-Q4_K_M ≈ 2 GB, needs ~3 GB RAM). Use `BAI_LLM_THREADS` to limit CPU threads.
