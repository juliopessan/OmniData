"""Deterministic tone signal for humanized replies (never a new LLM call — same reasoning as router.py's keyword route:
cheaper, faster, testable, and it only ever adjusts TONE downstream, never a fact or a number."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_ACK = {"valeu", "vlw", "obrigado", "obrigada", "obg", "blz", "beleza", "ok", "okay", "show", "top",
        "perfeito", "otimo", "otima", "👍", "🙏", "👍🏻", "👍🏼", "👍🏽"}
_NEGATIVE = re.compile(r"\b(pessimo|horrivel|nao funciona|nao esta funcionando|erro grave|quero cancelar|cancelar tudo|"
                       r"reclamacao|muito ruim|um absurdo|isso e um absurdo|nunca mais)\b")
_URGENT = re.compile(r"\b(urgente|urgencia|agora mesmo|preciso agora|correndo|emergencia|rapido por favor)\b")


def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower().strip()) if unicodedata.category(c) != "Mn")


@dataclass(frozen=True)
class Sentiment:
    acknowledgement: bool = False
    negative: bool = False
    urgent: bool = False


def classify(text: str) -> Sentiment:
    t = _norm(text)
    ack = t.strip("!.,; ") in _ACK
    return Sentiment(acknowledgement=ack, negative=bool(_NEGATIVE.search(t)), urgent=bool(_URGENT.search(t)))
