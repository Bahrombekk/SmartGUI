# Implementation Roadmap

Bu roadmap DOCXdagi umumiy rejani amaliy bosqichlarga bo'ladi.

## 1. Foundation

Status: bajarildi.

- Dashboard modulga bo'lindi.
- Compatibility shim saqlandi.
- `app/ui/design_system.py` qo'shildi.
- `theme.C()` design tokenlar bilan bog'landi.
- Dashboard flicker va old-frame sakrashi tuzatildi.

## 2. Dashboard Polish

Status: davom etmoqda.

- Department Stats stable row update ishlatadi.
- No Helmet kartalar crop thumbnail ko'rsatadi.
- Monitor toolbar icon path tuzatildi.

Keyingi ishlar:

- AI Detection panelini real health metrics bilan bog'lash.
- Detected People paneliga person crop/avatar qo'shish.
- Empty states va loading statesni bir xil uslubga keltirish.

## 3. Reports / Violations

Maqsad:

- crop/full evidence galereyasini design systemga moslash
- filterlar: date, camera, confidence, department
- detail dialogni premium monitoring uslubiga o'tkazish

Fayllar:

- `app/ui/pages/violations_page.py`
- `app/ui/widgets/violation_card.py`

## 4. Analytics

Maqsad:

- Today/week/month cards
- Department breakdown
- Hourly trend
- Camera ranking

Fayllar:

- `app/ui/pages/analytics_page.py`
- `app/ui/widgets/bar_chart.py`

## 5. Users

Maqsad:

- role/status based table
- create/edit user dialog
- audit-friendly layout

Fayl:

- `app/ui/pages/users_page.py`

## 6. Settings

Maqsad:

- settingsni guruhlarga ajratish
- camera/model/notifications/storage/performance tabs
- validation va restart kerak bo'lgan sozlamalar uchun aniq indicator

Fayl:

- `app/ui/pages/settings_dialog.py`

## 7. Architecture Hardening

Maqsad:

- dashboard presenter yoki view-model qatlamini qo'shish
- analytics service ajratish
- cleanup worker qo'shish
- startup checks qo'shish

Tavsiya qilingan yangi fayllar:

- `app/application/services/analytics_service.py`
- `app/workers/cleanup_worker.py`
- `app/bootstrap/startup_checks.py`

## 8. Test / Rollout

Minimal tekshiruv:

```powershell
venv\Scripts\python.exe -m py_compile app/ui/design_system.py app/ui/theme.py app/ui/pages/dashboard_page.py app/ui/pages/dashboard/page.py app/ui/pages/dashboard/monitor.py app/ui/pages/dashboard/bottom_panels.py
```

Manual QA:

- Dashboard ochiladi.
- Kamera grid update bo'ladi.
- Department stats qiymatlari lipillamaydi.
- No Helmet crop chiqadi.
- Violations sahifasi yangi violationdan keyin reload bo'ladi.
- AI pause/start signal ishlaydi.
