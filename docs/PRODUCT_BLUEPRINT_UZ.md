# SmartHelmet Product Blueprint

Ushbu hujjat `Deep Research Backing Conversation for session None.docx` ichidagi rejani loyiha uchun amaliy blueprintga aylantiradi.

## Mahsulot Maqsadi

SmartHelmet operator va xavfsizlik nazoratchisi uchun kamera-markaziy monitoring tizimi.

Asosiy vazifalar:

- Kameralardan real vaqtda video oqimini ko'rsatish.
- AI orqali odam va shlem holatini aniqlash.
- Shlemsiz holatni dalil rasmi bilan saqlash.
- Bo'lim, kamera va vaqt kesimida statistikani ko'rsatish.
- Operatorga tez qaror qilish uchun silliq, chalg'itmaydigan dashboard berish.

## Foydalanuvchilar

- Operator: live kameralarni kuzatadi, buzilishlarni tez ko'radi.
- Xavfsizlik nazoratchisi: violationlar va hisobotlarni tahlil qiladi.
- Admin: kameralar, foydalanuvchilar, integratsiyalar va AI sozlamalarini boshqaradi.

## Asosiy UI Yo'nalishi

Tanlangan yo'nalish: kamera-markaziy hybrid monitoring.

- Birinchi ekran live monitoring bo'ladi.
- Kamera grid asosiy ish maydoni bo'lib qoladi.
- Sidebar kamera/bo'lim navigatsiyasi uchun ishlaydi.
- Pastki panellar qisqa statistik va alert summary beradi.
- Reports/Violations alohida galereya sifatida chuqur ko'rish uchun ishlaydi.

## Sahifalar

### Dashboard

Vazifa: operatorning asosiy real-time ekrani.

Komponentlar:

- Department camera tree
- Live camera grid
- Grid column controls
- Department stats
- Detected people
- AI status
- No Helmet evidence cards

### Cameras

Vazifa: kamera holatini ko'rish, qo'shish va boshqarish.

### Violations / Reports

Vazifa: saqlangan buzilishlarni crop/full frame bilan tekshirish.

### Analytics

Vazifa: kun/hafta/oy kesimida statistik tahlil.

### Users

Vazifa: operator/admin foydalanuvchilarni boshqarish.

### Settings

Vazifa: model, kamera, notification, storage va performance sozlamalari.

## Amaldagi Loyiha Holati

Allaqachon moslashtirilgan qismlar:

- Dashboard modulga bo'lingan: `app/ui/pages/dashboard/`.
- Eski import saqlangan: `app/ui/pages/dashboard_page.py`.
- Detection display eski `raw_frame`ga sakramaydi.
- Violation saqlash alohida writer oqimida ishlaydi.
- No Helmet kartalarida crop rasm ko'rsatish qo'shilgan.
- Department Stats rowlari qayta yaratilmasdan yangilanadi.

Keyingi bosqichlar:

- Analytics va Reports sahifalarini shu design systemga to'liq moslash.
- Users va Settings sahifalarida bir xil panel/card pattern ishlatish.
- Presenter/use-case qatlamlarini bosqichma-bosqich ajratish.
