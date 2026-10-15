"""
Og'ir ishni (DB so'rovi, disk o'qish) GUI thread'dan tashqarida bajarish.

    run_async(self, self._query, self._apply)

`fn` QThreadPool'da ishlaydi, natija `on_done(result)` ga GUI thread'da keladi.
Xato bo'lsa `on_error(exc)` chaqiriladi (berilmagan bo'lsa log'ga yoziladi).
`owner` o'chirilgan bo'lsa, natija tashlab yuboriladi.

Eslatma: `fn` ichida QPixmap/QWidget yaratmang — faqat QImage va oddiy ma'lumot.
ViolationsDB thread-local ulanish ishlatadi, shuning uchun uni fondan chaqirish xavfsiz.
"""

import logging

from PyQt6 import sip
from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal

_log = logging.getLogger(__name__)
_pending: set = set()          # natija kelguncha bridge'lar GC'dan saqlanadi


class _Bridge(QObject):
    done = pyqtSignal(object)
    failed = pyqtSignal(object)


class _Task(QRunnable):
    def __init__(self, fn, bridge: _Bridge):
        super().__init__()
        self._fn = fn
        self._bridge = bridge

    def run(self):
        try:
            res = self._fn()
        except Exception as e:          # noqa: BLE001 — xato GUI thread'ga uzatiladi
            self._bridge.failed.emit(e)
        else:
            self._bridge.done.emit(res)


def run_async(owner: QObject, fn, on_done, on_error=None) -> None:
    bridge = _Bridge()             # GUI thread'da yaratiladi → slotlar GUI thread'da ishlaydi
    _pending.add(bridge)

    def _finish(cb, value):
        _pending.discard(bridge)
        bridge.deleteLater()
        if sip.isdeleted(owner):
            return
        if cb is not None:
            cb(value)
        elif isinstance(value, BaseException):
            _log.error("Fon vazifasida xato: %s", value, exc_info=value)

    bridge.done.connect(lambda r: _finish(on_done, r))
    bridge.failed.connect(lambda e: _finish(on_error, e))
    QThreadPool.globalInstance().start(_Task(fn, bridge))
