# SmartHelmet Data Flow

## Kamera Oqimi

1. `MainWindow` sozlamadan kameralar ro'yxatini oladi.
2. Har kamera uchun `DetectionWorker` yaratiladi.
3. Worker `CV2RTSPReader` orqali frame oladi.
4. Frame UIga signal orqali uzatiladi.
5. `DashboardPage.update_frame()` kamera panelini yangilaydi.

Qoida:

- UI hech qachon RTSP loopni bloklamaydi.
- Display doim joriy live framedan chiziladi.

## AI Detection Oqimi

1. Worker frame oladi.
2. Detection interval bo'yicha inference bajariladi.
3. Tracker/person state yangilanadi.
4. Overlay live frame nusxasiga chiziladi.
5. Stats UIga yuboriladi.

Qoida:

- Detection qilingan eski `raw_frame` displayga qaytarilmaydi.
- `raw_frame` faqat violation evidence saqlash uchun ishlatiladi.

## Violation Saqlash Oqimi

1. Worker shlemsiz yangi personni aniqlaydi.
2. Save item queuega qo'yiladi.
3. Alohida writer thread `ViolationService.register_violation()` chaqiradi.
4. `ViolationFileStorage` crop va full image saqlaydi.
5. `ViolationsDB` SQLitega yozadi.
6. Notification dispatcher Telegram/backend yuboradi.
7. UIga violation payload emit qilinadi.

Qoida:

- File/DB/network ishlar detection loopni qotirmasligi kerak.

## Dashboard State Oqimi

State `DashboardPage` ichida saqlanadi:

- `_panels`
- `_cam_items`
- `_cam_status`
- `_today_per_cam`
- `_recent_violations`
- `_department_rows`

Render:

- kamera ro'yxati o'zgarsa grid/sidebar rebuild
- stats o'zgarsa row/card ichidagi qiymatlar update
- violation kelsa no helmet/recent/detected panels update

## Persistence Oqimi

SQLite:

- violation history
- analytics queries

Files:

- crop image
- full frame image

Retention:

- keyingi bosqichda cleanup worker orqali eski fayllarni tozalash kerak.
