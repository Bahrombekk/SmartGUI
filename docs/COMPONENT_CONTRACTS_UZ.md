# Component Contracts

Bu hujjat UI komponentlari qanday data kutishini va qanday event chiqarishini belgilaydi.

## DashboardPage Public API

Import compatibility:

```python
from app.ui.pages.dashboard_page import DashboardPage
```

Signals:

- `go_violations`
- `add_camera_requested`
- `ai_pause_requested(bool)`

Methods:

- `setup_cameras(cameras: list)`
- `set_search_text(text: str)`
- `set_grid_columns(columns: int)`
- `update_frame(cam_id: int, frame)`
- `on_violation(data: dict)`
- `on_stats(cam_id: int, stats: dict)`
- `on_status(cam_id: int, text: str)`
- `on_error(cam_id: int, msg: str)`
- `on_model_loaded(cam_id: int, model_name: str)`
- `set_total_persons(total: int)`

## Camera Payload

```python
{
    "id": 1,
    "name": "Stansiya 1",
    "rtsp_url": "rtsp://...",
    "company_id": "company-1",
    "department_id": 10
}
```

Required:

- `id`
- `name`

Optional:

- `rtsp_url`
- `company_id`
- `department_id`

## Stats Payload

```python
{
    "fps": 14.2,
    "active_persons": 3,
    "today_count": 42,
    "connected": True
}
```

UI binding:

- `connected=True` -> camera status `live`
- `connected=False` -> camera status `offline`
- `today_count` -> camera and department detection counters

## Violation Payload

```python
{
    "track_id": 13,
    "timestamp": 1714560000,
    "camera_name": "Stansiya 4",
    "company_id": "company-1",
    "confidence": 0.91,
    "has_helmet": False,
    "crop_path": "violations/crop_...",
    "full_path": "violations/full_...",
    "today_count": 696
}
```

UI binding:

- `crop_path` -> No Helmet thumbnail
- `full_path` -> detail/report view
- `track_id` -> person ID label
- `timestamp` -> time chip
- `today_count` -> system overview counters

## Department Stats Contract

Internal derived model:

```python
{
    "key": "dep:10",
    "name": "Main Building",
    "total": 4,
    "online": 2,
    "offline": 2,
    "detections": 9072,
    "percent": 50
}
```

Render rule:

- `key` o'zgarmasa row qayta yaratilmaydi.
- faqat label, status chip va progress qiymatlari update bo'ladi.

## Worker/UI Boundary

Detection worker quyidagilarni emit qiladi:

- frame -> `update_frame`
- stats -> `on_stats`
- violation -> `on_violation`
- error -> `on_error`

UI worker ichki thread, OpenCV yoki model detallarini bilmasligi kerak.
