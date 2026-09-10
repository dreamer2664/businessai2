"""Identity mailbox over plain IMAP (agent/idmail.py) — offline, against a tiny fake IMAP server.
Run: python3 engine/scripts/score_idmail.py"""
import os, sys, re, ssl, socket, threading, time, tempfile, email.utils
sys.path.insert(0, ".")

ok = tot = 0
def check(name, cond, got=""):
    global ok, tot
    tot += 1; ok += bool(cond); print(("✅" if cond else "❌"), name, "" if cond else f"→ {str(got)[:200]}")

# ---- a fake IMAP server: LOGIN (one good password), SELECT, SEARCH, FETCH BODY.PEEK; records every command ------------
import datetime as _dt
now = email.utils.format_datetime(_dt.datetime.now(_dt.timezone.utc))
old = email.utils.format_datetime(_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=3))
MAILS = {
    1: f"From: Temu <noreply@temu.com>\r\nTo: bot@example.com\r\nSubject: Il tuo codice di verifica Temu\r\nDate: {now}\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nIl tuo codice di verifica è 482913. Scade tra 10 minuti.\r\n",
    2: f"From: Shein <no-reply@shein.com>\r\nTo: carlo@example.com\r\nSubject: Conferma il tuo account\r\nDate: {now}\r\nContent-Type: text/html; charset=utf-8\r\n\r\n<html><body><p>Benvenuto!</p><a href=\"https://it.shein.com/verify?token=abc123\">Conferma</a> <a href=\"https://shein.com/unsubscribe\">x</a></body></html>\r\n",
    3: f"From: Vinted <no-reply@vinted.it>\r\nTo: bot@example.com\r\nSubject: Your Vinted code\r\nDate: {old}\r\nContent-Type: text/plain\r\n\r\nYour code is 111222 (this one is 3 hours old)\r\n",
    4: f"From: Mum <mum@example.com>\r\nTo: carlo@example.com\r\nSubject: cena domenica\r\nDate: {now}\r\nContent-Type: text/plain\r\n\r\nVieni alle 12? codice porta 5544\r\n",
}
LOG = []
GOOD_PW = "abcd efgh ijkl mnop".replace(" ", "")

def serve(conn):
    f = conn.makefile("rwb", buffering=0)
    f.write(b"* OK fake IMAP ready\r\n")
    while True:
        line = f.readline()
        if not line:
            break
        line = line.decode("utf-8", "replace").rstrip("\r\n")
        LOG.append(line)
        tag, _, rest = line.partition(" ")
        cmd, _, args = rest.partition(" ")
        cmd = cmd.upper()
        if cmd == "LOGIN":
            m = re.match(r'"?([^"\s]+)"?\s+"?([^"]+)"?', args)
            if m and m.group(2) == GOOD_PW:
                f.write(f"{tag} OK LOGIN completed\r\n".encode())
            else:
                f.write(f"{tag} NO [AUTHENTICATIONFAILED] Application-specific password required\r\n".encode())
        elif cmd == "SELECT" or cmd == "EXAMINE":
            f.write(f"* {len(MAILS)} EXISTS\r\n{tag} OK [READ-ONLY] SELECT completed\r\n".encode())
        elif cmd == "SEARCH":
            ids = list(MAILS)
            m = re.search(r'TO "([^"]+)"', args)
            if m:
                ids = [i for i in ids if m.group(1).lower() in MAILS[i].lower().split("\r\n\r\n")[0]]
            f.write(("* SEARCH " + " ".join(map(str, ids)) + f"\r\n{tag} OK SEARCH completed\r\n").encode())
        elif cmd == "FETCH":
            mid = int(args.split()[0])
            body = MAILS[mid].encode()
            f.write(f"* {mid} FETCH (BODY[] {{{len(body)}}}\r\n".encode() + body + f")\r\n{tag} OK FETCH completed\r\n".encode())
        elif cmd == "LOGOUT":
            f.write(f"* BYE\r\n{tag} OK LOGOUT completed\r\n".encode()); break
        elif cmd == "CAPABILITY":
            f.write(f"* CAPABILITY IMAP4rev1 AUTH=PLAIN\r\n{tag} OK CAPABILITY completed\r\n".encode())
        elif cmd in ("STORE", "EXPUNGE", "COPY", "MOVE", "APPEND"):
            f.write(f"{tag} NO not allowed in this test\r\n".encode())
        else:
            f.write(f"{tag} OK {cmd} completed\r\n".encode())
    conn.close()

# self-signed cert for IMAP4_SSL
d = tempfile.mkdtemp()
os.system(f"openssl req -x509 -newkey rsa:2048 -nodes -keyout {d}/k.pem -out {d}/c.pem -days 2 -subj '/CN=localhost' >/dev/null 2>&1")
ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.load_cert_chain(f"{d}/c.pem", f"{d}/k.pem")
srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); srv.bind(("127.0.0.1", 0)); srv.listen(5)
PORT = srv.getsockname()[1]
def accept_loop():
    while True:
        try:
            c, _ = srv.accept()
            try:
                threading.Thread(target=serve, args=(ctx.wrap_socket(c, server_side=True),), daemon=True).start()
            except Exception:
                pass
        except Exception:
            break
threading.Thread(target=accept_loop, daemon=True).start()

import imaplib
_orig_ssl = imaplib.IMAP4_SSL
class _NoVerify(_orig_ssl):                       # the test cert is self-signed
    def __init__(self, host, port, timeout=None):
        c = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT); c.check_hostname = False; c.verify_mode = ssl.CERT_NONE
        super().__init__(host, port, ssl_context=c, timeout=timeout)
imaplib.IMAP4_SSL = _NoVerify

from agent import idmail as IM
os.environ.update({"BAI_ACCOUNT_EMAIL": "carlo@example.com", "BAI_MAIL_PASSWORD": "abcd efgh ijkl mnop", "BAI_MAIL_IMAP_HOST": "127.0.0.1", "BAI_MAIL_IMAP_PORT": str(PORT)})
os.environ.pop("BAI_MAIL_ALIAS", None)
m = IM.IdMail()
check("configured from env; spaces in the app password are dropped", m.configured() and m.password == GOOD_PW)
good, note = m.check()
check("check(): login ok + message count", good and "4 message" in note, note)
code, mail = m.find_code("temu", tries=1)
check("find_code('temu') → 482913 from the fresh Temu mail", code == "482913" and "temu" in mail["from"].lower(), (code, mail))
code, mail = m.find_code("vinted", tries=1)
check("a 3-hour-old code is ignored (only fresh mail)", code is None, code)
link, mail = m.find_link("shein", tries=1)
check("find_link('shein') → the verify url, not the unsubscribe one", link == "https://it.shein.com/verify?token=abc123", link)
code, mail = m.find_code("", tries=1)
check("without a hint the owner's own mail ('codice porta 5544' from Mum) is never read as a code", code == "482913", code)
check("read-only: only PEEK fetches, no STORE/EXPUNGE/COPY, and a LOGOUT after every lookup", all("BODY.PEEK" in l for l in LOG if " FETCH " in l) and not any(re.search(r" (STORE|EXPUNGE|COPY|MOVE) ", l) for l in LOG) and LOG.count("LOGOUT") == 0 or sum(1 for l in LOG if l.endswith("LOGOUT")) >= 4, [l for l in LOG if "FETCH" in l][:2])
# alias filter
os.environ["BAI_MAIL_ALIAS"] = "bot@example.com"
m2 = IM.IdMail()
check("alias: what sites get is the alias", m2.address() == "bot@example.com")
rec = m2.recent(minutes=60)
check("alias: only mail TO the alias is read (Temu yes, Mum no)", rec and all("bot@example.com" in r["to"] for r in rec) and not any("cena" in r["subject"] for r in rec), [r["subject"] for r in rec])
# wrong password → the Gmail hint
os.environ["BAI_MAIL_PASSWORD"] = "Business001!"; os.environ["BAI_MAIL_IMAP_HOST"] = "127.0.0.1"
m3 = IM.IdMail(); m3.host = "127.0.0.1"
good, note = m3.check()
m3.host = "imap.gmail.com"; note = m3._explain(Exception("[AUTHENTICATIONFAILED] Application-specific password required"))
check("wrong password on Gmail → says 'APP PASSWORD', in words", "APP PASSWORD" in note, note)
# host guesses
os.environ.pop("BAI_MAIL_IMAP_HOST", None)
for addr, host in (("x@gmail.com", "imap.gmail.com"), ("x@libero.it", "imapmail.libero.it"), ("x@gmx.com", "imap.gmx.com"), ("x@outlook.com", "outlook.office365.com")):
    os.environ["BAI_ACCOUNT_EMAIL"] = addr
    check(f"host guessed for {addr}", IM.IdMail().host == host, IM.IdMail().host)
# accounts: the lost identity is retired, the new one is used, codes come from IMAP
os.environ.update({"BAI_ACCOUNT_EMAIL": "carlo@example.com", "BAI_MAIL_PASSWORD": GOOD_PW, "BAI_MAIL_IMAP_HOST": "127.0.0.1", "BAI_STATE": tempfile.mkdtemp()})
os.environ.pop("BAI_MAIL_ALIAS", None)
import importlib, agent.config as _cfg; importlib.reload(_cfg)
import agent.accounts as AC; importlib.reload(AC)
import json, pathlib
pathlib.Path(os.environ["BAI_STATE"]).mkdir(exist_ok=True)
AC.ACCOUNTS.write_text(json.dumps({"accounts": [{"site": "temu.com", "email": "busynessai001@gmail.com", "status": "active", "t": "x"}], "approved": [], "refused": []}))
A = AC.Accounts(log=lambda k, **f: None)
check("an account made with the banned mailbox is marked 'lost' and no longer 'known'", A.data["accounts"][0]["status"] == "lost" and A.known("https://www.temu.com/") is None, A.data["accounts"])
check("identity address is the new mailbox; site password stays separate", A.id.email == "carlo@example.com" and A.mail.configured())
c, _ = A._find_code("temu", tries=1)
check("Accounts._find_code goes through IMAP (no Google)", c == "482913" and A.google is None, c)
check("mail_ok() true without any Google connection", A.mail_ok())
print(f"IDMAIL SCORE: {ok}/{tot}")
srv.close()
