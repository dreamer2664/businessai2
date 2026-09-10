"""The agent's own library (milestone 14, local half of milestone 17): documents it produces — research reports, seller
checks, comparisons, websites — as self-contained HTML files under state/library/, listed in an index, sent to the owner's
phone as files, and (when Drive is connected) mirrored there.

A Doc is built section by section:  doc = Doc(title, subtitle); doc.summary(text); doc.option(...) ...; path = doc.save()
Pictures are embedded as data URIs (small JPEGs) so the file works anywhere, offline, without leaking the owner's clicks.
"""
import base64
import datetime as _dt
import html
import json
import os
import re
import time

from . import config

LIB_DIR = config.STATE_DIR / "library"
INDEX = LIB_DIR / "index.jsonl"

CSS = """
body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:860px;margin:24px auto;padding:0 16px;color:#1b1b1b;line-height:1.45}
h1{font-size:1.6em;margin:.2em 0}h2{font-size:1.2em;margin:1.4em 0 .4em;border-bottom:1px solid #e5e5e5;padding-bottom:.2em}
.sub{color:#666;margin-bottom:1.2em}.box{background:#f6f7f9;border-radius:10px;padding:12px 16px;margin:10px 0}
.opt{display:grid;grid-template-columns:180px 1fr;gap:16px;border:1px solid #e5e5e5;border-radius:12px;padding:14px;margin:14px 0}
.opt img{width:180px;height:180px;object-fit:cover;border-radius:8px;background:#eee}.opt .noimg{width:180px;height:180px;border-radius:8px;background:#eee;color:#999;display:flex;align-items:center;justify-content:center;font-size:.9em}
.verdict{font-weight:600}.good{color:#1a7f37}.ok{color:#9a6700}.bad{color:#b42318}
table{border-collapse:collapse;width:100%;font-size:.95em}td,th{border-bottom:1px solid #eee;padding:6px 8px;text-align:left;vertical-align:top}
.src{font-size:.85em;color:#666;word-break:break-all}.tag{display:inline-block;background:#eef2ff;color:#3730a3;border-radius:6px;padding:1px 7px;font-size:.8em;margin-right:4px}
.small{font-size:.85em;color:#666}ul{margin:.3em 0 .3em 1.2em}
.glance{display:grid;gap:8px;margin:8px 0}.g{display:grid;grid-template-columns:1fr auto;gap:2px 12px;border:1px solid #e5e5e5;border-radius:10px;padding:10px 12px}
.g .n{font-weight:600}.g .p{font-weight:700;color:#1a7f37;white-space:nowrap}.g .w{color:#666;font-size:.9em;grid-column:1/-1}.g a{font-size:.9em}
.opt h3 a{color:inherit;text-decoration:none}.opt .src a{word-break:break-all}.pill{display:inline-block;border-radius:6px;padding:1px 7px;font-size:.8em;background:#f1f5f9;color:#334155;margin-right:4px}
@media(max-width:600px){body{margin:12px auto}.opt{grid-template-columns:1fr}.opt img,.opt .noimg{width:100%;height:200px}table{display:block;overflow-x:auto}h1{font-size:1.35em}}
"""


def _short_url(u, n=48):
    """vinted.it/items/99…-nintendo-switch — readable on a phone, the full url stays in href."""
    s = re.sub(r"^https?://(www\.)?", "", u or "")
    return s if len(s) <= n else s[:n - 1] + "…"


def _slug(text, n=48):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (s[:n].rstrip("-") or "doc")


class Doc:
    def __init__(self, title, subtitle="", kind="report"):
        self.title, self.subtitle, self.kind = title, subtitle, kind
        self.parts = []
        self.sources = []
        self.n_options = 0
        self.created = _dt.datetime.now()

    # ---- building blocks -----------------------------------------------------------
    def summary(self, text, heading="In short"):
        self.parts.append(f"<h2>{html.escape(heading)}</h2><div class=box>{_para(text)}</div>")
        return self

    def section(self, heading, text):
        self.parts.append(f"<h2>{html.escape(heading)}</h2>{_para(text)}")
        return self

    def bullets(self, heading, items):
        if items:
            self.parts.append(f"<h2>{html.escape(heading)}</h2><ul>" + "".join(f"<li>{_inline(i)}</li>" for i in items) + "</ul>")
        return self

    def table(self, heading, rows, header=None):
        if not rows:
            return self
        h = ("<tr>" + "".join(f"<th>{html.escape(str(c))}</th>" for c in header) + "</tr>") if header else ""
        b = "".join("<tr>" + "".join(f"<td>{_inline(str(c))}</td>" for c in r) + "</tr>" for r in rows)
        self.parts.append(f"<h2>{html.escape(heading)}</h2><table>{h}{b}</table>")
        return self

    def option(self, name, url, price="", image=None, verdict="", grade="ok", facts=None, pros=None, cons=None, note=""):
        """One researched option: picture, link, price, facts, verdict (grade: good | ok | bad)."""
        self.n_options += 1
        img = (f'<img src="{_data_uri(image)}" alt="">' if image else '<div class=noimg>no picture</div>')
        facts_html = "".join(f"<tr><th>{html.escape(k)}</th><td>{_inline(str(v))}</td></tr>" for k, v in (facts or {}).items() if v)
        pc = ""
        if pros:
            pc += "<div class=small>👍 " + " · ".join(html.escape(p) for p in pros) + "</div>"
        if cons:
            pc += "<div class=small>👎 " + " · ".join(html.escape(c) for c in cons) + "</div>"
        self.parts.append(
            f'<div class=opt>{img}<div><h3 style="margin:0 0 4px">{self.n_options}. ' + (f'<a href="{html.escape(url)}">{html.escape(name)}</a>' if url else html.escape(name))
            + (f' <span class=tag>{html.escape(price)}</span>' if price else "") + "</h3>"
            + (f'<div class=src><a href="{html.escape(url)}">open the listing → {html.escape(_short_url(url))}</a></div>' if url else "")
            + (f'<table style="margin:8px 0">{facts_html}</table>' if facts_html else "")
            + (f'<div class="verdict {grade}">{html.escape(verdict)}</div>' if verdict else "")
            + pc + (f"<p class=small>{_inline(note)}</p>" if note else "") + "</div></div>")
        if url:
            self.sources.append(url)
        return self

    def glance(self, heading, rows):
        """Phone-friendly summary cards: rows = [(name, price_text, where_text, url or "")]. Replaces a wide table."""
        cards = []
        for name, price, where, url in rows:
            cards.append(f'<div class=g><div class=n>{html.escape(str(name))}</div><div class=p>{html.escape(str(price))}</div>'
                         + f'<div class=w>{html.escape(str(where))}' + (f' · <a href="{html.escape(url)}">open the listing →</a>' if url else "") + '</div></div>')
        self.parts.append(f"<h2>{html.escape(heading)}</h2><div class=glance>" + "".join(cards) + "</div>")
        return self

    def source(self, url, title=""):
        self.sources.append(url if not title else f"{title} — {url}")
        return self

    # ---- output --------------------------------------------------------------------
    def html(self):
        srcs = list(dict.fromkeys(self.sources))
        src_html = ("<h2>Sources — pages I read</h2><ol class=src>" + "".join(f"<li>{_linkify(s)}</li>" for s in srcs) + "</ol>") if srcs else ""
        return (f"<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
                f"<title>{html.escape(self.title)}</title><style>{CSS}</style></head><body>"
                f"<h1>{html.escape(self.title)}</h1><div class=sub>{html.escape(self.subtitle)} · {self.created:%d %b %Y, %H:%M} · written by Business AI</div>"
                + "".join(self.parts) + src_html + "</body></html>")

    def save(self, name=None):
        LIB_DIR.mkdir(parents=True, exist_ok=True)
        fn = f"{self.created:%Y-%m-%d}_{_slug(name or self.title)}.html"
        path = LIB_DIR / fn
        i = 2
        while path.exists():
            path = LIB_DIR / fn.replace(".html", f"-{i}.html")
            i += 1
        path.write_text(self.html(), encoding="utf-8")
        with open(INDEX, "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": self.created.isoformat(timespec="seconds"), "kind": self.kind, "title": self.title,
                                "file": path.name, "options": self.n_options, "sources": len(set(self.sources))}, ensure_ascii=False) + "\n")
        return path


def _para(text):
    text = (text or "").strip()
    if not text:
        return ""
    return "".join(f"<p>{_inline(p)}</p>" for p in re.split(r"\n{2,}", text))


def _inline(text):
    """Escape, keep line breaks, make links clickable, **bold**."""
    t = html.escape(text or "")
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = _linkify(t, escaped=True)
    return t.replace("\n", "<br>")


def _linkify(s, escaped=False):
    if not escaped:
        s = html.escape(s)
    return re.sub(r"((?:https?|file)://[^\s<]+)", lambda m: f'<a href="{m.group(1)}">{m.group(1)[:80]}{"…" if len(m.group(1)) > 80 else ""}</a>', s)


def _data_uri(img):
    """bytes → data URI (JPEG/PNG sniffed); str that already is a URL/data URI → as is."""
    if isinstance(img, str):
        return img
    mime = "image/png" if img[:4] == b"\x89PNG" else "image/webp" if img[:4] == b"RIFF" else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(img).decode()


def register(kind, title, path, options=0, sources=0):
    """Put a file made elsewhere (a website zip, a screenshot, course notes) into the library index so /library shows it."""
    LIB_DIR.mkdir(parents=True, exist_ok=True)
    with open(INDEX, "a", encoding="utf-8") as f:
        f.write(json.dumps({"t": _dt.datetime.now().isoformat(timespec="seconds"), "kind": kind, "title": title, "file": str(path),
                            "options": options, "sources": sources}, ensure_ascii=False) + "\n")


def recent(n=10):
    if not INDEX.exists():
        return []
    rows = [json.loads(l) for l in INDEX.read_text(encoding="utf-8").splitlines() if l.strip()]
    return rows[-n:][::-1]


def list_text(n=10):
    rows = recent(n)
    if not rows:
        return "My library is empty. Ask me for research, a seller check or a comparison and the document lands here."
    def line(r):
        extra = f" ({r['options']} options, {r['sources']} sources)" if r.get("options") or r.get("sources") else ""
        return f"• {r['t'][:16].replace('T', ' ')} · {r['kind']} · {r['title'][:60]}{extra} — {os.path.basename(str(r['file']))}"
    return "My library (latest first):\n" + "\n".join(line(r) for r in rows)


def path_of(name):
    p = LIB_DIR / name
    return p if p.exists() else None
