"""
RTSP ulanish xatosining sababini aniqlash.

OpenCV/FFmpeg ochilmasa faqat "ochilmadi" deydi. Bu modul kameraga to'g'ridan-to'g'ri
RTSP DESCRIBE so'rovi yuborib, foydalanuvchiga tushunarli sabab qaytaradi:
tarmoq / port / login-parol / oqim yo'li / kodek.

    reason = diagnose("rtsp://admin:123@192.168.1.10:554/Streaming/Channels/101")
    # "Login yoki parol noto'g'ri (401)"
"""
from __future__ import annotations

import base64
import hashlib
import re
import socket
from urllib.parse import unquote, urlsplit

_DEFAULT_PORT = 554


def _read_response(sock: socket.socket) -> tuple[int, dict[str, str]]:
    data = b""
    while b"\r\n\r\n" not in data and len(data) < 16384:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data += chunk
    head = data.split(b"\r\n\r\n", 1)[0].decode("latin-1", "replace")
    lines = head.split("\r\n")
    m = re.match(r"RTSP/\d\.\d\s+(\d{3})", lines[0] if lines else "")
    if not m:
        raise ValueError("RTSP javob emas")
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            key = k.strip().lower()
            # Bir nechta WWW-Authenticate bo'lishi mumkin — Digest ustun
            if key in headers and key == "www-authenticate" and "digest" not in v.lower():
                continue
            headers[key] = v.strip()
    return int(m.group(1)), headers


def _auth_header(challenge: str, user: str, password: str, method: str, uri: str) -> str:
    if challenge.lower().startswith("basic"):
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        return f"Basic {token}"
    params = dict(re.findall(r'(\w+)="?([^",]+)"?', challenge))
    realm, nonce = params.get("realm", ""), params.get("nonce", "")
    ha1 = hashlib.md5(f"{user}:{realm}:{password}".encode()).hexdigest()
    ha2 = hashlib.md5(f"{method}:{uri}".encode()).hexdigest()
    resp = hashlib.md5(f"{ha1}:{nonce}:{ha2}".encode()).hexdigest()
    return (f'Digest username="{user}", realm="{realm}", nonce="{nonce}", '
            f'uri="{uri}", response="{resp}"')


def _describe(sock: socket.socket, uri: str, cseq: int, auth: str):
    req = (f"DESCRIBE {uri} RTSP/1.0\r\nCSeq: {cseq}\r\n"
           "Accept: application/sdp\r\nUser-Agent: SafeZone\r\n")
    if auth:
        req += f"Authorization: {auth}\r\n"
    sock.sendall((req + "\r\n").encode())
    return _read_response(sock)


_REACHABLE_PREFIX = "Kamera javob berdi"


def blocking_reason(url: str, timeout: float = 3.0) -> str | None:
    """
    Ulanishdan OLDIN tezkor tekshiruv: kamera aniq ishlamasa (tarmoq, port,
    login/parol, yo'l) — sababni qaytaradi va uzoq FFmpeg urinishlari keraksiz.
    Kamera javob bersa yoki tekshirib bo'lmasa — None (odatdagi ulanish davom etadi).
    """
    reason = diagnose(url, timeout)
    # Faqat aniq holatlar: ba'zi kameralar DESCRIBE ga nostandart kod qaytaradi,
    # lekin FFmpeg ular bilan ishlaydi — bunday holatda ulanishni to'xtatmaymiz
    definite = ("Manzil topilmadi", "port yopiq", "Kamera javob bermayapti", "Tarmoq xatosi",
                "(401)", "login va parol so'rayapti", "(403)", "(404)")
    if reason and any(key in reason for key in definite):
        return reason
    return None


def diagnose(url: str, timeout: float = 4.0) -> str:
    """Ulanish muvaffaqiyatsiz bo'lganda qisqa sabab (o'zbekcha). Bo'sh satr — sabab topilmadi."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return "RTSP URL noto'g'ri yozilgan"
    if parts.scheme.lower() not in ("rtsp", "rtsps"):
        return ""
    host = parts.hostname
    if not host:
        return "RTSP URL da IP manzil yo'q"
    try:
        port = parts.port or _DEFAULT_PORT
    except ValueError:
        return "RTSP URL dagi port noto'g'ri"
    user = unquote(parts.username or "")
    password = unquote(parts.password or "")
    netloc = host if port == _DEFAULT_PORT else f"{host}:{port}"
    uri = f"rtsp://{netloc}{parts.path or '/'}" + (f"?{parts.query}" if parts.query else "")

    try:
        # Ikkala so'rov bitta ulanishda: kamera nonce'ni ulanishga bog'laydi
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            code, headers = _describe(sock, uri, 1, "")
            if code == 401 and user:
                challenge = headers.get("www-authenticate", "")
                if challenge:
                    code, headers = _describe(
                        sock, uri, 2, _auth_header(challenge, user, password, "DESCRIBE", uri))
    except socket.gaierror:
        return f"Manzil topilmadi: {host}"
    except ConnectionRefusedError:
        return f"Kamera {host} da {port}-port yopiq (RTSP porti to'g'rimi?)"
    except (socket.timeout, TimeoutError):
        return f"Kamera javob bermayapti: {host} (IP va tarmoqni tekshiring)"
    except OSError as exc:
        return f"Tarmoq xatosi: {exc.strerror or exc}"
    except ValueError:
        return f"{host}:{port} RTSP kamera emas (port noto'g'ri bo'lishi mumkin)"

    if code == 200:
        return _REACHABLE_PREFIX + ", lekin video ochilmadi (kodek yoki oqim sozlamasi)"
    if code == 401:
        return ("Login yoki parol noto'g'ri (401)" if user
                else "Kamera login va parol so'rayapti — RTSP URL ga qo'shing")
    if code == 403:
        return "Kameraga kirishga ruxsat yo'q (403)"
    if code == 404:
        return "Oqim yo'li topilmadi (404) — URL oxirini tekshiring"
    if code in (453, 503):
        return f"Kamera band yoki ulanishlar soni to'lgan ({code})"
    return f"Kamera xato qaytardi: RTSP {code}"
