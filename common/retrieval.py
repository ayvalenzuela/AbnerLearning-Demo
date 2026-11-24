"""Tiny local retrieval used by the RAG builds when run offline.

TF-IDF vectors + cosine similarity in pure Python. It stands in for a real embedding
model + pgvector (or another vector store) so the demo runs on any laptop with no
services. The interface (add chunks with metadata, search with a metadata filter)
is the same shape you would use against pgvector.
"""
from __future__ import annotations

import math
import re
from collections import Counter

STOP = set("""a an and are as at be by for from has have in is it of on or that the this to was were
with which when who will shall all any following at least per must not be been its their than""".split())


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9][a-z0-9\-]*", text.lower()) if t not in STOP and len(t) > 1]


class TfidfIndex:
    def __init__(self):
        self.chunks: list[dict] = []   # {"id", "text", "meta": {...}}
        self.vectors: list[dict[str, float]] = []
        self.idf: dict[str, float] = {}

    def add(self, chunk_id: str, text: str, **meta):
        self.chunks.append({"id": chunk_id, "text": text, "meta": meta})

    def build(self):
        n = len(self.chunks)
        df = Counter()
        tfs = []
        for c in self.chunks:
            tf = Counter(tokenize(c["text"]))
            tfs.append(tf)
            df.update(tf.keys())
        self.idf = {t: math.log((1 + n) / (1 + d)) + 1 for t, d in df.items()}
        self.vectors = [self._vec(tf) for tf in tfs]
        return self

    def _vec(self, tf: Counter) -> dict[str, float]:
        v = {t: (1 + math.log(c)) * self.idf.get(t, 0.0) for t, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {t: x / norm for t, x in v.items()}

    def embed(self, text: str) -> dict[str, float]:
        return self._vec(Counter(tokenize(text)))

    def search(self, query: str, k: int = 3, **filters) -> list[tuple[float, dict]]:
        q = self.embed(query)
        scored = []
        for c, v in zip(self.chunks, self.vectors):
            if any(c["meta"].get(key) != val for key, val in filters.items()):
                continue
            s = sum(w * v.get(t, 0.0) for t, w in q.items())
            scored.append((round(s, 3), c))
        scored.sort(key=lambda x: -x[0])
        return scored[:k]

    def stats(self) -> dict:
        return {"chunks": len(self.chunks), "vocabulary": len(self.idf)}
