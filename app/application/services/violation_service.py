from __future__ import annotations

import time

import numpy as np

from app.domain.entities import ViolationEvent
from app.infrastructure.notifications.notification_dispatcher import (
    NotificationDispatcher,
)
from app.infrastructure.persistence.file_storage import ViolationFileStorage
from app.infrastructure.persistence.sqlite_db import ViolationsDB


class ViolationService:
    """Registers violations, stores evidence, and fans out notifications."""

    def __init__(
        self,
        db: ViolationsDB,
        file_storage: ViolationFileStorage | None = None,
        dispatcher: NotificationDispatcher | None = None,
    ):
        self.db = db
        self.file_storage = file_storage or ViolationFileStorage()
        self.dispatcher = dispatcher or NotificationDispatcher()

    def register_violation(
        self,
        *,
        frame: np.ndarray,
        person: dict,
        camera_name: str,
        company_id: str,
        violations_dir,
        save_files: bool,
        notifier=None,
        backend=None,
    ) -> ViolationEvent:
        track_id = int(person.get("track_id", -1))
        timestamp = int(time.time())
        box = person.get("box", [])
        confidence = float(person.get("score", 0.0))

        crop_path, full_path, crop_frame = self.file_storage.save_violation_images(
            frame=frame,
            box=box,
            output_dir=violations_dir,
            track_id=track_id,
            timestamp=timestamp,
            enabled=save_files,
        )

        self.db.add_violation(
            track_id=track_id,
            crop_path=crop_path,
            full_path=full_path,
            camera_name=camera_name,
            confidence=confidence,
            timestamp=timestamp,
        )

        event = ViolationEvent(
            track_id=track_id,
            timestamp=timestamp,
            camera_name=camera_name,
            company_id=company_id,
            confidence=confidence,
            crop_path=crop_path,
            full_path=full_path,
            crop_frame=crop_frame,
        )
        self.dispatcher.dispatch(event, frame, notifier=notifier, backend=backend)
        return event
