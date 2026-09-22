"""Optional local metadata retrieval. Scores are lexical, not confidence values.

This module narrows a catalog only when the user explicitly selects indexed
routing. Jev still ranks and verifies candidates; excluded skills are not judged.
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Iterable

from .catalog import Skill
from .config import RouterError

INDEX_VERSION = 'metadata-bm25-v1'
_WORDS = re.compile(r'[^\W_]+', re.UNICODE)
_CJK = re.compile(r'[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7a3]+')
_STOP_WORDS = frozenset('a an and are as at be by for from in is it of on or that the this to with please'.split())


def terms(text: str) -> list[str]:
    """Normalize words and add CJK bigrams; no translation or semantic expansion."""
    normalized = unicodedata.normalize('NFKC', text).casefold()
    words = [word for word in _WORDS.findall(normalized) if word not in _STOP_WORDS]
    for run in _CJK.findall(normalized):
        if len(run) > 2:
            words.extend(run[i:i + 2] for i in range(len(run) - 1))
    return words


@dataclass(frozen=True)
class CandidateSet:
    ids: tuple[str, ...]
    matched_count: int
    cutoff_ties: int


class MetadataIndex:
    """An inverted index over names/descriptions; never indexes instruction bodies."""

    def __init__(self, skills: Iterable[Skill]):
        self.postings: dict[str, list[tuple[str, int]]] = defaultdict(list)
        self.lengths: dict[str, int] = {}
        self.order = {}
        for skill in skills:
            # Names carry explicit capability identifiers; modest term-frequency
            # weighting helps named requests without hard-coding any skill labels.
            counts = Counter(terms(skill.name) * 2 + terms(skill.description))
            self.lengths[skill.id] = sum(counts.values())
            self.order[skill.id] = (skill.name, skill.digest, skill.id)
            for term, count in counts.items():
                self.postings[term].append((skill.id, count))
        self.size = len(self.lengths)
        self.average_length = sum(self.lengths.values()) / max(1, self.size)

    def search(self, query: str, limit: int = 64) -> CandidateSet:
        if not isinstance(query, str) or type(limit) is not int or not 1 <= limit <= 10000:
            raise RouterError('Retrieval needs text and a candidate limit from 1 to 10000')
        scores: dict[str, float] = defaultdict(float)
        # Each query term contributes once; repeating instructions cannot inflate
        # its weight. The caller applies the ordinary focused-state byte limit.
        for term in sorted(set(terms(query))):
            postings = self.postings.get(term, ())
            if not postings:
                continue
            idf = math.log1p((self.size - len(postings) + .5) / (len(postings) + .5))
            for skill_id, frequency in postings:
                norm = 1.2 * (.25 + .75 * self.lengths[skill_id] / max(1, self.average_length))
                scores[skill_id] += idf * frequency * 2.2 / (frequency + norm)
        ranked = sorted(scores, key=lambda skill_id: (-scores[skill_id], self.order[skill_id]))
        chosen = ranked[:limit]
        ties = 0
        if chosen and len(ranked) > limit:
            cutoff = scores[chosen[-1]]
            ties = sum(math.isclose(scores[sid], cutoff, rel_tol=1e-12) for sid in ranked[limit:])
        return CandidateSet(tuple(chosen), len(ranked), ties)
