"""
QSS yuklash va token almashtirish.

QSS fayllar `qss/` papkasida joylashadi. Ulardagi `{{token_name}}` shabloni
joriy mavzudagi rang qiymati bilan almashtiriladi.

Misol:
    qss/base.qss ichida: `background: {{bg_main}};`
    Light mode'da → `background: #f4faf2;`
    Dark mode'da  → `background: #03070b;`
"""
from __future__ import annotations

import re
from pathlib import Path

from app.ui.styles.tokens import active_palette


_QSS_DIR = Path(__file__).resolve().parent / "qss"
_TOKEN_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


def _substitute(qss: str, tokens: dict[str, str]) -> str:
    """`{{token}}` shabloni qiymat bilan almashtiriladi."""
    def repl(match: re.Match) -> str:
        key = match.group(1)
        return tokens.get(key, match.group(0))
    return _TOKEN_RE.sub(repl, qss)


def load_qss(name: str) -> str:
    """qss/{name}.qss faylni o'qib, joriy mavzu tokenlari bilan to'ldiradi."""
    path = _QSS_DIR / f"{name}.qss"
    if not path.exists():
        return ""
    raw = path.read_text(encoding="utf-8")
    return _substitute(raw, active_palette())


def build_main_stylesheet() -> str:
    """Asosiy QSS — barcha QSS fayllarni birlashtirib qaytaradi.

    Fayl tartibi muhim — keyingilari oldingilarini override qiladi.
    """
    parts: list[str] = []
    # Tartib: global → komponentlar → maxsus
    for name in ("base", "inputs", "buttons", "lists", "misc", "cameras"):
        chunk = load_qss(name)
        if chunk:
            parts.append(chunk)
    return "\n\n".join(parts)
