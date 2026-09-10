"""Configuration for the business agent.

All secrets live in .secrets/env (git-ignored) as KEY=VALUE lines, or in the
environment. Nothing here is ever printed; redact() strips known secrets from
any text before it is logged or sent anywhere.
"""
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SECRETS_FILE = ROOT / ".secrets" / "env"
STATE_DIR = pathlib.Path(os.environ.get("BAI_STATE", ROOT / "state"))
LOG_DIR = STATE_DIR / "logs"

_SECRET_KEYS = ("GITHUB_TOKEN", "GH_TOKEN", "TELEGRAM_BOT_TOKEN", "OPENAI_API_KEY",
                "GROQ_API_KEY", "GOOGLE_API_KEY", "SHOPIFY_TOKEN", "MAIL_PASSWORD", "META_PAGE_TOKEN", "BAI_LLM_KEY",
                "BAI_ACCOUNT_PASSWORD", "BAI_MAIL_PASSWORD", "GMAIL_APP_PASSWORD", "FALLBACK_BOT_TOKEN")


def load_env(path=SECRETS_FILE):
    """Load KEY=VALUE lines into os.environ (existing env wins)."""
    if not path.exists():
        return {}
    loaded = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        os.environ.setdefault(k, v)
        loaded[k] = os.environ[k]
    return loaded


load_env()

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_OWNER_USERNAME = os.environ.get("TELEGRAM_OWNER_USERNAME", "").lstrip("@").lower()
TELEGRAM_OWNER_ID = int(os.environ.get("TELEGRAM_OWNER_ID", "0") or 0)

OWNER_EMAILS = os.environ.get("OWNER_EMAILS", "")
FALLBACK_BOT_TOKEN = os.environ.get("FALLBACK_BOT_TOKEN", "")

# Knowledge brain (the C engine from kdr-brain). Optional at milestone 0.
BRAIN_BIN = os.environ.get("BAI_BRAIN_BIN", str(ROOT / "release" / "kdr-brain-lite"))
BRAIN_KDR = os.environ.get("BAI_BRAIN_KDR", str(ROOT / "release" / "brain.kdr"))
BRAIN_PORT = int(os.environ.get("BAI_BRAIN_PORT", "8090"))
PACKS_DIR = ROOT / "release" / "packs"


def redact(text):
    """Remove every known secret value from text (for logs / messages)."""
    if not text:
        return text
    for k in _SECRET_KEYS:
        v = os.environ.get(k)
        if v and len(v) >= 8:
            text = text.replace(v, f"<{k}>")
    try:                                                                  # the owner's hand-made site passwords too (.secrets/sites.json)
        import json as _j
        for v in _site_secrets():
            if v and len(v) >= 6:
                text = text.replace(v, "<site-password>")
    except Exception:
        pass
    return text


_SITE_CACHE = {"t": 0, "vals": []}


def _site_secrets():
    import json as _j, time as _t
    p = pathlib.Path(os.environ.get("BAI_SITES_FILE") or (ROOT / ".secrets" / "sites.json"))
    try:
        mt = p.stat().st_mtime
    except Exception:
        return []
    if _SITE_CACHE["t"] != mt:
        try:
            d = _j.loads(p.read_text())
            _SITE_CACHE["vals"] = [v.get("password", "") for v in d.values() if isinstance(v, dict)]
        except Exception:
            _SITE_CACHE["vals"] = []
        _SITE_CACHE["t"] = mt
    return _SITE_CACHE["vals"]


def ensure_dirs():
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
