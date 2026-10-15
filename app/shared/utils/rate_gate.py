"""Token-bucket FPS cheklagich.

RTSP kadrlar tarmoqdan notekis (to'p-to'p) keladi: 20 FPS kamerada ham ikki
kadr orasi 15 ms yoki 90 ms bo'lishi mumkin. "Oxirgi kadrdan beri 1/fps o'tdimi"
degan qattiq tekshiruv bunday to'p kadrlarni tashlab yuboradi (o'lchovda 20 → 12.8
FPS). Token-bucket esa faqat O'RTACHA tezlikni cheklaydi — manba limitdan sekin
bo'lsa hech bir kadr yo'qolmaydi.
"""
from __future__ import annotations


class RateGate:
    __slots__ = ("rate", "burst", "_tokens", "_ts")

    def __init__(self, fps: float, burst: float = 2.0):
        self.rate = max(0.1, float(fps))
        self.burst = max(1.0, float(burst))
        self._tokens = self.burst
        self._ts: float | None = None

    def _refill(self, now: float) -> None:
        if self._ts is not None:
            self._tokens = min(self.burst, self._tokens + (now - self._ts) * self.rate)
        self._ts = now

    def ready(self, now: float) -> bool:
        """Token bormi (olmaydi)."""
        self._refill(now)
        return self._tokens >= 1.0

    def try_take(self, now: float) -> bool:
        """Token bo'lsa oladi va True qaytaradi; aks holda False (kadr o'tkaziladi)."""
        self._refill(now)
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False
