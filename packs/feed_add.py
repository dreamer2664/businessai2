"""Grow a pack across sessions (item 8): add new guide URLs to a pack's sources.

Usage (runs on the PC, needs network):
  python3 packs/feed_add.py packs/sources/web_urls_dropship.tsv <ext_dir> <url>... [--topic suppliers]

Fetches the URLs (skips ones already listed and ones that fail/are thin), trims them,
appends the passages to the pack's ext dir with renumbered aids, and appends the good
URLs to the TSV. Then rebuild the .kdw with packs/build_pack.py (see docs/PACKS.md).

Offline-tested: python3 engine/scripts/score_dropship.py (append/dedupe/tsv logic on fixtures).
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_tsv(path):
    rows = []
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.rstrip("\n")
            if line.strip():
                rows.append(line.split("\t"))
    return rows


def append_ext(ext_dir, staging_dir):
    """Append staging articles/passages to ext_dir with renumbered aids. Returns (articles, passages) added."""
    arts = read_tsv(os.path.join(staging_dir, "articles.tsv"))
    passe = read_tsv(os.path.join(staging_dir, "passages.tsv"))
    old_arts = read_tsv(os.path.join(ext_dir, "articles.tsv"))
    old_passe = read_tsv(os.path.join(ext_dir, "passages.tsv"))
    aids = [int(r[0]) for r in old_arts + old_passe if r and r[0].isdigit()]
    nxt = max(aids) + 1 if aids else 0
    amap = {}
    with open(os.path.join(ext_dir, "articles.tsv"), "a", encoding="utf-8") as fa:
        for r in arts:
            if len(r) < 3:
                continue
            amap[r[0]] = nxt
            fa.write(f"{nxt}\t{r[1]}\t{r[2]}\n")
            nxt += 1
    n = 0
    with open(os.path.join(ext_dir, "passages.tsv"), "a", encoding="utf-8") as fp:
        for r in passe:
            if len(r) < 2 or r[0] not in amap:
                continue
            fp.write(f"{amap[r[0]]}\t{r[1]}\n")
            n += 1
    return len(amap), n


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    topic = next((argv[i + 1] for i, a in enumerate(argv) if a == "--topic"), "suppliers")
    if len(args) < 3:
        print(__doc__.strip().splitlines()[2].strip())
        return 1
    tsv, ext_dir, urls = args[0], args[1], args[2:]
    urls = [u for u in urls if u.startswith(("http://", "https://"))]
    if not urls:
        print("no usable URLs (need http(s) links).")
        return 1
    have = {r[1] for r in read_tsv(tsv) if len(r) > 1}
    urls = [u for u in dict.fromkeys(urls) if u not in have]
    if not urls:
        print("all URLs are already in the list — nothing to do.")
        return 0
    tmp = tempfile.mkdtemp(prefix="feed_")
    src, web, stg = os.path.join(tmp, "new.tsv"), os.path.join(tmp, "web.tsv"), os.path.join(tmp, "ext")
    open(src, "w").write("".join(f"{topic}\t{u}\n" for u in urls))
    print(f"fetching {len(urls)}…", flush=True)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "packs/web_fetch.py"), src, web],
                       capture_output=True, text=True)
    print("\n".join(l for l in r.stdout.splitlines() if l.startswith(("FAIL", "thin", "fetched"))))
    got = {r[2] for r in read_tsv(web) if len(r) > 2}
    if not got:
        print("nothing fetchable — list unchanged.")
        return 1
    subprocess.run([sys.executable, os.path.join(ROOT, "packs/trim.py"), web, stg],
                   capture_output=True, text=True)
    na, np_ = append_ext(ext_dir, stg)
    with open(tsv, "a", encoding="utf-8") as f:
        for u in urls:
            if u in got:
                f.write(f"{topic}\t{u}\n")
    print(f"added {len(got)} URL(s), {na} article(s), {np_} passage(s). Rebuild: python3 packs/build_pack.py {ext_dir} release/packs/<name>.kdw")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
