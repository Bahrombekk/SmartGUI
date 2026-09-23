"""RTSP manzillarni ekranda ko'rsatish uchun yordamchilar."""
from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit


def mask_rtsp_password(url: str) -> str:
    """rtsp://admin:parol@host/... -> rtsp://admin:•••@host/... (login qoladi, parol yashiriladi)."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    if not parts.password:
        return url
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    netloc = f"{parts.username}:•••@{host}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
