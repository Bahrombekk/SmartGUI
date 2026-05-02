# SmartHelmet UI/UX Spec

## Design System

Kanonik tokenlar: `app/ui/design_system.py`

Token guruhlari:

- `COLORS`: dark theme, status, border, camera status ranglari
- `TYPOGRAPHY`: font family, font size, weight
- `SPACING`: 4/8/12/16/24/32 ritm
- `RADIUS`: 4/6/8/10/pill
- `MOTION`: fast/normal/slow animation vaqtlar
- `SHADOWS`: panel va popover shadow tavsiflari

Eski moslik:

- Mavjud kod `app.ui.theme.C()` orqali ishlashda davom etadi.
- `C()` endi avval `design_system.COLORS`dan o'qiydi.

## Layout Qoidalari

- Dashboard birinchi ekran bo'ladi, landing page ishlatilmaydi.
- Kamera grid eng katta vizual maydon bo'ladi.
- Pastki panellar 260px atrofida qoladi.
- Cards radiusi odatda 8px.
- Qizil rang faqat haqiqiy danger/violation holatlarida ishlatiladi.
- Har bir dinamik panel ichidagi widgetlar imkon qadar qayta yaratilmaydi, faqat qiymatlar yangilanadi.

## Dashboard Komponentlari

### Monitor Header

Elementlar:

- `Live Monitoring` title
- camera count badge
- grid column buttons
- stream filter
- expand button

State:

- active grid column button orange accent border bilan ajraladi
- icon topilmasa fallback text chiqadi

### Camera Grid

Maqsad:

- real-time videoni silliq ko'rsatish
- selected camera holatini saqlash
- filter/search bo'yicha tez render qilish

### Department Stats

Maqsad:

- bo'lim bo'yicha kamera soni, online/offline va bugungi detectionni ko'rsatish

Behavior:

- bo'lim ro'yxati o'zgarsa rowlar rebuild bo'ladi
- stats o'zgarsa mavjud row label/progresslari yangilanadi

### No Helmet

Maqsad:

- oxirgi shlemsiz holatlarni crop rasm bilan tez ko'rsatish

Card tarkibi:

- crop thumbnail
- `NO HELMET` badge
- time chip
- track ID
- camera name

Fallback:

- `crop_path` bo'sh yoki fayl topilmasa `NO IMG` chiqadi

## Motion Qoidalari

- Qiymat oshishi mumkin, lekin butun panel lipillamasligi kerak.
- Real-time stats update UI hierarchy yoki layoutni siljitmasligi kerak.
- Kamera frame update va detection overlay UI threadni bloklamasligi kerak.
