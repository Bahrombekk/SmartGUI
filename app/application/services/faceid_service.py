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
# Bundan kichik yuzlar (piksel) ishonchsiz — tanishga urinilmaydi.
DEFAULT_MIN_FACE_PX = 40


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

    def match_person_crop(self, frame: np.ndarray) -> FaceIdentity | None:
        """
        Odam kesimidan yuzni topib, eng o'xshash xodimni qaytaradi.
        Avval yuqori qism (bosh odatda shu yerda), topilmasa butun kesim.
        """
        if frame is None or frame.size == 0:
            return None
        emb = None
        h = frame.shape[0]
        upper = frame[:max(32, int(h * 0.45)), :]
        for region in (upper, frame):
            emb = self._get_embedding(region)
            if emb is not None:
                break
        if emb is None:
            return None
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
        if self._use_neural:
            return self._sface_embedding(image)
        return self._haar_embedding(image)

    def _detect_face(self, image: np.ndarray):
        """Eng katta yuz: neural'da YuNet qatori, Haar'da (x, y, w, h). Kichik bo'lsa None."""
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
            if min(face[2], face[3]) < self.min_face_px:
                return None
            return face
        box = self._haar_box(image)
        if box is None or min(box[2], box[3]) < min(self.min_face_px, 24):
            return None
        return box

    def _sface_embedding(self, image: np.ndarray) -> np.ndarray | None:
        face = self._detect_face(image)
        if face is None:
            return None
        if image.ndim == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        aligned = self._recognizer.alignCrop(image, face)
        feat = self._recognizer.feature(aligned)
        return feat.flatten().astype(np.float32)

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
