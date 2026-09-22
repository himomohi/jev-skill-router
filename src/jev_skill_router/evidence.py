"""Bounded local evidence sampling; this never chooses or accepts a skill."""
from __future__ import annotations
import re

SEPARATOR = '\n[…]\n'


def excerpt(body: str, task: str, budget: int) -> str:
    """Keep the opening, ending and two useful windows within one character cap.

    Literal task overlap only prioritizes evidence windows for Jev to evaluate.
    When no terms match, sample both interior thirds. This cannot guarantee that
    a short excerpt captures every capability in a long document.
    """
    if len(body) <= budget:
        return body
    separator = SEPARATOR
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


def json_width_counts(body: str) -> tuple[int, ...]:
    """Cache a UTF-8 JSON character-width histogram when loading a skill.

    Unlike extracting evidence, these C-level character scans do not depend on
    the task. Valid UTF-8 source files contain no unpaired surrogates.
    """
    two = len(re.findall(r'["\\\b\t\n\f\r\u0080-\u07ff]', body))
    three = len(re.findall(r'[\u0800-\uffff]', body))
    four = len(re.findall(r'[\U00010000-\U0010ffff]', body))
    six = len(re.findall(r'[\x00-\x07\x0b\x0e-\x1f]', body))
    return (len(body)-two-three-four-six, two, three, four, 0, six)


def excerpt_byte_bound(body: str, counts: tuple[int, ...], budget: int) -> int:
    """Bound encoded excerpt contents without reading or sampling the body.

    Sampling takes at most four non-overlapping source windows and three
    separators. JSON encodes each separator (two newlines, brackets, ellipsis)
    as nine bytes. Sum the costliest source characters that fit those windows.
    """
    truncated = len(body) > budget
    source_limit = 4 * max(1, (budget - 3 * len(SEPARATOR)) // 4) if truncated else budget
    remaining = min(len(body), source_limit)
    size = 0
    for width in range(6, 0, -1):
        taken = min(remaining, counts[width-1])
        size += taken * width
        remaining -= taken
    return size + (27 if truncated else 0)
