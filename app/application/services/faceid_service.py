from __future__ import annotations

import os
import pickle
import re
import shutil
import time
from pathlib import Path

import cv2
import numpy as np

from app.domain.entities import FaceIdentity
from app.shared.paths import data_path, resource_path

_MODELS_DIR = resource_path("app", "models")
_YUNET_PATH  = _MODELS_DIR / "yunet.onnx"
_SFACE_PATH  = _MODELS_DIR / "sface.onnx"

# SFace cosine chegarasi: OpenCV tavsiyasi 0.363. Kamera kadrida (siqilgan,
# burchak ostida) bir odamning o'xshashligi odatda 0.40–0.60 bo'ladi.
DEFAULT_THRESHOLD = 0.42
# Bundan kichik yuzlar (asl kadrda, piksel) umuman ishlatilmaydi. 24–40 px yuzlar
# faqat bir necha kadr birlashtirilganda (TrackIdentity) qaror uchun ishlatiladi.
DEFAULT_MIN_FACE_PX = 24
# Kesim shundan kichik bo'lsa, yuz qidirishdan oldin 2x kattalashtiriladi
# (YuNet kichik yuzlarni kattalashtirilgan kesimda ancha yaxshi topadi).
_UPSCALE_BELOW_PX = 360


def user_photo_paths(user: dict) -> list[str]:
    """Xodimning barcha rasmlari: `photo_paths` ro'yxati + eski `photo_path`."""
    paths = [str(p).strip() for p in (user.get("photo_paths") or []) if str(p).strip()]
    main = str(user.get("photo_path", "") or "").strip()
    if main and main not in paths:
        paths.insert(0, main)
    return paths


def _photos_signature(paths: list[str]) -> str:
    """Rasm fayllari o'zgarganini aniqlash uchun imzo (yo'l + o'lcham + vaqt)."""
    parts = []
    for p in paths:
        try:
            st = os.stat(p)
            parts.append(f"{p}:{st.st_size}:{int(st.st_mtime)}")
        except OSError:
            parts.append(f"{p}:missing")
    return "|".join(parts)


def store_employee_photos(employee_id: str, src_paths: list[str]) -> list[str]:
    """
    Rasmlarni ilova papkasiga (DATA_DIR/faces/<ID>/) ko'chiradi — asl fayl
    o'chirilsa yoki boshqa kompyuterga o'tkazilsa ham FaceID ishlayveradi.
    Allaqachon shu papkada turgan rasmlar qayta ko'chirilmaydi.
    """
    safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(employee_id)).strip("._") or "xodim"
    dest_dir = data_path("faces", safe_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    stored = []
    stamp = time.strftime("%Y%m%d_%H%M%S")
    for i, src in enumerate(src_paths, 1):
        src_p = Path(src)
        if not src_p.is_file():
            continue
        try:
            if src_p.resolve().parent == dest_dir.resolve():
                stored.append(str(src_p))
                continue
        except OSError:
            pass
        dest = dest_dir / f"{stamp}_{i}{src_p.suffix.lower() or '.jpg'}"
        shutil.copy2(src_p, dest)
        stored.append(str(dest))
    return stored


_PHOTO_DETECTOR = None


def photos_with_face(paths: list[str], min_face_px: int = DEFAULT_MIN_FACE_PX) -> list[bool]:
    """Har bir rasmda tanish uchun yaroqli yuz bormi (UI da darhol tekshirish uchun)."""
    global _PHOTO_DETECTOR
    if not _YUNET_PATH.exists():
        return [Path(p).is_file() for p in paths]  # tekshirib bo'lmaydi — faqat mavjudligi
    if _PHOTO_DETECTOR is None:
        _PHOTO_DETECTOR = cv2.FaceDetectorYN.create(str(_YUNET_PATH), "", (320, 320), 0.6, 0.3, 50)
    result = []
    for p in paths:
        img = cv2.imread(str(p))
        if img is None:
            result.append(False)
            continue
        h, w = img.shape[:2]
        _PHOTO_DETECTOR.setInputSize((w, h))
        _, faces = _PHOTO_DETECTOR.detect(img)
        result.append(faces is not None and any(min(f[2], f[3]) >= min_face_px for f in faces))
    return result


class FaceIdService:
    """
    YuNet face detector + SFace 128-dim neural embeddings + cosine similarity.
    Falls back to Haar cascade + CLAHE-64 if ONNX models are missing.

    Xodimda bir nechta rasm bo'lsa, ularning embeddinglari o'rtachalanadi
    (bitta rasmdan ko'ra barqaror). Rasm almashtirilsa embedding avtomatik
    qayta hisoblanadi.
    """

    MODEL_VERSION = "sface-128-v1"
    HAAR_MODEL_VERSION = "haar-64-v1"

    def __init__(self, db, cfg, threshold: float | None = None):
        self.db  = db
        self.cfg = cfg
        self.threshold = float(
            threshold if threshold is not None else cfg.get("faceid_threshold", DEFAULT_THRESHOLD)
        )
        self.min_face_px = int(cfg.get("faceid_min_face_px", DEFAULT_MIN_FACE_PX))
        self._use_neural = _YUNET_PATH.exists() and _SFACE_PATH.exists()
        if self._use_neural:
            self._detector   = self._load_yunet()
            self._recognizer = self._load_sface()
            self.model_version = self.MODEL_VERSION
        else:
            self._cascade = self._load_cascade()
            self._clahe   = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
            # Boshqa o'lchamdagi vektorlar SFace bilan aralashmasin
            self.model_version = self.HAAR_MODEL_VERSION

        self._cache: list[tuple[str, str, np.ndarray]] = []
        self._cache_loaded = False
        self._cached_active: set[str] | None = None
        self._last_sync = time.monotonic()

    SYNC_INTERVAL = 30.0

    def _sync_if_due(self) -> None:
        """
        Xodimlar ro'yxati o'zgargan bo'lsa (qo'shildi, rasm almashdi, o'chirildi)
        kamera qayta ishga tushmasdan ham yangilanadi.
        """
        now = time.monotonic()
        if now - self._last_sync < self.SYNC_INTERVAL:
            return
        self._last_sync = now
        try:
            if self.enroll_from_settings_users() or self._active_employee_ids() != self._cached_active:
                self._cache_loaded = False
        except Exception:
            pass

    # ── Model yuklash ────────────────────────────────────────────────────

    @staticmethod
    def _load_yunet():
        det = cv2.FaceDetectorYN.create(
            str(_YUNET_PATH), "", (320, 320),
            score_threshold=0.60,
            nms_threshold=0.30,
            top_k=200,
        )
        return det

    @staticmethod
    def _load_sface():
        return cv2.FaceRecognizerSF.create(str(_SFACE_PATH), "")

    @staticmethod
    def _load_cascade():
        path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        c = cv2.CascadeClassifier(str(path))
        return c if not c.empty() else None

    # ── Ro'yxatga olish ──────────────────────────────────────────────────

    def enroll_from_settings_users(self) -> int:
        """
        Faol xodimlarni ro'yxatga oladi. Rasmlari o'zgarmagan xodim qayta
        hisoblanmaydi; rasm almashtirilgan yoki qo'shilgan bo'lsa yangilanadi.
        """
        enrolled = 0
        for user in self.cfg.get_users():
            if not user.get("active", True):
                continue
            employee_id = str(user.get("employee_id", "")).strip()
            photos = user_photo_paths(user)
            if not employee_id or not photos:
                continue
            sig = _photos_signature(photos)
            existing = self.db.get_face_embedding(employee_id, self.model_version)
            if existing is not None and (existing.get("source_sig") or "") == sig:
                continue
            try:
                self.enroll_employee(
                    employee_id=employee_id,
                    employee_name=f"{user.get('first_name','')} {user.get('last_name','')}".strip(),
                    photo_paths=photos,
                    department_id=user.get("department_id"),
                )
                enrolled += 1
            except ValueError:
                continue
        if enrolled:
            self._cache_loaded = False
        return enrolled

    def enroll_employee(
        self,
        *,
        employee_id: str,
        employee_name: str,
        photo_path: str = "",
        photo_paths: list[str] | None = None,
        department_id: int | None = None,
    ) -> int:
        """Rasm(lar)dan embedding hisoblab saqlaydi. Yuz topilgan rasmlar sonini qaytaradi."""
        paths = list(photo_paths or ([photo_path] if photo_path else []))
        embs = []
        for p in paths:
            image = cv2.imread(str(p))
            if image is None:
                continue
            emb = self._get_embedding(image)
            if emb is not None:
                embs.append(emb / (np.linalg.norm(emb) + 1e-8))
        if not embs:
            raise ValueError("FaceID enrollment: rasm(lar)da yuz topilmadi")
        mean = np.mean(embs, axis=0)
        mean = mean / (np.linalg.norm(mean) + 1e-8)
        self.db.upsert_employee(
            employee_id=employee_id,
            first_name=employee_name.split(" ", 1)[0] if employee_name else "",
            last_name=employee_name.split(" ", 1)[1] if " " in employee_name else "",
            photo_path=paths[0],
            department_id=department_id,
            active=True,
        )
        self.db.upsert_face_embedding(
            employee_id=employee_id,
            model_version=self.model_version,
            embedding=pickle.dumps(mean.astype(np.float32), protocol=pickle.HIGHEST_PROTOCOL),
            created_at=int(time.time()),
            source_sig=_photos_signature(paths),
        )
        self._cache_loaded = False
        return len(embs)

    # ── Moslik tekshirish ────────────────────────────────────────────────

    def has_face(self, image: np.ndarray) -> bool:
        """Rasmda tanish uchun yetarli o'lchamdagi yuz bormi (joriy detektor bilan)."""
        return self._detect_face(image) is not None

    def analyze(self, crop: np.ndarray) -> dict | None:
        """
        Odam kesimidan yuzni topadi: {"emb", "quality" (0..1), "face_px"}.
        Avval yuqori qism (bosh odatda shu yerda), topilmasa butun kesim.
        Juda burilgan yoki topilmagan yuz — None.
        """
        if crop is None or crop.size == 0:
            return None
        h = crop.shape[0]
        for region in (crop[:max(32, int(h * 0.45)), :], crop):
            sample = self._analyze_region(region)
            if sample is not None:
                return sample
        return None

    def match_person_crop(self, frame: np.ndarray) -> FaceIdentity | None:
        """Bitta kadr bo'yicha eng o'xshash xodim (kirish ro'yxati tekshiruvi uchun)."""
        sample = self.analyze(frame)
        return self.match_embedding(sample["emb"]) if sample else None

    def match_embedding(self, emb: np.ndarray) -> FaceIdentity | None:
        self._sync_if_due()
        self._ensure_cache()
        if not self._cache:
            return None

        best: tuple[str, str, float] | None = None
        for employee_id, employee_name, known in self._cache:
            if known.shape != emb.shape:
                continue
            cos_sim = float(np.dot(emb, known) / (
                np.linalg.norm(emb) * np.linalg.norm(known) + 1e-8
            ))
            confidence = max(0.0, min(1.0, cos_sim))
            if best is None or confidence > best[2]:
                best = (employee_id, employee_name, confidence)

        if best is None:
            return None
        employee_id, employee_name, confidence = best
        return FaceIdentity(
            employee_id=employee_id,
            employee_name=employee_name,
            confidence=confidence,
            matched=confidence >= self.threshold,
        )

    # ── Embedding olish ──────────────────────────────────────────────────

    def _get_embedding(self, image: np.ndarray) -> np.ndarray | None:
        sample = self._analyze_region(image)
        return sample["emb"] if sample else None

    def _analyze_region(self, image: np.ndarray) -> dict | None:
        if image is None or image.size == 0:
            return None
        if not self._use_neural:
            emb = self._haar_embedding(image)
            return {"emb": emb, "quality": 0.5, "face_px": 0.0} if emb is not None else None
        if image.ndim == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        scale = 1.0
        if max(image.shape[:2]) < _UPSCALE_BELOW_PX:
            scale = 2.0
            image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        face = self._detect_face(image, scale)
        if face is None:
            return None
        aligned = self._recognizer.alignCrop(image, face)
        quality = self._quality(face, aligned, scale)
        if quality <= 0.0:
            return None
        emb = self._recognizer.feature(aligned).flatten().astype(np.float32)
        emb /= (np.linalg.norm(emb) + 1e-8)
        return {"emb": emb, "quality": quality, "face_px": float(face[2]) / scale}

    @staticmethod
    def _quality(face, aligned: np.ndarray, scale: float) -> float:
        """
        Arzon sifat bahosi (0..1): yuz o'lchami x tiniqlik x bosh burilishi x detektor ishonchi.
        Bosh ~35° dan ko'p burilgan bo'lsa 0 (ishlatilmaydi).
        """
        face_px = float(face[2]) / scale
        size_q = min(1.0, max(0.15, (face_px - 20.0) / 40.0))
        gray = cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY) if aligned.ndim == 3 else aligned
        sharp_q = min(1.0, max(0.1, cv2.Laplacian(gray, cv2.CV_64F).var() / 120.0))
        re_, le_, nose = face[4:6], face[6:8], face[8:10]
        eye_d = float(np.linalg.norm(re_ - le_)) or 1.0
        yaw = abs(float(nose[0]) - float(re_[0] + le_[0]) / 2.0) / eye_d
        yaw_q = max(0.0, 1.0 - yaw / 0.6)
        det_q = min(1.0, max(0.0, float(face[14])))
        return size_q * sharp_q * yaw_q * det_q

    def _detect_face(self, image: np.ndarray, scale: float = 1.0):
        """Eng katta yuz: neural'da YuNet qatori, Haar'da (x, y, w, h). Kichik bo'lsa None.
        `scale` — rasm asl kadrga nisbatan necha marta kattalashtirilgan (o'lcham asl kadrda o'lchanadi)."""
        if image is None or image.size == 0:
            return None
        if self._use_neural:
            if image.ndim == 2:
                image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
            h, w = image.shape[:2]
            self._detector.setInputSize((w, h))
            _, faces = self._detector.detect(image)
            if faces is None or len(faces) == 0:
                return None
            face = max(faces, key=lambda f: f[2] * f[3])
            if min(face[2], face[3]) / scale < self.min_face_px:
                return None
            return face
        box = self._haar_box(image)
        if box is None or min(box[2], box[3]) < min(self.min_face_px, 24):
            return None
        return box

    def _haar_embedding(self, image: np.ndarray) -> np.ndarray | None:
        face = self._extract_face(image)
        if face is None:
            return None
        resized = cv2.resize(face, (64, 64), interpolation=cv2.INTER_LANCZOS4)
        eq = self._clahe.apply(resized)
        blurred = cv2.GaussianBlur(eq, (3, 3), 0)
        vec = blurred.astype(np.float32).reshape(-1) / 255.0
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec

    def _haar_box(self, image: np.ndarray):
        if image is None or image.size == 0 or getattr(self, "_cascade", None) is None:
            return None
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        faces = self._cascade.detectMultiScale(gray, scaleFactor=1.05, minNeighbors=3, minSize=(24, 24))
        if len(faces) == 0:
            faces = self._cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=2, minSize=(20, 20))
        if len(faces) == 0:
            return None
        return max(faces, key=lambda b: b[2] * b[3])

    def _extract_face(self, image: np.ndarray) -> np.ndarray | None:
        box = self._haar_box(image)
        if box is None:
            return None
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        x, y, w, h = box
        pad = int(min(w, h) * 0.10)
        ih, iw = gray.shape[:2]
        return gray[max(0,y-pad):min(ih,y+h+pad), max(0,x-pad):min(iw,x+w+pad)]

    # ── Cache ────────────────────────────────────────────────────────────

    def _active_employee_ids(self) -> set[str] | None:
        try:
            return {
                str(u.get("employee_id", "")).strip()
                for u in self.cfg.get_users()
                if u.get("active", True) and str(u.get("employee_id", "")).strip()
            }
        except Exception:
            return None

    def _ensure_cache(self) -> None:
        if self._cache_loaded:
            return
        # O'chirilgan / nofaol xodimlar bazada qolgan bo'lsa ham tanilmasin
        active = self._active_employee_ids()
        rows = self.db.get_face_embeddings(self.model_version)
        cache = []
        for row in rows:
            if active is not None and str(row["employee_id"]) not in active:
                continue
            try:
                emb  = pickle.loads(row["embedding"])
                user = self.db.get_employee_by_employee_id(row["employee_id"]) or {}
                name = f"{user.get('first_name','')} {user.get('last_name','')}".strip()
                cache.append((str(row["employee_id"]), name or str(row["employee_id"]), emb.astype(np.float32)))
            except Exception:
                continue
        self._cache = cache
        self._cached_active = active
        self._cache_loaded = True


class TrackIdentity:
    """
    Kuzatilayotgan odam (track) bo'yicha yuzlarni yig'ib qaror qiladi.

    Uzoq kamerada bitta kadrdagi 25–40 px yuz ishonchsiz; odam kadrda bir necha
    soniya turadi, shuning uchun eng yaxshi K ta kadr embeddingi sifat bo'yicha
    o'rtachalanadi va shundan keyin xodim bilan solishtiriladi.
    Yengil: faqat kerakli track'lar uchun, xodim aniqlangach to'xtaydi.
    """

    TOP_K = 6          # saqlanadigan eng yaxshi kadrlar
    MIN_FRAMES = 3     # oddiy holatda qaror uchun kamida shuncha kadr
    STRONG_PX = 60     # shunchalik katta va tiniq yuz — bitta kadr ham yetadi
    STRONG_Q = 0.5
    TTL = 120.0        # shuncha soniya ko'rinmagan track unutiladi

    def __init__(self, service: FaceIdService):
        self.service = service
        self._tracks: dict[int, dict] = {}
        self._last_prune = time.monotonic()

    def identity(self, track_id: int) -> FaceIdentity | None:
        """Aniqlangan xodim (matched) yoki None."""
        st = self._tracks.get(track_id)
        return st["ident"] if st and st["ident"] is not None and st["ident"].matched else None

    def add(self, track_id: int, sample: dict) -> FaceIdentity | None:
        """
        Yangi yuz namunasini qo'shadi. Qaror chiqsa (birinchi marta tanilsa yoki
        yetarli kadrdan keyin ham noma'lum bo'lsa) FaceIdentity qaytaradi, aks holda None.
        """
        now = time.monotonic()
        self._prune(now)
        st = self._tracks.setdefault(track_id, {"samples": [], "ident": None,
                                                "unknown_reported": False, "seen": now})
        st["seen"] = now
        if st["ident"] is not None and st["ident"].matched:
            return None
        samples = st["samples"]
        samples.append((float(sample["quality"]), sample["emb"]))
        samples.sort(key=lambda x: x[0], reverse=True)
        del samples[self.TOP_K:]

        strong = sample.get("face_px", 0) >= self.STRONG_PX and sample["quality"] >= self.STRONG_Q
        if len(samples) < self.MIN_FRAMES and not strong:
            return None
        weights = np.array([q for q, _ in samples], dtype=np.float32)
        agg = (np.stack([e for _, e in samples]) * weights[:, None]).sum(axis=0)
        agg /= (np.linalg.norm(agg) + 1e-8)
        ident = self.service.match_embedding(agg)
        if ident is None:
            return None
        if ident.matched:
            st["ident"] = ident
            return ident
        # Yetarli kadr to'plandi, lekin hech kimga o'xshamadi — bir marta "noma'lum" deb xabar
        if len(samples) >= self.MIN_FRAMES + 2 and not st["unknown_reported"]:
            st["unknown_reported"] = True
            return ident
        return None

    def _prune(self, now: float) -> None:
        if now - self._last_prune < 30.0:
            return
        self._last_prune = now
        for tid in [t for t, st in self._tracks.items() if now - st["seen"] > self.TTL]:
            del self._tracks[tid]


def save_face_sample(employee_id: str, image_path: str) -> str | None:
    """
    Kamera kadridagi (buzilish rasmidagi) yuzni kesib, xodimga namuna sifatida saqlaydi.
    Namuna shu kamera sharoitida (masofa, xiralik) olingani uchun tanishni oshiradi.
    """
    img = cv2.imread(str(image_path))
    if img is None or not _YUNET_PATH.exists():
        return None
    scale = 2.0 if max(img.shape[:2]) < _UPSCALE_BELOW_PX else 1.0
    big = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC) if scale > 1 else img
    det = cv2.FaceDetectorYN.create(str(_YUNET_PATH), "", (big.shape[1], big.shape[0]), 0.6, 0.3, 50)
    _, faces = det.detect(big)
    if faces is None or len(faces) == 0:
        return None
    x, y, w, h = [float(v) for v in max(faces, key=lambda f: f[2] * f[3])[:4]]
    if min(w, h) / scale < 16:
        return None
    m = 0.45  # yuz atrofida hoshiya — alignment uchun
    x0, y0 = int(max(0, x - w * m)), int(max(0, y - h * m))
    x1, y1 = int(min(big.shape[1], x + w * (1 + m))), int(min(big.shape[0], y + h * (1 + m)))
    face = big[y0:y1, x0:x1]
    if face.shape[0] < 160:
        k = 160.0 / face.shape[0]
        face = cv2.resize(face, None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC)
    tmp = data_path("faces", f"_sample_{int(time.time() * 1000)}.jpg")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(tmp), face, [cv2.IMWRITE_JPEG_QUALITY, 95])
    try:
        stored = store_employee_photos(employee_id, [str(tmp)])
    finally:
        tmp.unlink(missing_ok=True)
    return stored[0] if stored else None
