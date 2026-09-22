"""Bounded local evidence sampling; this never chooses or accepts a skill."""
from __future__ import annotations
import re


def excerpt(body: str, task: str, budget: int) -> str:
    """Keep the opening, ending and two useful windows within one character cap.

    Literal task overlap only prioritizes evidence windows for Jev to evaluate.
    When no terms match, sample both interior thirds. This cannot guarantee that
    a short excerpt captures every capability in a long document.
    """
    if len(body) <= budget:
        return body
    separator = '\n[…]\n'
    width = max(1, (budget - 3 * len(separator)) // 4)
    starts = list(range(0, len(body), width))
    terms = set(re.findall(r'[^\W_]{2,}', task.casefold()))
    # A focused task is bounded, but cap terms as well to avoid multiplying scan cost.
    terms = sorted(terms, key=lambda word: (-len(word), word))[:64]
    interior = []
    for start in starts[1:-1]:
        text = body[start:start + width].casefold()
        score = sum(min(len(term), 12) for term in terms if term in text)
        if score:
            interior.append((score, start))
    interior.sort(key=lambda item: (-item[0], item[1]))
    chosen = {0, len(body) - width}
    for _, start in interior:
        if all(abs(start - other) >= width for other in chosen):
            chosen.add(start)
        if len(chosen) == 4:
            break
    for fraction in (1/3, 2/3):
        start = int((len(body) - width) * fraction)
        if len(chosen) < 4 and all(abs(start - other) >= width for other in chosen):
            chosen.add(start)
    return separator.join(body[start:start + width] for start in sorted(chosen))[:budget]
