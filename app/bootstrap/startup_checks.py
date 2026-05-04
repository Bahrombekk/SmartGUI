from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    message: str


def run_startup_checks(cfg, db) -> list[CheckResult]:
    results: list[CheckResult] = []

    try:
        for camera in cfg.get_cameras():
            db.upsert_camera(camera)
        for user in cfg.get_users():
            if not str(user.get("employee_id", "")).strip():
                continue
            db.upsert_employee(
                employee_id=str(user.get("employee_id", "")),
                first_name=user.get("first_name", ""),
                last_name=user.get("last_name", ""),
                photo_path=user.get("photo_path", ""),
                department_id=user.get("department_id"),
                active=bool(user.get("active", True)),
            )
        results.append(CheckResult("Config sync", True, "Cameras and employees synced to DB"))
    except Exception as exc:
        results.append(CheckResult("Config sync", False, str(exc)))

    model_path = Path(str(getattr(cfg, "model_path", "") or cfg.get("model_path", "") or ""))
    model_enabled = bool(getattr(cfg, "ai_model_enabled", False))
    if model_enabled:
        results.append(CheckResult("AI model", model_path.exists(), f"Model path: {model_path or 'empty'}"))
    else:
        results.append(CheckResult("AI model", True, "AI model disabled"))

    if model_enabled and bool(cfg.get("use_gpu", True)):
        try:
            import torch
            results.append(CheckResult("CUDA", torch.cuda.is_available(), "CUDA available" if torch.cuda.is_available() else "CUDA not available"))
        except Exception as exc:
            results.append(CheckResult("CUDA", False, str(exc)))

    viol_dir = Path(getattr(cfg, "violations_dir", Path("violations")))
    try:
        viol_dir.mkdir(parents=True, exist_ok=True)
        writable = viol_dir.exists() and viol_dir.is_dir()
    except Exception:
        writable = False
    results.append(CheckResult("Violations directory", writable, str(viol_dir)))

    try:
        total = db.get_total_count()
        results.append(CheckResult("Database", True, f"Total violations: {total}"))
    except Exception as exc:
        results.append(CheckResult("Database", False, str(exc)))

    image_dir = Path("images")
    required = ["dashboard.svg", "camera.svg", "layout-4x2.svg", "expand.svg"]
    missing = [name for name in required if not (image_dir / name).exists()]
    results.append(CheckResult("Assets", not missing, "Missing: " + ", ".join(missing) if missing else "OK"))

    if bool(cfg.get("telegram_enabled", False)):
        token_ok = bool(cfg.get("telegram_token", ""))
        chats_ok = bool(cfg.get("telegram_chat_ids", []))
        results.append(CheckResult("Telegram secrets", token_ok and chats_ok, "Configured" if token_ok and chats_ok else "Token/chat missing"))

    if bool(cfg.get("backend_enabled", False)):
        url_ok = bool(cfg.get("backend_url", ""))
        results.append(CheckResult("Backend config", url_ok, "Configured" if url_ok else "Backend URL missing"))

    if bool(cfg.get("faceid_enabled", False) or cfg.get("access_roster_enabled", False)):
        users = [u for u in cfg.get_users() if u.get("active", True)]
        with_photos = [u for u in users if u.get("photo_path") and Path(u.get("photo_path")).exists()]
        results.append(CheckResult("FaceID roster", bool(with_photos), f"{len(with_photos)}/{len(users)} active employees have photos"))

    return results
