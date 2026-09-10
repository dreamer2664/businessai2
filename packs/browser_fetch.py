"""Fetch help-centre articles through the real browser (sites that refuse plain HTTP: Zendesk help centres, SPA pages).
   python3 packs/browser_fetch.py <index-spec.tsv> <out.tsv>

index-spec.tsv lines:  topic <TAB> index-url <TAB> link-pattern (regex on href) <TAB> max-articles
The index page is opened, its links matching the pattern are collected (de-duplicated), and each article is opened and
reduced to headings + paragraphs, appended to out.tsv as (title, topic, url, text) like packs/web_fetch.py.
Gentle: 6 s between pages, one browser, cookie banners closed by Browser.open()."""
import html, os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent.browser import Browser, BrowserError

JS_TEXT = r"""
() => {
  const root = document.querySelector('article, main, [role=main], .article-body, .article, #article, .help-article, .content') || document.body;
  const out = [];
  for (const el of root.querySelectorAll('h1,h2,h3,h4,p,li')) {
    if (el.closest('nav,footer,header,aside,form,[role=navigation],[class*=breadcrumb],[class*=sidebar],[class*=related],[class*=footer],[class*=cookie]')) continue;
    const s = (el.innerText || '').replace(/\s+/g, ' ').trim();
    if (!s) continue;
    if (/^H[1-4]$/.test(el.tagName)) { if (s.length < 120) out.push('## ' + s); }
    else if (s.length >= 40 || (out.length && out[out.length-1].startsWith('## ') && s.length >= 20)) out.push(s);
  }
  return out;
}
"""


def main():
    spec, dst = sys.argv[1], sys.argv[2]
    try:
        have = set(l.split("\t")[2] for l in open(dst, encoding="utf-8") if l.count("\t") >= 3)
    except FileNotFoundError:
        have = set()
    out = open(dst, "a", encoding="utf-8")
    b = Browser(log=lambda *a, **k: None, viewer=None)
    n = 0
    try:
        for line in open(spec, encoding="utf-8"):
            if "\t" not in line or line.startswith("#"):
                continue
            topic, index, pat, mx = (line.rstrip("\n").split("\t") + ["", "", "", ""])[:4]
            mx = int(mx or 25)
            try:
                b.open(index)
                time.sleep(2)
                links = b.page.evaluate("() => [...document.querySelectorAll('a[href]')].map(a => [a.href, (a.innerText||'').trim()])")
            except BrowserError as e:
                print("FAIL index", index, str(e)[:60], flush=True)
                continue
            seen, todo = set(), []
            for href, label in links:
                h = href.split("#")[0]
                if re.search(pat, h) and h not in seen and h != index:
                    seen.add(h); todo.append(h)
            print(f"{topic}: {len(todo)} article links on {index[:60]}", flush=True)
            for u in todo[:mx]:
                if u in have:
                    continue
                time.sleep(6)
                try:
                    b.open(u)
                    time.sleep(1.5)
                    paras = b.page.evaluate(JS_TEXT)
                    title = b.page.title().strip()
                except Exception as e:
                    print("FAIL", u[:70], str(e)[:50], flush=True)
                    continue
                txt = "\n".join(paras)
                if len(txt) < 600:
                    print("thin", u[:70], len(txt), flush=True)
                    continue
                out.write(f"{title}\t{topic}\t{u}\t{txt.replace(chr(9), ' ').replace(chr(10), chr(92) + 'n')}\n"); out.flush()
                have.add(u); n += 1
    finally:
        b.close()
    print("fetched", n)


if __name__ == "__main__":
    main()
