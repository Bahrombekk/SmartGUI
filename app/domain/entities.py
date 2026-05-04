from dataclasses import dataclass, field

import numpy as np


@dataclass(slots=True)
class Department:
    id: int
    name: str
    expanded: bool = True


@dataclass(slots=True)
class Camera:
    id: int
    name: str
    rtsp_url: str = ""
    company_id: str = ""
    department_id: int | None = None
    enabled: bool = True
    access_mode: str = "department"
    allowed_department_ids: list[int] = field(default_factory=list)
    allowed_employee_ids: list[str] = field(default_factory=list)
    polygon_points: list[list[int]] = field(default_factory=list)


@dataclass(slots=True)
class Employee:
    id: int
    first_name: str
    last_name: str
    employee_id: str
    photo_path: str = ""
    department_id: int | None = None
    active: bool = True

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip() or self.employee_id


@dataclass(slots=True)
class FaceIdentity:
    employee_id: str
    employee_name: str
    confidence: float
    matched: bool


@dataclass(slots=True)
class DetectionEvent:
    camera_id: int
    camera_name: str
    timestamp: int
    persons: list[dict]


@dataclass(slots=True)
class AccessViolation:
    violation_type: str
    employee_id: str | None = None
    employee_name: str = ""
    identity_confidence: float = 0.0


@dataclass(slots=True)
class NotificationJob:
    id: int | None
    channel: str
    payload: dict
    status: str = "pending"
    retry_count: int = 0
    last_error: str = ""


@dataclass(slots=True)
class CameraHealth:
    camera_id: int
    connected: bool
    fps: float = 0.0
    ping_ms: float | None = None
    active_persons: int = 0
    last_error: str = ""


@dataclass(slots=True)
class ViolationEvent:
    """Single helmet violation detected from one camera frame."""

    track_id: int
    timestamp: int
    camera_name: str
    company_id: str
    confidence: float
    violation_type: str = "no_helmet"
    camera_id: int | None = None
    department_id: int | None = None
    employee_id: str | None = None
    employee_name: str = ""
    identity_confidence: float = 0.0
    sync_status: str = "queued"
    crop_path: str = ""
    full_path: str = ""
    crop_frame: np.ndarray | None = None

    def to_payload(self) -> dict:
        """UI-friendly payload while keeping DB-friendly field names."""
        return {
            "track_id": self.track_id,
            "timestamp": self.timestamp,
            "crop_path": self.crop_path,
            "full_path": self.full_path,
            "camera": self.camera_name,
            "camera_name": self.camera_name,
            "company_id": self.company_id,
            "confidence": self.confidence,
            "violation_type": self.violation_type,
            "camera_id": self.camera_id,
            "department_id": self.department_id,
            "employee_id": self.employee_id,
            "employee_name": self.employee_name,
            "identity_confidence": self.identity_confidence,
            "sync_status": self.sync_status,
            "has_helmet": self.violation_type != "no_helmet",
            "crop_frame": self.crop_frame,
        }
