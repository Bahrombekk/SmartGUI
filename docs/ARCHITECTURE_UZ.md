# SmartGUI Arxitekturasi

## Maqsad

Bu loyiha zavod hududidagi kameralar orqali:

- odamlarni aniqlash
- shlem bor yoki yo'qligini tekshirish
- buzilishlarni saqlash
- operatorga ko'rsatish
- Telegram, backend yoki boshqa tizimlarga yuborish

uchun quriladi.

Arxitektura shunday bo'lishi kerakki:

- yangi dasturchi tez tushunsin
- yangi kamera, yangi integratsiya yoki yangi qoida qo'shish oson bo'lsin
- UI, detection va integratsiya kodlari bir-biriga yopishib ketmasin
- test yozish va xatoni topish oson bo'lsin

## Asosiy tamoyillar

1. Har bir papka bitta aniq vazifaga ega bo'lsin.
2. UI kodlari detection logikasini bilmasin.
3. Detection worker tashqi servislar bilan to'g'ridan-to'g'ri gaplashmasin.
4. Konfiguratsiya, saqlash, yuborish va biznes qoidalar alohida qatlamlarda bo'lsin.
5. Fayl nomlari bir xil uslubda bo'lsin: `snake_case`.
6. Bitta fayl ichida bitta katta mas'uliyat bo'lsin.

## Tavsiya etilgan papka struktura

```text
SmartGUI/
├── main.py
├── requirements.txt
├── settings.json
├── README.md
├── docs/
│   ├── ARCHITECTURE_UZ.md
│   ├── DETECTION_FLOW.md
│   ├── CONFIG_GUIDE.md
│   └── DEPLOYMENT.md
├── app/
│   ├── __init__.py
│   ├── bootstrap/
│   │   ├── __init__.py
│   │   ├── app_factory.py
│   │   ├── dependency_container.py
│   │   └── startup_checks.py
│   ├── config/
│   │   ├── __init__.py
│   │   ├── settings_manager.py
│   │   ├── defaults.py
│   │   ├── schema.py
│   │   └── migrations.py
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── entities.py
│   │   ├── enums.py
│   │   ├── dto.py
│   │   └── policies.py
│   ├── application/
│   │   ├── __init__.py
│   │   ├── use_cases/
│   │   │   ├── process_frame.py
│   │   │   ├── register_violation.py
│   │   │   ├── send_notifications.py
│   │   │   ├── restart_cameras.py
│   │   │   └── load_dashboard_stats.py
│   │   └── services/
│   │       ├── camera_service.py
│   │       ├── violation_service.py
│   │       ├── analytics_service.py
│   │       └── cleanup_service.py
│   ├── infrastructure/
│   │   ├── __init__.py
│   │   ├── camera/
│   │   │   ├── cv2_rtsp_reader.py
│   │   │   ├── video_file_reader.py
│   │   │   └── reconnect_policy.py
│   │   ├── detection/
│   │   │   ├── smarthelmet_adapter.py
│   │   │   ├── detector_factory.py
│   │   │   └── polygon_filter.py
│   │   ├── persistence/
│   │   │   ├── sqlite_db.py
│   │   │   ├── violation_repository.py
│   │   │   └── file_storage.py
│   │   ├── notifications/
│   │   │   ├── telegram_client.py
│   │   │   ├── backend_client.py
│   │   │   └── notification_dispatcher.py
│   │   └── logging/
│   │       ├── logger.py
│   │       └── crash_reporter.py
│   ├── workers/
│   │   ├── __init__.py
│   │   ├── detection_worker.py
│   │   ├── notification_worker.py
│   │   └── cleanup_worker.py
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── pages/
│   │   │   ├── main_window.py
│   │   │   ├── dashboard_page.py
│   │   │   ├── violations_page.py
│   │   │   ├── analytics_page.py
│   │   │   ├── settings_dialog.py
│   │   │   └── about_page.py
│   │   ├── widgets/
│   │   │   ├── camera_panel.py
│   │   │   ├── video_label.py
│   │   │   ├── violation_card.py
│   │   │   ├── stat_card.py
│   │   │   └── charts/
│   │   │       ├── bar_chart.py
│   │   │       ├── line_chart.py
│   │   │       └── hourly_bar_chart.py
│   │   └── presenters/
│   │       ├── dashboard_presenter.py
│   │       ├── violation_presenter.py
│   │       └── analytics_presenter.py
│   ├── shared/
│   │   ├── __init__.py
│   │   ├── paths.py
│   │   ├── constants.py
│   │   ├── exceptions.py
│   │   └── utils/
│   │       ├── cv2qt.py
│   │       ├── time_utils.py
│   │       └── image_utils.py
│   └── assets/
│       ├── models/
│       │   └── best.pt
│       ├── icons/
│       └── styles/
│           └── theme.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── smoke/
└── scripts/
    ├── run_dev.py
    ├── cleanup_data.py
    └── export_violations.py
```

## Papkalar vazifasi

### `bootstrap/`

Dastur ishga tushganda kerak bo'ladigan boshlang'ich kodlar shu yerda bo'ladi.

- `app_factory.py`: `QApplication`, `MainWindow`, servislar va dependencylarni yig'adi
- `dependency_container.py`: qaysi klass qaysi servisni olishini belgilaydi
- `startup_checks.py`: model bor-yo'qligi, papkalar, DB va config tekshiradi

### `config/`

Sozlamalarni faqat shu qatlam boshqaradi.

- `defaults.py`: default qiymatlar
- `schema.py`: setting struktura va validatsiya
- `migrations.py`: eski `settings.json` formatlarini yangi formatga o'tkazish
- `settings_manager.py`: o'qish, yozish, update qilish

Bu qatlamda hech qanday UI bo'lmasligi kerak.

### `domain/`

Bu loyiha yuragidagi biznes tushunchalar shu yerda turadi.

Misollar:

- `Camera`
- `Violation`
- `DetectionResult`
- `PersonDetection`
- `NotificationPayload`

Bu qatlam iloji boricha PyQt, SQLite yoki Telegram'ga bog'liq bo'lmasin.

### `application/`

Bu qatlam "nima qilish kerak?" degan savolga javob beradi.

Misollar:

- frame kelganda nima qilish kerak
- buzilish topilganda nima qilish kerak
- dashboard uchun statistikani qanday yig'ish kerak

Bu yerda katta oqimlar boshqariladi, lekin past darajadagi texnik detal bo'lmaydi.

### `infrastructure/`

Tashqi dunyo bilan bog'liq kodlar shu yerda bo'ladi.

- RTSP o'qish
- SmartHelmet integratsiyasi
- SQLite
- fayl saqlash
- Telegram yuborish
- backend API yuborish
- log yozish

Bu qatlam almashtirilishi mumkin bo'lgan adapterlardan iborat bo'lsa yaxshi bo'ladi.

### `workers/`

Thread yoki background workerlar shu yerda bo'ladi.

Masalan:

- `detection_worker.py`: kamera oqimini qayta ishlaydi
- `notification_worker.py`: navbatdagi xabarlarni yuboradi
- `cleanup_worker.py`: eski fayllarni tozalaydi

Muhim qoida:

worker ichida hamma ishni yozib yubormaslik kerak. Worker faqat oqimni boshqaradi, logikani servislar va use case'larga beradi.

### `ui/`

PyQt bilan bog'liq hamma narsa shu yerda bo'ladi.

- `pages/`: to'liq oynalar va sahifalar
- `widgets/`: qayta ishlatiladigan komponentlar
- `presenters/`: domain/application ma'lumotini UI formatiga moslab beradi

Masalan `CameraPanel_dash.py` o'rniga `ui/widgets/camera_panel.py` ancha to'g'ri bo'ladi.

### `shared/`

Barcha modullar ishlatadigan umumiy narsalar.

- umumiy exceptionlar
- path helperlar
- constantlar
- kichik util funksiyalar

### `assets/`

Kod bo'lmagan resurslar shu yerda saqlanadi.

- model fayllar
- iconlar
- style fayllar

`app/models/best.pt` o'rniga `app/assets/models/best.pt` tushunarliroq.

## Joriy loyihadan yangi struktura tomon ko'chirish

Hozirgi fayllarni mana shunday yo'nalishda ko'chirish mumkin:

| Hozirgi fayl | Tavsiya etilgan joy |
|---|---|
| `app/core/cam_read.py` | `app/infrastructure/camera/cv2_rtsp_reader.py` |
| `app/core/detection_worker.py` | `app/workers/detection_worker.py` |
| `app/core/database.py` | `app/infrastructure/persistence/sqlite_db.py` |
| `app/core/config_manager.py` | `app/config/settings_manager.py` |
| `app/pages/CameraPanel_dash.py` | `app/ui/widgets/camera_panel.py` |
| `app/pages/dashboard_page.py` | `app/ui/pages/dashboard_page.py` |
| `app/pages/violations_page.py` | `app/ui/pages/violations_page.py` |
| `app/pages/analytics_page.py` | `app/ui/pages/analytics_page.py` |
| `app/widgets/violation_card.py` | `app/ui/widgets/violation_card.py` |
| `app/widgets/video_label.py` | `app/ui/widgets/video_label.py` |
| `app/utils/theme.py` | `app/assets/styles/theme.py` yoki `app/ui/theme.py` |

## Detection oqimi qanday bo'lishi kerak

Toza arxitekturadagi oqim:

1. `camera_service` kameradan frame oladi
2. `process_frame` use case frame'ni detection adapterga beradi
3. detection natijasi `DetectionResult` ko'rinishida qaytadi
4. `violation_service` buzilish bor-yo'qligini tekshiradi
5. buzilish bo'lsa:
   - repository orqali DB ga yoziladi
   - file storage orqali crop/full image saqlanadi
   - notification dispatcher orqali Telegram/backend queue'ga yuboriladi
6. presenter UI uchun tayyor ko'rinishga o'tkazadi
7. dashboard faqat tayyor view-modelni chizadi

## Yangi funksiyalar uchun oldindan joy qoldirish

Kelajakda quyidagilar qo'shilishi mumkin:

- PPE turlari: shlem, jilet, niqob, qo'lqop
- zonalar bo'yicha nazorat
- ishchi identifikatsiyasi
- smena bo'yicha hisobot
- buzilish statistikasi eksporti
- email, SMS, WhatsApp bildirishnoma
- web panel
- rol va login tizimi
- offline queue va qayta yuborish
- bir nechta modelni almashtirish

Shu sabab quyidagi kengayish nuqtalari oldindan bo'lsin:

- `domain/enums.py`
  PPE turlari va violation turlari
- `application/services/notification_service.py`
  Yangi kanal qo'shish oson bo'ladi
- `infrastructure/notifications/`
  Har kanal alohida client
- `application/use_cases/register_violation.py`
  Barcha buzilishlar bir joydan ro'yxatdan o'tadi
- `domain/policies.py`
  "qaysi holat violation?" qoidalari shu yerda

## Fayl bo'lish qoidalari

Kod tez tushunilishi uchun quyidagi qoida juda foydali:

### 1. 300-400 qatordan oshgan faylni bo'lishni o'ylash

Masalan:

- detection
- file save
- notification
- db save

bular bir faylda emas.

### 2. Klass nomi va fayl nomi mos bo'lsin

Misol:

- `camera_panel.py` ichida `CameraPanel`
- `settings_manager.py` ichida `SettingsManager`

### 3. Bitta faylda bitta asosiy klass yoki bitta aniq modul bo'lsin

### 4. UI va backend logikani aralashtirmaslik

Masalan `QMessageBox` chaqiradigan kod `database.py` ichida bo'lmasin.

### 5. Noma'lum nomlardan qochish

Yomon nomlar:

- `core.py`
- `helper.py`
- `manager.py`
- `utils.py`

Yaxshi nomlar:

- `violation_repository.py`
- `telegram_client.py`
- `process_frame.py`
- `camera_panel.py`

## Naming qoidalari

- papka nomlari: `snake_case`
- fayl nomlari: `snake_case`
- klass nomlari: `PascalCase`
- funksiya va metodlar: `snake_case`
- constantlar: `UPPER_SNAKE_CASE`

Misol:

- to'g'ri: `camera_panel.py`
- noto'g'ri: `CameraPanel_dash.py`

## Har bir modul nima bilishi mumkin

Bu juda muhim qoida:

- `ui/` -> `application/` ni bilishi mumkin
- `application/` -> `domain/` ni bilishi mumkin
- `infrastructure/` -> `domain/` ni bilishi mumkin
- `domain/` -> hech kimga qaram bo'lmasin

Yaxshi amaliy qoida:

- `ui` hech qachon to'g'ridan-to'g'ri `sqlite3`, `requests`, `cv2.VideoCapture` bilan ishlamasin

## Yangi dasturchi uchun tushunarli qilish usuli

Repo ochgan odam birinchi 10 daqiqada yo'lini topishi kerak.

Buning uchun:

- `README.md` ichida qisqa loyiha tavsifi bo'lsin
- `docs/ARCHITECTURE_UZ.md` ichida umumiy arxitektura bo'lsin
- har katta papkada qisqa `README.md` bo'lsa yanada yaxshi
- muhim klasslar boshida 2-3 qatorlik docstring bo'lsin
- signal oqimlari alohida hujjatda yozilsin

## Sizning loyiha uchun eng to'g'ri yaqin reja

Hammasini birdan ko'chirish shart emas. Eng xavfsiz bosqichma-bosqich yo'l:

1. `pages` va `widgets` ni `ui/` ostiga tartibli ko'chirish
2. `CameraPanel_dash.py` nomini `camera_panel.py` qilish
3. `config_manager.py` ni `config/` ga ajratish
4. `database.py` va fayl saqlashni `infrastructure/persistence/` ga ajratish
5. `detection_worker.py` ichidan notification va save logikasini servisga chiqarish
6. `domain` entitylarini kiritish
7. `application/use_cases/` qatlamini qo'shish

## Birinchi bo'lib ajratilishi kerak bo'lgan joriy kodlar

Hozirgi loyihada birinchi navbatda ajratish kerak bo'lgan fayllar:

- `app/core/detection_worker.py`
  Juda ko'p mas'uliyat yig'ilgan
- `app/core/config_manager.py`
  Config, migration, camera CRUD va proxy bir joyda
- `app/pages/CameraPanel_dash.py`
  Joylashuvi va nomi noto'g'ri
- `app/core/database.py`
  Keyinchalik repository va storage qatlamiga bo'linishi kerak

## Xulosa

Eng yaxshi arxitektura bu:

- kichik papka
- aniq vazifa
- nomidan maqsadi bilinadigan fayl
- UI, logika va tashqi integratsiya bir-biridan ajralgan tizim

Bu loyiha uchun eng to'g'ri yo'nalish:

- `domain`
- `application`
- `infrastructure`
- `workers`
- `ui`
- `config`

ko'rinishidagi tuzilma bo'ladi.

Shunda keyinchalik yangi dasturchi kelib ham tez tushunadi, sizga ham yangi funksiya qo'shish ancha osonlashadi.
