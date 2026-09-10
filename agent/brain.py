"""Adapter to the knowledge brain (the C engine inherited from kdr-brain).

The brain = engine binary (release/kdr-brain-lite) + brain.kdr (retriever + reader
models) + knowledge packs (release/packs/*.kdw, e.g. business.kdw).
ask() runs the engine's `wiki` command against the pack and returns the answer
sentence with its source title; None when the brain is not installed or unsure.
"""
import json
import os
import shutil
import subprocess

from . import config


class Brain:
    def __init__(self):
        self.bin = config.BRAIN_BIN if os.path.isfile(config.BRAIN_BIN) else shutil.which("kdr-brain-lite")
        self.kdr = config.BRAIN_KDR if os.path.isfile(config.BRAIN_KDR) else None
        self.packs = sorted(str(p) for p in config.PACKS_DIR.glob("*.kdw")) if config.PACKS_DIR.exists() else []

    @property
    def ready(self):
        return bool(self.bin and self.kdr and self.packs)

    def describe(self):
        if not (self.bin and self.kdr):
            return "engine not installed (run scripts/get_brain.sh)"
        mb = lambda p: f"{os.path.getsize(p) / 1e6:.1f} MB"
        packs = ", ".join(f"{os.path.basename(p)} {mb(p)}" for p in self.packs) or "no knowledge packs yet"
        return f"engine {mb(self.bin)} + models {mb(self.kdr)}; packs: {packs}"

    RELEASE_PACKS = ("business.kdw", "operations.kdw", "dropship.kdw", "marketplaces.kdw")     # packs published on the GitHub Release (scripts/get_brain.sh fetches the same list)

    def refresh(self):
        self.packs = sorted(str(p) for p in config.PACKS_DIR.glob("*.kdw")) if config.PACKS_DIR.exists() else []
        return self.packs

    def missing_packs(self):
        return [n for n in self.RELEASE_PACKS if not (config.PACKS_DIR / n).is_file()]

    def fetch_missing(self, log=None):
        """Download release packs that are not on this machine yet (new packs arrive with a plain `git pull` this way)."""
        got = []
        for name in self.missing_packs():
            url = f"https://github.com/{os.environ.get('BAI_REPO', 'dreamer2664/businessai2')}/releases/download/latest/{name}"
            tmp = config.PACKS_DIR / (name + ".part")
            try:
                config.PACKS_DIR.mkdir(parents=True, exist_ok=True)
                import urllib.request
                with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
                    while True:
                        chunk = r.read(1 << 20)
                        if not chunk:
                            break
                        f.write(chunk)
                if tmp.stat().st_size > 100_000:
                    tmp.rename(config.PACKS_DIR / name)
                    got.append(name)
                else:
                    tmp.unlink(missing_ok=True)
            except Exception as e:
                tmp.unlink(missing_ok=True)
                if log:
                    log("pack_fetch_failed", pack=name, error=str(e)[:120])
        if got and log:
            log("pack_fetched", packs=got)
        self.refresh()
        return got

    def ask_raw(self, question, pack=None, timeout=60):
        if pack is None:
            self.refresh()
        if not self.ready or not question:
            return None
        pack = pack or self.packs[0]
        cmd = [self.bin, self.kdr, "--wiki", pack, "wiki", question]
        env = dict(os.environ); env.setdefault("KDR_WIKI_READK", "3")   # tuned on tests/business.txt: 52/55, 2.5x faster
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
            return json.loads(out.stdout)
        except (subprocess.TimeoutExpired, OSError, ValueError):
            return None

    @staticmethod
    def _quality(d):
        """How good is this pack's answer? The reader's confidence alone prefers a confident span from an off-topic passage;
        weighting it by how well the best passage matched the question in meaning fixes that (tested: business 52/55 + operations 38/41
        with both packs loaded, vs 49/55 + 38/41 on confidence alone)."""
        hits = d.get("hits") or []
        dense = max((h.get("dense", 0) for h in hits), default=0)      # meaning match of the best passage (0..1)
        return d.get("confidence", 0) * dense

    MIN_QUALITY = 0.30      # confidence × meaning match. Scan over tests/business + operations (96 q): every correct answer scores ≥ 0.33,
                            # off-topic "answers" to owner chatter sit below ("send me the last document" → abandoned-cart mails 0.18,
                            # "how's the store doing" → store location 0.15, "why so slow yesterday" → checkout length 0.27).

    def ask(self, question, min_conf=0.35, min_quality=None):
        """Best answer across packs, formatted for the owner. None if the brain isn't confident — or if the passage merely
        contains confident words without matching the question's meaning (that is what produced off-topic 'answers')."""
        best = None
        for pack in self.refresh():
            d = self.ask_raw(question, pack)
            if d and d.get("answer") and (best is None or self._quality(d) > self._quality(best)):
                best = d
        if not best or best.get("confidence", 0) < min_conf or not best.get("answer"):
            return None
        if self._quality(best) < (self.MIN_QUALITY if min_quality is None else min_quality):
            return None
        sent = (best.get("sentence") or best["answer"]).strip()
        ans = best["answer"].strip()
        text = sent if ans.lower() in sent.lower() else f"{ans}. {sent}"
        if len(text) > 700:
            text = text[:700].rsplit(" ", 1)[0] + "…"
        src = best.get("title") or ""
        return f"{text}\n— {src} (knowledge pack, confidence {best['confidence']:.2f})"
