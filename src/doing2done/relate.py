"""Related-notes / backlinks via pure-Python TF-IDF + shared-tag boost.

No embeddings API, no deps. Computes note-to-note similarity and injects a
"## Related" section into each vault note (idempotent).
"""
from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path

_STOP = set(
    "the a an and or but of to in on for with at by from is are was were be been "
    "this that these those it its as i you he she we they my your our their not no "
    "do does did will would can could should have has had if then than so about into "
    "over out up down more most some any all one two can’t don’t note notes todo".split()
)
_REL_RE = re.compile(r"\n## Related\n.*?(?=\n## |\Z)", re.S)


def _tokens(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2 and w not in _STOP]


def _frontmatter(md: str) -> tuple[dict, str]:
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", md, re.S)
    if not m:
        return {}, md
    fm: dict = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        v = v.strip()
        if v.startswith("[") and v.endswith("]"):
            fm[k.strip()] = [x.strip().strip("\"'") for x in v[1:-1].split(",") if x.strip()]
        else:
            fm[k.strip()] = v.strip("\"'")
    return fm, m.group(2)


def relate_vault(notes_dir: str, top_k: int = 5, threshold: float = 0.06) -> int:
    nd = Path(notes_dir)
    files = [f for f in nd.glob("*.md") if f.name != "index.md"]
    docs = []
    for f in files:
        fm, body = _frontmatter(f.read_text())
        text = f"{fm.get('title', '')} {fm.get('summary', '')} {body}"
        docs.append(
            {
                "file": f,
                "stem": f.stem,
                "title": fm.get("title", f.stem),
                "tags": set(fm.get("tags", []) or []),
                "tf": Counter(_tokens(text)),
            }
        )
    if len(docs) < 2:
        return 0

    # idf
    df: Counter = Counter()
    for d in docs:
        for term in d["tf"]:
            df[term] += 1
    n = len(docs)
    idf = {t: math.log(n / (1 + c)) + 1 for t, c in df.items()}

    def vec(d):
        v = {t: (f / max(d["tf"].values())) * idf[t] for t, f in d["tf"].items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return v, norm

    vecs = [vec(d) for d in docs]

    def cosine(i, j):
        vi, ni = vecs[i]
        vj, nj = vecs[j]
        small, big = (vi, vj) if len(vi) < len(vj) else (vj, vi)
        dot = sum(w * big.get(t, 0.0) for t, w in small.items())
        return dot / (ni * nj)

    updated = 0
    for i, d in enumerate(docs):
        scored = []
        for j, other in enumerate(docs):
            if i == j:
                continue
            sim = cosine(i, j) + 0.05 * len(d["tags"] & other["tags"])  # shared-tag boost
            if sim >= threshold:
                scored.append((sim, other))
        scored.sort(key=lambda x: -x[0])
        related = scored[:top_k]
        block = ""
        if related:
            block = "\n## Related\n\n" + "\n".join(
                f"- [{o['title']}](./{o['stem']})" for _, o in related
            ) + "\n"
        raw = d["file"].read_text()
        raw = _REL_RE.sub("", raw).rstrip() + ("\n" + block if block else "\n")
        d["file"].write_text(raw)
        if block:
            updated += 1
    return updated
