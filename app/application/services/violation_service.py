from __future__ import annotations

import time

import numpy as np

from app.domain.entities import ViolationEvent
from app.infrastructure.notifications.notification_dispatcher import (
    NotificationDispatcher,
)
from app.infrastructure.persistence.file_storage import ViolationFileStorage
from app.infrastructure.persistence.sqlite_db import ViolationsDB
from app.application.services.notification_queue_service import NotificationQueueService


class ViolationService:
    """Registers violations, stores evidence, and fans out notifications."""

    def __init__(
        self,
        db: ViolationsDB,
        file_storage: ViolationFileStorage | None = None,
        dispatcher: NotificationDispatcher | None = None,
        notification_queue: NotificationQueueService | None = None,
    ):
        self.db = db
        self.file_storage = file_storage or ViolationFileStorage()
        self.dispatcher = dispatcher or NotificationDispatcher()
        self.notification_queue = notification_queue or NotificationQueueService(db)

    def register_violation(
        self,
        *,
        frame: np.ndarray,
        person: dict,
        camera_name: str,
        company_id: str,
        violations_dir,
        save_files: bool,
        violation_type: str = "no_helmet",
        camera_id: int | None = None,
        department_id: int | None = None,
        employee_id: str | None = None,
        employee_name: str = "",
        identity_confidence: float = 0.0,
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
            violation_type=violation_type,
            camera_id=camera_id,
            department_id=department_id,
            employee_id=employee_id,
            employee_name=employee_name,
            identity_confidence=identity_confidence,
            sync_status="queued" if (notifier or backend) else "local",
        )

        event = ViolationEvent(
            track_id=track_id,
            timestamp=timestamp,
            camera_name=camera_name,
            company_id=company_id,
            confidence=confidence,
            violation_type=violation_type,
            camera_id=camera_id,
            department_id=department_id,
            employee_id=employee_id,
            employee_name=employee_name,
            identity_confidence=identity_confidence,
            sync_status="queued" if (notifier or backend) else "local",
            crop_path=crop_path,
            full_path=full_path,
            crop_frame=crop_frame,
        )
        # Diskda rasm bo'lsa — navbatga qo'yamiz (NotificationWorker ishonchli
        # yuboradi: retry + backoff + offline drain). Aks holda retry uchun rasm
        # yo'q, shuning uchun darhol (retrysiz) yuboramiz.
        if crop_path or full_path:
            self.notification_queue.enqueue_violation_jobs(
                event,
                telegram_enabled=notifier is not None,
                backend_enabled=backend is not None,
            )
        else:
            self.dispatcher.dispatch(event, frame, notifier=notifier, backend=backend)
        return event
