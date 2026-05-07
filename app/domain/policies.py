from __future__ import annotations

from app.domain.entities import AccessViolation, FaceIdentity


NO_HELMET_CLASS_IDS = {2}
HELMET_CLASS_IDS = {1}

_NO_HELMET_KEYS = ("no_helmet", "no-helmet", "without", "bare", "nohel")
_HELMET_KEYS = ("helmet", "with_helmet", "safe", "hardhat", "hard_hat")


class HelmetPolicy:
    """Classifies model detections into helmet safety states."""

    def __init__(
        self,
        helmet_class_ids: set[int] | None = None,
        no_helmet_class_ids: set[int] | None = None,
    ):
        self.helmet_class_ids = helmet_class_ids or HELMET_CLASS_IDS
        self.no_helmet_class_ids = no_helmet_class_ids or NO_HELMET_CLASS_IDS

    def classify(self, person: dict) -> dict:
        class_id = person.get("class_id")
        if class_id in self.no_helmet_class_ids:
            person["has_helmet"] = False
            return person
        if class_id in self.helmet_class_ids:
            person["has_helmet"] = True
            return person

        cname = str(person.get("class_name", person.get("class", ""))).lower()
        if any(k in cname for k in _NO_HELMET_KEYS):
            person["has_helmet"] = False
        elif any(k in cname for k in _HELMET_KEYS):
            person["has_helmet"] = True
        else:
            person["has_helmet"] = None
        return person


class AccessPolicy:
    """Evaluates FaceID matches against camera access roster settings."""

    def evaluate(self, camera: dict, identity: FaceIdentity | None) -> AccessViolation | None:
        if identity is None or not identity.matched:
            return AccessViolation(violation_type="unknown_person")

        access_mode = str(camera.get("access_mode", "department") or "department")
        allowed_employee_ids = {str(x) for x in camera.get("allowed_employee_ids", []) if str(x)}
        if access_mode == "employees" and allowed_employee_ids:
            if str(identity.employee_id) not in allowed_employee_ids:
                return AccessViolation(
                    violation_type="unauthorized_area",
                    employee_id=identity.employee_id,
                    employee_name=identity.employee_name,
                    identity_confidence=identity.confidence,
                )
        return None
