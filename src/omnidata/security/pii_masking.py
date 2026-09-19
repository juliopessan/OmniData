"""Mask PII before ANY text reaches an LLM (NFR 'PII to LLM'). Regex-based, unit-tested."""
from __future__ import annotations

import re

_CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
_CNPJ = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE = re.compile(r"(?<!\w)(?:\+?55\s?)?(?:\(?\d{2}\)?\s?)?9?\d{4}[-\s]?\d{4}(?!\w)")


def mask_pii(text: str) -> str:
    # CNPJ before CPF (longer first), then e-mail, then phone.
    text = _CNPJ.sub("[CNPJ]", text)
    text = _CPF.sub("[CPF]", text)
    text = _EMAIL.sub("[EMAIL]", text)
    return _PHONE.sub("[TEL]", text)
