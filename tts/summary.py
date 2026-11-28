"""Turn the agent's answer into a short, speakable summary (~15 s or less).

Speech runs ~2.5-3 words/s, so 40 words is about 15 s.
"""
from __future__ import annotations

import re

MAX_WORDS = 40


def clean_for_speech(text: str) -> str:
    """Strip citation markers, URLs, markdown and table pipes."""
    text = re.sub(r"\[\d+\]", "", text)                  # [1] markers
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[*_`#>|]+", " ", text)
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def split_sentences(text: str) -> list:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def fit_to_limit(text: str, max_words: int = MAX_WORDS) -> str:
    """Keep whole sentences up to max_words; hard-trim the first if it is too long."""
    kept, n = [], 0
    for s in split_sentences(text):
        w = len(s.split())
        if n + w > max_words:
            break
        kept.append(s)
        n += w
    if kept:
        return " ".join(kept)
    words = text.split()[:max_words]
    return " ".join(words).rstrip(",;:") + ("." if words else "")


def build_spoken_summary(spoken_summary: str = "", final_answer: str = "",
                         clarification_question: str = "", max_words: int = MAX_WORDS) -> str:
    """Prefer the Answerer's spoken_summary, then the start of final_answer (which also covers
    refusals), then the Router's clarification_question."""
    src = clean_for_speech(spoken_summary or final_answer or clarification_question or "")
    return fit_to_limit(src, max_words) if src else ""
