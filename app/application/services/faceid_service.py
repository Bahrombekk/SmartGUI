from __future__ import annotations

import pickle
import time
from pathlib import Path

import cv2
import numpy as np

from app.domain.entities import FaceIdentity


class FaceIdService:
    """
    Lightweight local FaceID foundation.

    It validates that an enrollment image contains a face, stores a compact
    grayscale embedding, and performs nearest-neighbor matching. This keeps the
    app offline-first and dependency-light; a stronger face model can replace
    `_embedding_from_face` without changing callers.
    """

    MODEL_VERSION = "opencv-gray-32-v1"

    def __init__(self, db, cfg, threshold: float | None = None):
        self.db = db
        self.cfg = cfg
        self.threshold = float(threshold if threshold is not None else cfg.get("faceid_threshold", 0.72))
        self._cascade = self._load_cascade()
        self._cache: list[tuple[str, str, np.ndarray]] = []
        self._cache_loaded = False

    @staticmethod
    def _load_cascade():
        path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        cascade = cv2.CascadeClassifier(str(path))
        return cascade if not cascade.empty() else None

    def enroll_from_settings_users(self) -> int:
        enrolled = 0
        for user in self.cfg.get_users():
            if not user.get("active", True):
                continue
            employee_id = str(user.get("employee_id", "")).strip()
            photo_path = str(user.get("photo_path", "")).strip()
            if not employee_id or not photo_path:
                continue
            if self.db.get_face_embedding(employee_id, self.MODEL_VERSION) is not None:
                continue
            try:
                self.enroll_employee(
                    employee_id=employee_id,
                    employee_name=f"{user.get('first_name', '')} {user.get('last_name', '')}".strip(),
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
        face = self._extract_face(image)
        if face is None:
            raise ValueError("FaceID enrollment: rasmda yuz topilmadi")
        emb = self._embedding_from_face(face)
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

    def match_person_crop(self, frame: np.ndarray) -> FaceIdentity | None:
        face = self._extract_face(frame)
        if face is None:
            return None
        embedding = self._embedding_from_face(face)
        self._ensure_cache()
        if not self._cache:
            return None

        best: tuple[str, str, float] | None = None
        for employee_id, employee_name, known in self._cache:
            distance = float(np.linalg.norm(embedding - known))
            confidence = max(0.0, min(1.0, 1.0 - distance / 2.0))
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

    def _ensure_cache(self) -> None:
        if self._cache_loaded:
            return
        rows = self.db.get_face_embeddings(self.MODEL_VERSION)
        cache = []
        for row in rows:
            try:
                emb = pickle.loads(row["embedding"])
                user = self.db.get_employee_by_employee_id(row["employee_id"]) or {}
                name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
                cache.append((str(row["employee_id"]), name or str(row["employee_id"]), emb.astype(np.float32)))
            except Exception:
                continue
        self._cache = cache
        self._cache_loaded = True

    def _extract_face(self, image: np.ndarray) -> np.ndarray | None:
        if image is None or image.size == 0 or self._cascade is None:
            return None
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        faces = self._cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(32, 32))
        if len(faces) == 0:
            return None
        x, y, w, h = max(faces, key=lambda b: b[2] * b[3])
        return gray[y:y + h, x:x + w]

    @staticmethod
    def _embedding_from_face(face: np.ndarray) -> np.ndarray:
        resized = cv2.resize(face, (32, 32), interpolation=cv2.INTER_AREA)
        vec = resized.astype(np.float32).reshape(-1) / 255.0
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec
