from __future__ import annotations

import pickle
import time
from pathlib import Path

import cv2
import numpy as np

from app.domain.entities import FaceIdentity

_MODELS_DIR = Path(__file__).resolve().parents[3] / "app" / "models"
_YUNET_PATH  = _MODELS_DIR / "yunet.onnx"
_SFACE_PATH  = _MODELS_DIR / "sface.onnx"


class FaceIdService:
    """
    YuNet face detector + SFace 128-dim neural embeddings + cosine similarity.
    Falls back to Haar cascade + CLAHE-64 if ONNX models are missing.
    """

    MODEL_VERSION = "sface-128-v1"

    def __init__(self, db, cfg, threshold: float | None = None):
        self.db  = db
        self.cfg = cfg
        self.threshold = float(
            threshold if threshold is not None else cfg.get("faceid_threshold", 0.30)
        )
        self._use_neural = _YUNET_PATH.exists() and _SFACE_PATH.exists()
        if self._use_neural:
            self._detector   = self._load_yunet()
            self._recognizer = self._load_sface()
        else:
            self._cascade = self._load_cascade()
            self._clahe   = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))

        self._cache: list[tuple[str, str, np.ndarray]] = []
        self._cache_loaded = False

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
        enrolled = 0
        for user in self.cfg.get_users():
            if not user.get("active", True):
                continue
            employee_id = str(user.get("employee_id", "")).strip()
            photo_path  = str(user.get("photo_path",  "")).strip()
            if not employee_id or not photo_path:
                continue
            if self.db.get_face_embedding(employee_id, self.MODEL_VERSION) is not None:
                continue
            try:
                self.enroll_employee(
                    employee_id=employee_id,
                    employee_name=f"{user.get('first_name','')} {user.get('last_name','')}".strip(),
                    photo_path=photo_path,
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
        photo_path: str,
        department_id: int | None = None,
    ) -> None:
        image = cv2.imread(str(photo_path))
        if image is None:
            raise ValueError("FaceID enrollment: rasm ochilmadi")
        emb = self._get_embedding(image)
        if emb is None:
            raise ValueError("FaceID enrollment: rasmda yuz topilmadi")
        self.db.upsert_employee(
            employee_id=employee_id,
            first_name=employee_name.split(" ", 1)[0] if employee_name else "",
            last_name=employee_name.split(" ", 1)[1] if " " in employee_name else "",
            photo_path=photo_path,
            department_id=department_id,
            active=True,
        )
        self.db.upsert_face_embedding(
            employee_id=employee_id,
            model_version=self.MODEL_VERSION,
            embedding=pickle.dumps(emb.astype(np.float32), protocol=pickle.HIGHEST_PROTOCOL),
            created_at=int(time.time()),
        )
        self._cache_loaded = False

    # ── Moslik tekshirish ────────────────────────────────────────────────

    def match_person_crop(self, frame: np.ndarray) -> FaceIdentity | None:
        emb = self._get_embedding(frame)
        if emb is None:
            return None
        self._ensure_cache()
        if not self._cache:
            return None

        best: tuple[str, str, float] | None = None
        for employee_id, employee_name, known in self._cache:
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

    def _sface_embedding(self, image: np.ndarray) -> np.ndarray | None:
        if image is None or image.size == 0:
            return None
        if image.ndim == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        h, w = image.shape[:2]
        self._detector.setInputSize((w, h))
        _, faces = self._detector.detect(image)
        if faces is None or len(faces) == 0:
            return None
        # Eng katta yuz
        face = max(faces, key=lambda f: f[2] * f[3])
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

    def _extract_face(self, image: np.ndarray) -> np.ndarray | None:
        if image is None or image.size == 0 or not hasattr(self, "_cascade") or self._cascade is None:
            return None
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image.copy()
        faces = self._cascade.detectMultiScale(gray, scaleFactor=1.05, minNeighbors=3, minSize=(24, 24))
        if len(faces) == 0:
            faces = self._cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=2, minSize=(20, 20))
        if len(faces) == 0:
            return None
        x, y, w, h = max(faces, key=lambda b: b[2] * b[3])
        pad = int(min(w, h) * 0.10)
        ih, iw = gray.shape[:2]
        return gray[max(0,y-pad):min(ih,y+h+pad), max(0,x-pad):min(iw,x+w+pad)]

    # ── Cache ────────────────────────────────────────────────────────────

    def _ensure_cache(self) -> None:
        if self._cache_loaded:
            return
        rows = self.db.get_face_embeddings(self.MODEL_VERSION)
        cache = []
        for row in rows:
            try:
                emb  = pickle.loads(row["embedding"])
                user = self.db.get_employee_by_employee_id(row["employee_id"]) or {}
                name = f"{user.get('first_name','')} {user.get('last_name','')}".strip()
                cache.append((str(row["employee_id"]), name or str(row["employee_id"]), emb.astype(np.float32)))
            except Exception:
                continue
        self._cache = cache
        self._cache_loaded = True
