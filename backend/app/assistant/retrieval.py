"""TF-IDF passage retrieval (scikit-learn), rebuilt when the NASA corpus grows."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

import numpy as np
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

from app.assistant.corpus import Passage

MIN_SCORE = 0.06
_TOKEN = re.compile(r"[a-z0-9₂]{2,}")


def stem(word: str) -> str:
    """Light suffix stripping so 'baselines', 'baseline' and 'computed'/'compute' meet."""
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        word = word[:-1]
    for suffix in ("ation", "ing", "ed"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            word = word[: -len(suffix)]
            break
    if len(word) > 4 and word.endswith("e"):
        word = word[:-1]
    return word


def analyse(text: str) -> list[str]:
    words = [stem(w) for w in _TOKEN.findall(text.lower()) if w not in ENGLISH_STOP_WORDS]
    return words + [f"{a} {b}" for a, b in zip(words, words[1:])]


@dataclass
class Hit:
    passage: Passage
    score: float


class PassageIndex:
    def __init__(self, passages: list[Passage]) -> None:
        self.passages = passages
        self.built_at = time.time()
        self.vectorizer = TfidfVectorizer(analyzer=analyse, sublinear_tf=True, min_df=1, max_df=0.6)
        self.matrix = self.vectorizer.fit_transform([p.search_text for p in passages]) if passages else None

    def search(self, query: str, k: int = 6, source_types: tuple[str, ...] | None = None,
               min_score: float = MIN_SCORE) -> list[Hit]:
        if self.matrix is None or not query.strip():
            return []
        scores = linear_kernel(self.vectorizer.transform([query]), self.matrix).ravel()
        order = np.argsort(-scores)
        hits: list[Hit] = []
        seen_docs: dict[str, int] = {}
        for i in order:
            s = float(scores[i])
            if s < min_score:
                break
            p = self.passages[i]
            if source_types and p.source_type not in source_types:
                continue
            key = p.path or p.title
            if seen_docs.get(key, 0) >= 2:  # at most two passages per document keeps sources diverse
                continue
            seen_docs[key] = seen_docs.get(key, 0) + 1
            hits.append(Hit(p, round(s, 4)))
            if len(hits) >= k:
                break
        return hits
