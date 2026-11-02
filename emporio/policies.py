"""Search over the store policy manual.

The manual is short (about 3,000 words), so a small keyword ranker is enough:
no vector database, no embeddings, no extra dependencies, and results are easy
to explain. The Markdown is split into one chunk per numbered (sub)section.
Ranking is BM25 over accent-free, crudely stemmed tokens, with the section
title counted extra so a query like "devolução" lands on the right section.
"""

import math
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

from emporio.data import normalize_text

POLICY_FILE = Path(__file__).resolve().parent.parent / "data" / "store_policies.md"

STOPWORDS = set("""a o as os um uma de do da dos das em no na nos nas por para com sem e ou que se
ao aos ha ja mais muito como qual quais quando onde eu voce meu minha seu sua isso esta este
sao ser foi tem ter pode posso podem loja tempo quanto""".split())

BM25_K1, BM25_B, TITLE_WEIGHT = 1.5, 0.75, 3
# Chosen from observed scores: off-topic questions top out near 1.9, the weakest
# legitimate ones ("tem garantia?") score about 3.5. Weaker hits than 40% of the
# best one are noise and are dropped.
MIN_SCORE = 3.0
RELATIVE_CUTOFF = 0.4


def _stem(token: str) -> str:
    # Crude on purpose: shared prefixes link devolver/devolução/devoluções.
    return token[:5]


def tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", normalize_text(text))
    return [_stem(w) for w in words if w not in STOPWORDS and len(w) > 1]


@lru_cache(maxsize=1)
def load_chunks(path: Path = POLICY_FILE) -> tuple[dict, ...]:
    """One chunk per '##' or '###' heading. A '##' chunk holds only the text
    before its first '###', which keeps chunks small and specific."""
    chunks, parent = [], ""
    current = None
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^(#{2,3}) (\S+?)\.? (.+)$", line)
        if m:
            current = {"section": m.group(2), "title": m.group(3), "lines": []}
            if m.group(1) == "##":
                parent = m.group(3)
                current["context"] = ""
            else:
                current["context"] = parent
            chunks.append(current)
        elif current is not None:
            current["lines"].append(line)
    out = []
    for c in chunks:
        text = "\n".join(c["lines"]).strip()
        if text:
            full_title = c["title"] + (f" ({c['context']})" if c["context"] else "")
            out.append({"section": c["section"], "title": full_title, "text": text})
    return tuple(out)


def search_policies(query: str, top_k: int = 3) -> dict:
    chunks = load_chunks()
    q_tokens = set(tokenize(query))
    if not q_tokens:
        return {"found": False, "note": "Consulta vazia."}

    docs = [Counter(tokenize(c["text"]) + tokenize(c["title"]) * TITLE_WEIGHT) for c in chunks]
    lengths = [sum(d.values()) for d in docs]
    avg = sum(lengths) / len(docs)
    scored = []
    for chunk, doc, length in zip(chunks, docs, lengths):
        score = 0.0
        for t in q_tokens:
            tf = doc.get(t, 0)
            if not tf:
                continue
            df = sum(1 for d in docs if t in d)
            idf = math.log(1 + (len(docs) - df + 0.5) / (df + 0.5))
            score += idf * tf * (BM25_K1 + 1) / (tf + BM25_K1 * (1 - BM25_B + BM25_B * length / avg))
        scored.append((score, chunk))
    scored.sort(key=lambda s: s[0], reverse=True)

    best = scored[0][0]
    hits = [{"section": c["section"], "title": c["title"], "text": c["text"], "score": round(s, 2)}
            for s, c in scored[:top_k] if s >= MIN_SCORE and s >= RELATIVE_CUTOFF * best]
    # A hit on a section intro ("4. Trocas e Devoluções") brings its subsections along:
    # the intro is short, so it outranks the subsection that holds the actual rule (4.1: 7 days).
    for hit in list(hits):
        if "." not in hit["section"]:
            have = {h["section"] for h in hits}
            hits += [{"section": c["section"], "title": c["title"], "text": c["text"], "score": 0.0}
                     for c in chunks if c["section"].startswith(hit["section"] + ".") and c["section"] not in have]
    if not hits:
        return {"found": False,
                "note": "Nenhuma política cobre isso. Não invente uma regra: diga que vai confirmar "
                        "com a equipe e encaminhe a um atendente."}
    return {"found": True, "sections": hits,
            "note": "O manual é de uso interno: responda com suas palavras, sem copiar trechos longos."}
