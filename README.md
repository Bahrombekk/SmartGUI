# SafeZone — SmartHelmet GUI

**SafeZone** — zavod va sanoat hududidagi IP kameralar orqali ishchilarni real
vaqtda kuzatuvchi, **shlem (kaska) kiymagan** xodimlarni AI yordamida aniqlovchi
va buzilishlarni dalil rasmi bilan qayd etuvchi desktop ilova.

Ilova PyQt6 da yozilgan, YOLO (Ultralytics) detection modeli bilan ishlaydi,
bir nechta RTSP kamerani bir vaqtda boshqaradi, buzilishlarni SQLite bazaga
saqlaydi hamda Telegram va backend API orqali xabar yuboradi.

> Kod va izohlar asosan o'zbek tilida. Interfeys tili: o'zbekcha (`uz`).

---

## Asosiy imkoniyatlar

- 🎥 **Ko'p kamerali live monitoring** — bir vaqtda 10 tagacha RTSP/RTMP kamera.
- 🦺 **Shlem detection** — YOLO model + rolling-vote (ovoz berish) bilan
  barqaror "shlem bor / yo'q" qarori.
- 🧠 **Batch GPU inference** — bir nechta kamera bitta YOLO modelida guruhlanib
  batch rejimida qayta ishlanadi (CPU yukini keskin kamaytiradi).
- 🎯 **IoU + velocity tracker** — har odamga barqaror `track_id`, bo'sh
  freymlarda box ekstrapolyatsiyasi (silliq overlay).
- 📸 **Buzilishni dalil bilan saqlash** — crop + full rasm, SQLite yozuvi,
  takroriy event-ni oldini olish (track + fazoviy + cooldown filtrlari).
- 🔔 **Ishonchli xabar yetkazish** — Telegram va backend uchun navbatga
  asoslangan (queue) worker: retry, eksponensial backoff, offline drain.
- 👤 **FaceID (ixtiyoriy)** — YuNet + SFace embedding orqali xodimni tanish va
  ruxsat (access roster) nazorati.
- 📊 **Analitika** — kunlik/soatlik/haftalik statistika, bo'lim va kamera
  kesimida hisobotlar.
- 🌗 **Dark / Light tema**, fullscreen, klaviatura yorliqlari, screenshot.
- 🛡️ **Bardoshlilik** — RTSP qayta ulanish (4 usul + GPU NVDEC), SQLite
  korruptsiyadan avtomatik tiklanish (quarantine + qayta yaratish).
- 🪟 **Windows Service rejimi** — `nssm` orqali avtoyuklanuvchi xizmat.

---

## Texnologiyalar

| Qatlam | Texnologiya |
|---|---|
| GUI | PyQt6 |
| Kompyuter ko'rish | OpenCV (FFmpeg/NVDEC), NumPy |
| AI / detection | Ultralytics YOLO, PyTorch (CUDA ixtiyoriy) |
| FaceID | OpenCV YuNet (`yunet.onnx`) + SFace (`sface.onnx`), Haar fallback |
| Ma'lumotlar bazasi | SQLite (WAL rejimi, thread-local ulanishlar) |
| Xabarnomalar | Telegram Bot API, maxsus backend API (`requests`) |
| Til | Python 3.10+ |

---

## Arxitektura

Loyiha qatlamli (layered) arxitekturada qurilgan — UI, biznes logika va tashqi
integratsiyalar bir-biridan ajratilgan.

```
                 ┌─────────────────────────────────────────────┐
                 │                  UI (PyQt6)                   │
                 │  MainWindow · Dashboard · Cameras · Reports   │
                 │  Analytics · Users · Settings                 │
                 └───────────────────────┬─────────────────────┘
                                         │ signals
                 ┌───────────────────────▼─────────────────────┐
                 │        CameraRuntimeController (controller)   │
                 │  worker lifecycle · cache · restart machine   │
                 └───────────────────────┬─────────────────────┘
                                         │
        ┌────────────────────────────────┼──────────────────────────────┐
        │                                │                               │
┌───────▼────────┐          ┌────────────▼──────────┐        ┌───────────▼────────┐
│ DetectionWorker│          │   CameraService       │        │ Notification/Cleanup│
│  (QThread/cam) │◄────────►│  (global singleton)   │        │      Workers        │
│  frame loop    │  result  │  DetectorGroup (batch │        │  queue drain/retry  │
└───────┬────────┘          │  YOLO inference)      │        └─────────────────────┘
        │                   └───────────────────────┘
        │ frame
┌───────▼────────┐   ┌──────────────────────────────────────────────┐
│ CV2RTSPReader  │   │           Application services               │
│ (lock-free buf)│   │ PersonDetectionAnalyzer · ViolationRuntime · │
└────────────────┘   │ ViolationService · FaceIdService · Analytics │
                     └──────────────────────┬───────────────────────┘
                                            │
                     ┌──────────────────────▼───────────────────────┐
                     │            Infrastructure                     │
                     │ sqlite_db · file_storage · telegram_notifier  │
                     │ backend_client · notification_dispatcher      │
                     └───────────────────────────────────────────────┘
```

### Qatlamlar va ularning vazifasi

- **`app/ui/`** — PyQt6 oynalari, sahifalar, widgetlar va tema. UI hech qachon
  to'g'ridan-to'g'ri SQLite, RTSP yoki YOLO bilan ishlamaydi — faqat controller
  signallariga ulanadi.
- **`app/ui/controllers/`** — `CameraRuntimeController`: barcha kamera
  workerlarining yagona egasi. Worker'larni ishga tushiradi, to'xtatadi, qayta
  ulaydi va oxirgi holatlarni cache qilib UI ga signal orqali uzatadi
  (bloklanmaydigan restart state-machine).
- **`app/workers/`** — fon (QThread) workerlari:
  - `DetectionWorker` — bitta kamera uchun frame loop, AI natijani olish,
    overlay chizish, buzilishni qayd etish.
  - `CameraService` / `DetectorGroup` — global YOLO singleton, batch inference.
  - `NotificationWorker` — `notification_jobs` navbatini ishonchli yuboruvchi.
  - `CleanupWorker` — eski yozuv va fayllarni tozalovchi.
- **`app/application/services/`** — biznes logika (UI va texnik detallardan
  ajratilgan): `PersonDetectionAnalyzer`, `ViolationRuntime`, `ViolationService`,
  `FaceIdService`, `NotificationQueueService`, `tracking` (IoUTracker),
  `analytics_service`.
- **`app/domain/`** — sof biznes obyektlari va qoidalari: `entities.py`
  (`Camera`, `ViolationEvent`, `FaceIdentity`...), `policies.py`
  (`HelmetPolicy`, `AccessPolicy`).
- **`app/infrastructure/`** — tashqi dunyo bilan ishlovchi adapterlar:
  - `camera/cv2_rtsp_reader.py` — RTSP o'qish (lock-free double buffer, NVDEC).
  - `persistence/sqlite_db.py`, `file_storage.py` — DB va fayl saqlash.
  - `notifications/` — Telegram, backend va dispatcher.
- **`app/config/`** — `settings_manager.py`: `settings.json` o'qish/yozish,
  migratsiyalar, kamera/bo'lim/foydalanuvchi CRUD, `CameraConfigProxy`.
- **`app/bootstrap/`** — `startup_checks.py`: ishga tushishda model, DB,
  papkalar, secrets va asset tekshiruvlari.
- **`app/shared/`** — umumiy yordamchilar (`cv2qt`, `frame_display`).

### Detection oqimi (qisqacha)

1. `CV2RTSPReader` kameradan freym oladi (lock-free bufer, NVDEC GPU dekod).
2. `DetectorGroup` bir guruh kameradan snapshot olib **batch YOLO** inference
   bajaradi va `DetectionResult` ni cache qiladi.
3. `DetectionWorker` oxirgi natijani oladi → `PersonDetectionAnalyzer` odamlarni
   `IoUTracker` bilan track qiladi va rolling-vote orqali shlem holatini aniqlaydi.
4. `ViolationRuntime` `confirmation_threshold` ketma-ket freymdan keyin, track +
   fazoviy + cooldown duplicate filtridan o'tib, buzilishni navbatga qo'yadi.
5. `ViolationService` rasmni saqlaydi, SQLite ga yozadi va xabar navbatiga
   (`notification_jobs`) qo'yadi.
6. `NotificationWorker` navbatni Telegram/backend ga ishonchli yuboradi
   (retry + backoff + offline drain).
7. UI esa faqat tayyor freym, statistika va buzilish signallarini chizadi.

---

## Papkalar tuzilishi

```text
SmartGUI/
├── main.py                      # Kirish nuqtasi (venv majburlash, splash, logging)
├── run.bat                      # Windows ishga tushirish + service o'rnatish
├── requirements.txt
├── settings.example.json        # Namuna konfiguratsiya (settings.json git'ga kirmaydi)
├── app/
│   ├── bootstrap/               # startup_checks
│   ├── config/                  # settings_manager (ConfigManager, CameraConfigProxy)
│   ├── domain/                  # entities, policies
│   ├── application/services/    # detection_analysis, tracking, violation_*, faceid, analytics
│   ├── infrastructure/
│   │   ├── camera/              # cv2_rtsp_reader
│   │   ├── persistence/         # sqlite_db, file_storage
│   │   └── notifications/       # telegram_notifier, backend_client, dispatcher
│   ├── workers/                 # detection_worker, camera_service, notification_worker, cleanup_worker
│   ├── ui/
│   │   ├── controllers/         # camera_runtime_controller
│   │   ├── pages/               # main_window, dashboard/, cameras, violations, analytics, users, settings
│   │   ├── widgets/             # camera_panel, video_label, violation_card, stat_card, bar_chart, polygon_editor
│   │   └── styles/              # QSS + tema tokenlari
│   └── models/                  # best.pt, yunet.onnx, sface.onnx (git'ga kirmaydi)
├── docs/                        # Batafsil hujjatlar (o'zbekcha)
├── images/                      # SVG ikonalar, logo
├── violations/                  # Buzilish rasmlari (runtime)
├── screenshots/                 # Saqlangan screenshotlar
└── logs/                        # smartgui.log (rotating)
```

---

## O'rnatish

### Talablar

- **Python 3.10+** (Windows tavsiya etiladi; ilova win32 uchun moslangan)
- AI rejim uchun: **PyTorch + CUDA** (GPU bilan tavsiya etiladi)
- YOLO modeli: `app/models/best.pt`

### Qadamlar

```bash
# 1. Repozitoriyni klonlash
git clone <repo-url>
cd SmartGUI

# 2. Virtual muhit yaratish (papka nomi 'venv' bo'lishi shart — main.py shuni kutadi)
python -m venv venv

# 3. Faollashtirish
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/macOS

# 4. Kutubxonalarni o'rnatish
pip install -r requirements.txt

# 5. PyTorch ni alohida o'rnatish (GPU uchun pytorch.org dan mos versiyani tanlang)
pip install torch torchvision

# 6. Modelni joylashtirish
#    app/models/best.pt  (shlem detection modeli)
#    app/models/yunet.onnx + sface.onnx  (FaceID uchun, ixtiyoriy)

# 7. Konfiguratsiya
copy settings.example.json settings.json     # Windows
# cp settings.example.json settings.json      # Linux/macOS
#    -> settings.json ichida RTSP URL, token va boshqalarni to'ldiring
```

> **Eslatma:** `settings.json`, `*.pt`, `*.db`, `venv/` va buzilish rasmlari
> `.gitignore` da — ular git'ga commit qilinmaydi. Maxfiy ma'lumotlar (RTSP
> parol, Telegram token, backend login) faqat lokal `settings.json` da turadi.

---

## Ishga tushirish

```bash
python main.py
```

yoki Windows da `run.bat` ni ikki marta bosing.

`main.py` avtomatik ravishda:
- agar boshqa Python bilan ishga tushsa, `venv\Scripts\python.exe` ga o'tadi;
- AI yoqilgan bo'lsa `torch` ni PyQt6 dan **oldin** import qiladi (Windows
  CUDA DLL muammosini oldini olish uchun);
- splash screen ko'rsatadi va `MainWindow` ni ochadi;
- xato bo'lsa `logs/crash_*.log` ga to'liq stacktrace yozadi.

### Windows Service (avtoyuklash)

```bash
# Administrator sifatida (nssm.cc dan nssm.exe kerak)
run.bat service           # xizmatni o'rnatish va ishga tushirish
run.bat service remove    # xizmatni o'chirish
```

### Klaviatura yorliqlari

| Yorliq | Amal |
|---|---|
| `Ctrl+1..4` | Dashboard / Cameras / Reports / Analytics |
| `Ctrl+,` | Settings |
| `Ctrl+S` | Screenshot |
| `Space` | Barcha kameralarni pauza / davom |
| `F5` | Joriy sahifani yangilash |
| `Esc` | Fullscreen dan chiqish |
| `Ctrl+Q` | Chiqish |

---

## Konfiguratsiya (`settings.json`)

Sozlamalar `settings.example.json` dan nusxalanadi. Asosiy maydonlar:

### Kameralar va bo'limlar

| Kalit | Tavsif |
|---|---|
| `cameras[]` | Kameralar ro'yxati (maks. 10). Har biri: `id`, `name`, `rtsp_url`, `company_id`, `department_id`, `enabled`, `polygon_points`, `access_mode` |
| `departments[]` | Bo'limlar ro'yxati (`id`, `name`, `expanded`) |
| `users[]` | Xodimlar (FaceID/access uchun: `employee_id`, `photo_path`, `department_id`) |

### AI / detection

| Kalit | Default | Tavsif |
|---|---|---|
| `ai_model_enabled` | `false` | AI ni yoqish/o'chirish (o'chirilsa — faqat video) |
| `model_path` | `app\models\best.pt` | YOLO model yo'li (`.pt` yoki `.engine`) |
| `confidence` | `0.5` | Detection ishonch chegarasi |
| `yolo_imgsz` | `1024` | Inference rasm o'lchami |
| `use_gpu` | `true` | CUDA ishlatish |
| `person_class_id` | `0` | Odam classi ID si |
| `helmet_class_ids` | `[1]` | Shlemli class ID(lar) |
| `no_helmet_class_ids` | `[2]` | Shlemsiz class ID(lar) |
| `cameras_per_model` | `3` | Har YOLO modeliga nechta kamera (guruhlash) |
| `inference_batch_size` | `3` | Batch hajmi |
| `ai_fps_limit` | `10` | AI inference FPS chegarasi |
| `process_every_n` | `1` | Har N-freymdan birini qayta ishlash |

### Tracking va tasdiqlash

| Kalit | Tavsif |
|---|---|
| `tracking_strictness` | `stable` / `balanced` / `fast` preset |
| `confirmation_threshold` | Buzilish tasdiqlanishi uchun ketma-ket freym soni |
| `violation_cooldown` | Bir joydan takror buzilishgacha kutish (sekund) |
| `helmet_status_window` / `helmet_status_threshold` | Rolling-vote oynasi va chegarasi |

### Video / ko'rsatish

| Kalit | Tavsif |
|---|---|
| `video_fps_limit` | Video ko'rsatish FPS chegarasi |
| `display_max_width` | Freymni ko'rsatishdan oldin masshtablash kengligi |
| `reconnect_delay` / `max_reconnects` | RTSP qayta ulanish |
| `cameras_grid_columns` | Dashboard grid ustunlari |

### Integratsiyalar

| Kalit | Tavsif |
|---|---|
| `telegram_enabled`, `telegram_token`, `telegram_chat_ids` | Telegram xabarnomasi |
| `backend_enabled`, `backend_url`, `backend_login`, `backend_password` | Backend API |
| `save_violations`, `violations_dir` | Dalil rasmlarini saqlash |
| `keep_files_days`, `cleanup_files` | Eski yozuv/fayllarni tozalash |
| `faceid_enabled`, `faceid_threshold`, `access_roster_enabled` | FaceID va ruxsat nazorati |

---

## Ma'lumotlar bazasi (SQLite)

`smartgui.db` — WAL rejimida, har thread o'z ulanishiga ega. Korruptsiya
aniqlansa fayl avtomatik karantin (`*.corrupt.*`) qilinadi va qayta yaratiladi.

| Jadval | Vazifa |
|---|---|
| `violations` | Buzilishlar jurnali (timestamp, track_id, rasm yo'llari, kamera, xodim, sync_status) |
| `employees` | Xodimlar (FaceID uchun) |
| `face_embeddings` | Yuz embeddinglari (SFace 128-dim, BLOB) |
| `cameras` | Kameralar (config'dan sync qilinadi) |
| `notification_jobs` | Xabar navbati (pending/sent/failed, retry_count) |
| `daily_stats` | Kunlik deteksiya statistikasi |

---

## Xabarnomalar (Telegram / Backend)

Buzilish rasmi diskka saqlangan bo'lsa, xabar **`notification_jobs` navbatiga**
qo'yiladi — `NotificationWorker` uni fon rejimida yuboradi:

- ✅ **Retry + eksponensial backoff** — vaqtinchalik xato bo'lsa qayta urinadi.
- ✅ **Offline drain** — ilova ishlamagan paytda to'plangan joblarni startda yuboradi.
- ✅ **`max_retries`** dan oshsa — `failed` deb belgilanadi (cheksiz urinmaydi).
- ✅ Yuborilgach `violations.sync_status = 'synced'` qilinadi.

Rasm yo'q bo'lsa (saqlash o'chirilgan), `NotificationDispatcher` orqali darhol
(retrysiz) yuboriladi.

---

## FaceID (ixtiyoriy)

`faceid_enabled` yoqilsa va `app/models/` da `yunet.onnx` + `sface.onnx` bo'lsa:

- **YuNet** yuzni topadi, **SFace** 128-o'lchovli embedding chiqaradi,
  cosine similarity bilan xodim tanilanadi (`faceid_threshold`).
- ONNX modellari bo'lmasa — Haar cascade + CLAHE fallback ishlaydi.
- Xodimlar `users[]` dagi `photo_path` orqali avtomatik enroll qilinadi.
- `AccessPolicy` — `access_mode: "employees"` bo'lganda ruxsatsiz xodim
  `unauthorized_area`, tanilmagan odam `unknown_person` buzilishi sifatida
  qayd etiladi.

---

## Hujjatlar

Batafsil texnik hujjatlar `docs/` papkasida (o'zbekcha):

- [ARCHITECTURE_UZ.md](docs/ARCHITECTURE_UZ.md) — arxitektura tamoyillari va tavsiyalar
- [PRODUCT_BLUEPRINT_UZ.md](docs/PRODUCT_BLUEPRINT_UZ.md) — mahsulot blueprinti
- [DATA_FLOW_UZ.md](docs/DATA_FLOW_UZ.md) — ma'lumotlar oqimi
- [COMPONENT_CONTRACTS_UZ.md](docs/COMPONENT_CONTRACTS_UZ.md) — komponent shartnomalari
- [UI_UX_SPEC_UZ.md](docs/UI_UX_SPEC_UZ.md) — UI/UX spetsifikatsiyasi
- [IMPLEMENTATION_ROADMAP_UZ.md](docs/IMPLEMENTATION_ROADMAP_UZ.md) — amalga oshirish rejasi

---

## Muammolarni bartaraf etish

| Muammo | Yechim |
|---|---|
| `PyQt6 o'rnatilmagan` | `pip install PyQt6` |
| `torch yuklanmadi` | `pip install torch torchvision` (pytorch.org dan CUDA mos versiyasi) |
| `Model topilmadi` | `app/models/best.pt` ni joylang yoki `model_path` ni to'g'rilang |
| Kamera ulanmayapti | RTSP URL, login/parol, tarmoqni tekshiring; UI dagi "↻ Reconnect" tugmasi |
| Yuqori CPU | `use_gpu: true`, `ai_fps_limit` va `process_every_n` ni sozlang |
| DB buzilgan | Avtomatik karantin qilinadi (`*.corrupt.*`) va yangisi yaratiladi |
| Batafsil xato | `logs/smartgui.log` va `logs/crash_*.log` ga qarang |

---

## Litsenziya

`LICENSE` fayliga qarang.
