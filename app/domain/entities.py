from dataclasses import dataclass

import numpy as np


@dataclass(slots=True)
class ViolationEvent:
    """Single helmet violation detected from one camera frame."""

    track_id: int
    timestamp: int
    camera_name: str
    company_id: str
    confidence: float
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
            "crop_frame": self.crop_frame,
        }
