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

    model_path = Path(str(getattr(cfg, "model_path", "") or cfg.get("model_path", "") or ""))
    model_enabled = bool(getattr(cfg, "ai_model_enabled", False))
    if model_enabled:
        results.append(CheckResult("AI model", model_path.exists(), f"Model path: {model_path or 'empty'}"))
    else:
        results.append(CheckResult("AI model", True, "AI model disabled"))

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

    return results
