"""Local, free retrieval over the company documents.

* EmbeddingIndex: sentence-transformers (default intfloat/multilingual-e5-small, 118M params, CPU).
  Multilingual, so a Russian question finds the English or German answer. Vectors are cached in
  SQLite and re-computed only when a document changes.
* RerankIndex (default): the 12 best chunks from the embeddings are re-scored by a small multilingual
  cross-encoder (cross-encoder/mmarco-mMiniLMv2-L12-H384-v1, 118M params) sentence by sentence.
  Its score is a calibrated "does this text answer the question" signal, which is what the
  hand-over threshold needs. Embedding similarity alone can't tell "close topic" from "answers it".
* BM25Index: keyword search (rank-bm25), used automatically if sentence-transformers is missing.
  Works well when the question and the document share a language.

All return hits with a score 0..1; below `min_score` the agent does not answer and hands over to a manager.
"""
from __future__ import annotations

import hashlib
import math
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from .loader import Chunk


@dataclass
class Hit:
    chunk: Chunk
    score: float


def _passage(c: Chunk) -> str:
    return f"{c.title}. {c.text}"


class BaseIndex:
    name = "base"
    default_min_score = 0.5

    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks

    def scores(self, query: str) -> np.ndarray:  # pragma: no cover - abstract
        raise NotImplementedError

    def search(self, query: str, k: int = 4, lang: Optional[str] = None) -> list[Hit]:
        """Best chunk per key (EN/DE twins count once), sorted by score."""
        s = self.scores(query)
        best: dict[str, Hit] = {}
        for i in np.argsort(-s):
            c = self.chunks[int(i)]
            if c.key not in best:
                best[c.key] = Hit(c, float(s[int(i)]))
            if len(best) >= k:
                break
        return sorted(best.values(), key=lambda h: -h.score)


class EmbeddingIndex(BaseIndex):
    name = "embeddings"
    # embeddings-only mode (no reranker): best split on the dev set, noticeably less accurate
    DEFAULT_THRESHOLDS = {"intfloat/multilingual-e5-small": 0.86}

    def __init__(self, chunks: list[Chunk], model_name: str, cache_db: Optional[str] = None):
        super().__init__(chunks)
        from sentence_transformers import SentenceTransformer  # heavy import only when used

        self.model_name = model_name
        self.e5 = "e5" in model_name.lower()
        self.default_min_score = self.DEFAULT_THRESHOLDS.get(model_name, 0.5)
        self.model = SentenceTransformer(model_name)
        self.matrix = self._vectors(cache_db)

    def _enc(self, texts: list[str], kind: str) -> np.ndarray:
        if self.e5:
            texts = [f"{kind}: {t}" for t in texts]
        return np.asarray(self.model.encode(texts, normalize_embeddings=True, batch_size=32), dtype=np.float32)

    def _vectors(self, cache_db: Optional[str]) -> np.ndarray:
        texts = [_passage(c) for c in self.chunks]
        hashes = [hashlib.sha256(f"{self.model_name}\n{t}".encode()).hexdigest() for t in texts]
        cached: dict[str, np.ndarray] = {}
        con = None
        if cache_db:
            Path(cache_db).parent.mkdir(parents=True, exist_ok=True)
            con = sqlite3.connect(cache_db)
            con.execute("CREATE TABLE IF NOT EXISTS vectors (hash TEXT PRIMARY KEY, vec BLOB)")
            q = ",".join("?" * len(hashes))
            for h, blob in con.execute(f"SELECT hash, vec FROM vectors WHERE hash IN ({q})", hashes):
                cached[h] = np.frombuffer(blob, dtype=np.float32)
        missing = [i for i, h in enumerate(hashes) if h not in cached]
        if missing:
            new = self._enc([texts[i] for i in missing], "passage")
            for i, v in zip(missing, new):
                cached[hashes[i]] = v
            if con:
                con.executemany("INSERT OR REPLACE INTO vectors VALUES (?, ?)",
                                [(hashes[i], cached[hashes[i]].tobytes()) for i in missing])
                con.commit()
        if con:
            con.close()
        return np.stack([cached[h] for h in hashes])

    def scores(self, query: str) -> np.ndarray:
        return self.matrix @ self._enc([query], "query")[0]


# The cross-encoder was trained on web search, where "you" is not the business. In a chat, "Where are
# you located?" means the school, so the query is rewritten before re-scoring ("Where is the school located?").
_REWRITE = {
    "en": [(r"\byour\b", "the school's"), (r"\b(do|can|are|will|would|could) you\b", r"\1 the school"),
           (r"\byou\b", "the school")],
    "de": [(r"\b(Ihre[nmrs]?|Ihr)\b", "der Schule"), (r"\b(Sie|Ihnen)\b", "die Schule")],
    "ru": [(r"\bу вас\b", "в школе"), (r"\b(ваш[а-я]*)\b", "школы"), (r"\bвы\b", "школа")],
}
_SENT = re.compile(r"(?<=[.!?])\s+")


def _sentences(text: str) -> list[str]:
    """Split into sentences; a very short one ("Yes.", "Ja.") is glued to the next, because on its own
    it would "answer" any yes/no question."""
    out: list[str] = []
    carry = ""
    for x in (p for p in _SENT.split(text) if p):
        x = f"{carry} {x}".strip() if carry else x
        if len(x) < 25:
            carry = x
            continue
        out.append(x)
        carry = ""
    if carry:
        out = out[:-1] + [f"{out[-1]} {carry}"] if out else [carry]
    return out


def rewrite_query(q: str, lang: str) -> str:
    for pat, rep in _REWRITE.get(lang, []):
        q = re.sub(pat, rep, q, flags=0 if lang == "de" else re.I)  # German "Sie" is capitalised
    return q


class RerankIndex(BaseIndex):
    """Embeddings find candidates, a cross-encoder scores them. Score = sigmoid(best logit) in 0..1."""
    name = "embeddings + reranker"
    # logit -1.0, chosen on tests/data/dev_questions.jsonl with a safety margin (see README, Evaluation)
    default_min_score = 0.27
    candidates = 12

    def __init__(self, emb: EmbeddingIndex, model_name: str):
        super().__init__(emb.chunks)
        from sentence_transformers import CrossEncoder

        self.emb = emb
        self.model_name = model_name
        self.ce = CrossEncoder(model_name, max_length=320)
        # every chunk is scored as a whole and sentence by sentence (long FAQ answers hide the one relevant line)
        self.passages = []
        for c in self.chunks:
            parts = _sentences(c.text)
            self.passages.append([f"{c.title}. {c.text}"] + ([f"{c.title}. {x}" for x in parts] if len(parts) > 1 else []))

    def search(self, query: str, k: int = 4, lang: Optional[str] = None) -> list[Hit]:
        from ..core.lang import detect

        cos = self.emb.scores(query)
        idx = [int(i) for i in np.argsort(-cos)[: self.candidates]]
        q = rewrite_query(query, lang or detect(query))
        pairs, owner = [], []
        for i in idx:
            for p in self.passages[i]:
                pairs.append((q, p))
                owner.append(i)
        logits = np.asarray(self.ce.predict(pairs, batch_size=64), dtype=np.float32)
        best: dict[int, float] = {}
        for i, z in zip(owner, logits):
            best[i] = max(best.get(i, -1e9), float(z))
        by_key: dict[str, Hit] = {}
        for i, z in sorted(best.items(), key=lambda x: -x[1]):
            c = self.chunks[i]
            if c.key not in by_key:
                by_key[c.key] = Hit(c, float(1 / (1 + math.exp(-z))))
        return sorted(by_key.values(), key=lambda h: -h.score)[:k]


_TOKEN = re.compile(r"[\wäöüß€]+", re.I)
_STOP = set("""a an the and or of to in on for is are be i you we my your our do does can how what when where which
who it this that with at by from there any have has me der die das und oder ein eine ist sind ich sie wir mein
ihr kann wie was wann wo gibt es mit bei für von zu im am den dem des и в на с по не я вы мы у ли как что где
когда есть можно ваш мой это""".split())


def _tokens(s: str) -> list[str]:
    out = []
    for t in _TOKEN.findall(s.lower()):
        if t in _STOP or len(t) < 2:
            continue
        out.append(t[:6])  # crude stemming: kurs/kurse/kursgebühr, course/courses, курс/курса
    return out


class BM25Index(BaseIndex):
    """Fallback without any model download. Score = BM25 normalised to 0..1 by the query's own maximum."""
    name = "bm25"
    default_min_score = 0.35

    def __init__(self, chunks: list[Chunk]):
        super().__init__(chunks)
        from rank_bm25 import BM25Okapi

        self.bm25 = BM25Okapi([_tokens(_passage(c)) for c in chunks])

    def scores(self, query: str) -> np.ndarray:
        q = _tokens(query)
        if not q:
            return np.zeros(len(self.chunks))
        raw = np.asarray(self.bm25.get_scores(q), dtype=np.float32)
        # squash to 0..1: ~0.5 at a score of 4 (two rare words matched)
        return 1 - np.exp(-raw / (4 / math.log(2)))


DEFAULT_RERANKER = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"


def make_index(chunks: list[Chunk], kind: str = "auto", model_name: str = "intfloat/multilingual-e5-small",
               cache_db: Optional[str] = None, rerank_model: str = DEFAULT_RERANKER) -> BaseIndex:
    """kind: auto (reranker if possible) | rerank | embeddings | bm25"""
    if kind in ("auto", "rerank", "embeddings"):
        try:
            emb = EmbeddingIndex(chunks, model_name, cache_db)
            if kind != "embeddings" and rerank_model:
                return RerankIndex(emb, rerank_model)
            return emb
        except ImportError:
            if kind != "auto":
                raise
    return BM25Index(chunks)
