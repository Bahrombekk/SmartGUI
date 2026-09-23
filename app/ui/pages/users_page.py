"""
Employees page - hodimlar ro'yxati, FaceID rasmlari va bo'limlar bo'yicha ko'rinish.
"""

from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QScrollArea,
    QPushButton, QLineEdit, QComboBox, QFileDialog, QMessageBox,
    QGridLayout, QSizePolicy
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap, QPainter, QColor, QPen, QFont

from app.application.services.faceid_service import (
    photos_with_face, store_employee_photos, user_photo_paths,
)
from app.ui.widgets.toast import persist_config, show_toast
from app.ui.widgets.app_dialog import AppMessageBox
from app.ui.theme import C
from app.ui.ui_kit import button_style, input_style, panel_style, soft_card_style


class UserAvatar(QLabel):
    def __init__(self, first_name: str, last_name: str, photo_path: str = "", parent=None):
        super().__init__(parent)
        self._first_name = first_name or ""
        self._last_name = last_name or ""
        self._photo_path = photo_path or ""
        self.setFixedSize(58, 58)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background: transparent; border: none;")
        self._load_photo()

    def _load_photo(self):
        if self._photo_path and Path(self._photo_path).exists():
            pix = QPixmap(self._photo_path)
            if not pix.isNull():
                self.setPixmap(pix.scaled(
                    58, 58,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation
                ))

    def paintEvent(self, event):
        if self.pixmap() and not self.pixmap().isNull():
            super().paintEvent(event)
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(C('success_dim')))
        p.drawRoundedRect(0, 0, self.width(), self.height(), 12, 12)
        p.setPen(QPen(QColor(C('accent'))))
        font = QFont("Segoe UI", 15, QFont.Weight.Bold)
        p.setFont(font)
        initials = ((self._first_name[:1] or "H") + (self._last_name[:1] or "")).upper()
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, initials)
        p.end()


class UserCard(QFrame):
    def __init__(self, user: dict, department_name: str, on_remove, on_add_photos=None, parent=None):
        super().__init__(parent)
        self._user = user
        self._on_remove = on_remove
        self.setFixedHeight(118)
        self.setStyleSheet(f"""
            QFrame {{
                background: {C('bg_card')};
                border: 1px solid {C('border')};
                border-radius: 10px;
            }}
            QFrame:hover {{
                border-color: {C('accent')};
            }}
            QLabel {{ border: none; background: transparent; }}
        """)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 12, 12, 12)
        lay.setSpacing(12)

        lay.addWidget(UserAvatar(
            user.get("first_name", ""),
            user.get("last_name", ""),
            user.get("photo_path", "")
        ))

        info = QVBoxLayout()
        info.setSpacing(4)

        name = QLabel(f"{user.get('first_name', '')} {user.get('last_name', '')}".strip())
        name.setStyleSheet(f"color: {C('text_primary')}; font-size: 15px; font-weight: 700;")
        info.addWidget(name)

        active = bool(user.get("active", True))
        emp_id = QLabel(f"ID: {user.get('employee_id', '')}  |  {'Faol' if active else 'Nofaol'}")
        emp_id.setStyleSheet(f"color: {C('accent')}; font-size: 12px; font-weight: 600;")
        info.addWidget(emp_id)

        dep = QLabel(department_name or "Bo'limsiz")
        dep.setStyleSheet(f"color: {C('text_secondary')}; font-size: 12px;")
        info.addWidget(dep)
        photos = [p for p in user_photo_paths(user) if Path(p).exists()]
        has_photo = bool(photos)
        face_status = (f"FaceID: {len(photos)} ta rasm" if has_photo
                       else "FaceID rasmi yo'q — rasm qo'shing")
        face = QLabel(face_status)
        face.setStyleSheet(
            f"color: {C('success')}; font-size: 11px;" if has_photo
            else f"color: {C('warning')}; font-size: 11px;"
        )
        info.addWidget(face)
        info.addStretch()
        lay.addLayout(info, 1)

        remove_btn = QPushButton("O'chirish")
        remove_btn.setFixedSize(80, 30)
        remove_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #ef4444;
                border: 1px solid rgba(239,68,68,0.35);
                border-radius: 7px;
                font-size: 11px;
                padding: 0;
            }
            QPushButton:hover {
                background: rgba(239,68,68,0.12);
                border-color: #ef4444;
            }
        """)
        remove_btn.clicked.connect(lambda: self._on_remove(user.get("id")))
        btn_col = QVBoxLayout()
        btn_col.setSpacing(6)
        btn_col.addWidget(remove_btn)
        if on_add_photos is not None:
            photo_btn = QPushButton("+ Rasm")
            photo_btn.setFixedSize(80, 30)
            photo_btn.setToolTip("Tanishni yaxshilash uchun turli burchakdan 3–5 ta rasm qo'shing")
            photo_btn.setStyleSheet(button_style("secondary"))
            photo_btn.clicked.connect(lambda: on_add_photos(user.get("id")))
            btn_col.addWidget(photo_btn)
        btn_col.addStretch()
        lay.addLayout(btn_col)


class UsersPage(QWidget):
    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.cfg = config_manager
        self._search_text = ""
        self._dept_combo_items: list[tuple[int, str]] = []
        self._dept_filter_value = "all"
        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        self.setStyleSheet(f"background: {C('bg_main')};")
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(12)

        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("Xodimlar")
        title.setStyleSheet(f"color: {C('text_primary')}; font-size: 20px; font-weight: 800;")
        title_col.addWidget(title)
        subtitle = QLabel("Xodimlar rasmlari, ID raqamlari va bo'limlar bo'yicha ro'yxat")
        subtitle.setStyleSheet(f"color: {C('text_muted')}; font-size: 12px;")
        title_col.addWidget(subtitle)
        header.addLayout(title_col)
        header.addStretch()

        self._total_badge = QLabel("0 ta xodim")
        self._total_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._total_badge.setFixedHeight(32)
        self._total_badge.setStyleSheet(
            f"color: {C('success')}; background: {C('success_dim')};"
            f" border: 1px solid {C('success')}; border-radius: 8px; padding: 0 12px;"
        )
        header.addWidget(self._total_badge)
        root.addLayout(header)

        content = QHBoxLayout()
        content.setSpacing(12)
        root.addLayout(content, 1)

        form = self._build_form()
        content.addWidget(form)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._container = QWidget()
        self._container.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(self._container)
        self._list_layout.setContentsMargins(0, 0, 4, 0)
        self._list_layout.setSpacing(12)
        self._scroll.setWidget(self._container)
        content.addWidget(self._scroll, 1)

    def _build_form(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("userForm")
        panel.setFixedWidth(330)
        panel.setStyleSheet(panel_style("userForm") + " QLabel { border: none; background: transparent; }")

        lay = QVBoxLayout(panel)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        title = QLabel("Xodim qo'shish / FaceID")
        title.setStyleSheet(f"color: {C('text_primary')}; font-size: 15px; font-weight: 800;")
        lay.addWidget(title)

        self._first_name = self._input("Ism")
        self._last_name = self._input("Familiya")
        self._employee_id = self._input("Xodim ID")
        lay.addWidget(self._first_name)
        lay.addWidget(self._last_name)
        lay.addWidget(self._employee_id)

        self._department = QComboBox()
        self._department.setFixedHeight(36)
        self._department.setStyleSheet(input_style())
        lay.addWidget(self._department)

        photo_row = QHBoxLayout()
        self._chosen_photos: list[str] = []
        self._photo_path = QLineEdit()
        self._photo_path.setReadOnly(True)
        self._photo_path.setPlaceholderText("Yuz rasmlari (1–5 ta, turli burchakdan)")
        self._photo_path.setFixedHeight(36)
        self._photo_path.setStyleSheet(input_style())
        photo_row.addWidget(self._photo_path, 1)

        browse = QPushButton("...")
        browse.setFixedSize(42, 36)
        browse.setStyleSheet(button_style("secondary"))
        browse.clicked.connect(self._choose_photo)
        photo_row.addWidget(browse)
        lay.addLayout(photo_row)

        add_btn = QPushButton("+ Xodim qo'shish")
        add_btn.setFixedHeight(38)
        add_btn.setStyleSheet(button_style("primary"))
        add_btn.clicked.connect(self._add_user)
        lay.addWidget(add_btn)

        self._search = self._input("Xodimlarni qidirish...")
        self._search.textChanged.connect(self.set_search_text)
        lay.addWidget(self._search)

        self._dept_filter = QComboBox()
        self._dept_filter.setFixedHeight(36)
        self._dept_filter.setStyleSheet(input_style())
        self._dept_filter.currentIndexChanged.connect(self._on_department_filter_changed)
        lay.addWidget(self._dept_filter)
        lay.addStretch()

        hint = QLabel("Xodimlar mavjud kamera bo'limlariga biriktiriladi.")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {C('text_muted')}; font-size: 11px; line-height: 16px;")
        lay.addWidget(hint)
        return panel

    @staticmethod
    def _input(placeholder: str) -> QLineEdit:
        inp = QLineEdit()
        inp.setPlaceholderText(placeholder)
        inp.setFixedHeight(36)
        inp.setStyleSheet(input_style())
        return inp

    def _pick_photos(self) -> list[str]:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Yuz rasmlarini tanlash", "", "Rasmlar (*.png *.jpg *.jpeg *.bmp)"
        )
        return paths

    def _choose_photo(self):
        paths = self._pick_photos()
        if paths:
            self._chosen_photos = paths
            self._photo_path.setText(
                Path(paths[0]).name if len(paths) == 1 else f"{len(paths)} ta rasm tanlandi"
            )
            self._photo_path.setToolTip("\n".join(paths))

    def _checked_photos(self, paths: list[str]) -> list[str] | None:
        """
        Rasmlarda yuz borligini tekshiradi. Yuzsizlari tashlab yuboriladi.
        None — foydalanuvchi bekor qildi.
        """
        if not paths:
            return []
        ok = photos_with_face(paths)
        good = [p for p, has in zip(paths, ok) if has]
        bad = [Path(p).name for p, has in zip(paths, ok) if not has]
        if not good:
            reply = AppMessageBox.question(
                self, "Yuz topilmadi",
                "Tanlangan rasmlarning birortasida aniq yuz topilmadi "
                "(yuz kichik, yon tomondan yoki xira bo'lishi mumkin).\n\n"
                "Rasmsiz davom etilsinmi? FaceID bu xodimni tanimaydi.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            return [] if reply == QMessageBox.StandardButton.Yes else None
        if bad:
            show_toast(self, f"{len(paths)} ta rasmdan {len(good)} tasida yuz topildi. "
                             f"Yuzsiz: {', '.join(bad[:3])}", "warning", 5000)
        return good

    def _load_departments(self):
        self._department.clear()
        if hasattr(self, "_dept_filter"):
            self._dept_filter.blockSignals(True)
            self._dept_filter.clear()
            self._dept_filter.addItem("Barcha bo'limlar", "all")
        self._dept_combo_items = []
        for dep in self.cfg.get_departments():
            dep_id = dep.get("id")
            name = dep.get("name", "Bo'lim")
            self._dept_combo_items.append((dep_id, name))
            self._department.addItem(name, dep_id)
            if hasattr(self, "_dept_filter"):
                self._dept_filter.addItem(name, dep_id)
        if hasattr(self, "_dept_filter"):
            idx = self._dept_filter.findData(self._dept_filter_value)
            self._dept_filter.setCurrentIndex(idx if idx >= 0 else 0)
            self._dept_filter.blockSignals(False)

    def _add_user(self):
        try:
            dep_id = self._department.currentData()
            emp_id = self._employee_id.text().strip()
            if not (self._first_name.text().strip() and self._last_name.text().strip() and emp_id):
                raise ValueError("Ism, familiya va xodim ID kiritilishi shart")
            photos = self._checked_photos(self._chosen_photos)
            if photos is None:
                return
            stored = store_employee_photos(emp_id, photos) if photos else []
            self.cfg.add_user(
                self._first_name.text(),
                self._last_name.text(),
                emp_id,
                department_id=dep_id,
                photo_paths=stored,
            )
            if not persist_config(self, self.cfg,
                                  f"Xodim qo'shildi: {self._first_name.text().strip()} {self._last_name.text().strip()}"):
                return
            self._first_name.clear()
            self._last_name.clear()
            self._employee_id.clear()
            self._photo_path.clear()
            self._photo_path.setToolTip("")
            self._chosen_photos = []
            self.refresh()
        except Exception as exc:
            AppMessageBox.warning(self, "Xodimlar", str(exc))

    def _remove_user(self, user_id: int):
        if user_id is None:
            return
        user = next((u for u in self.cfg.get_users() if u.get("id") == user_id), {})
        full = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or "Xodim"
        reply = AppMessageBox.question(
            self, "Xodimni o'chirish",
            f'"{full}" o\'chirilsinmi? U endi FaceID orqali tanilmaydi.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.cfg.remove_user(user_id)
        persist_config(self, self.cfg, f"Xodim o'chirildi: {full}")
        self.refresh()

    def _add_photos(self, user_id: int):
        user = next((u for u in self.cfg.get_users() if u.get("id") == user_id), None)
        if user is None:
            return
        photos = self._checked_photos(self._pick_photos())
        if not photos:
            return
        stored = store_employee_photos(user.get("employee_id", ""), photos)
        existing = [p for p in user_photo_paths(user) if Path(p).exists()]
        all_photos = existing + [p for p in stored if p not in existing]
        self.cfg.update_user(user_id, photo_paths=all_photos,
                             photo_path=all_photos[0] if all_photos else "")
        if persist_config(self, self.cfg,
                          f"{len(stored)} ta rasm qo'shildi — FaceID 30 soniya ichida yangilanadi"):
            self.refresh()

    def set_search_text(self, text: str):
        self._search_text = (text or "").strip().lower()
        if hasattr(self, "_list_layout"):
            self._render_users()

    def _on_department_filter_changed(self):
        self._dept_filter_value = self._dept_filter.currentData()
        self._render_users()

    def refresh(self):
        self._load_departments()
        self._render_users()

    def _render_users(self):
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        users = self.cfg.get_users()
        q = self._search_text
        if q:
            users = [
                user for user in users
                if q in " ".join([
                    str(user.get("first_name", "")),
                    str(user.get("last_name", "")),
                    str(user.get("employee_id", "")),
                ]).lower()
            ]
        if self._dept_filter_value != "all":
            users = [user for user in users if user.get("department_id") == self._dept_filter_value]
        self._total_badge.setText(f"{len(users)} ta xodim")

        dep_map = {dep_id: name for dep_id, name in self._dept_combo_items}
        for dep_id, dep_name in self._dept_combo_items:
            dep_users = [u for u in users if u.get("department_id") == dep_id]
            if not dep_users:
                continue
            self._list_layout.addWidget(self._section(dep_name, dep_users, dep_map))

        ungrouped = [u for u in users if u.get("department_id") not in dep_map]
        if ungrouped:
            self._list_layout.addWidget(self._section("Bo'limsiz", ungrouped, dep_map))

        if not users:
            empty = QLabel("Hali xodim qo'shilmagan.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setMinimumHeight(220)
            empty.setStyleSheet(
                f"color: {C('text_muted')}; background: {C('bg_card')};"
                f" border: 1px solid {C('border')};"
                " border-radius: 12px; font-size: 14px;"
            )
            self._list_layout.addWidget(empty)

        self._list_layout.addStretch()

    def _section(self, title: str, users: list, dep_map: dict[int, str]) -> QFrame:
        section = QFrame()
        section.setObjectName("userSection")
        section.setStyleSheet("""
            QFrame#userSection {
                background: transparent;
                border: none;
            }
            QLabel { border: none; background: transparent; }
        """)
        lay = QVBoxLayout(section)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        hdr = QHBoxLayout()
        name = QLabel(title)
        name.setStyleSheet(f"color: {C('text_primary')}; font-size: 14px; font-weight: 800;")
        hdr.addWidget(name)
        count = QLabel(str(len(users)))
        count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        count.setFixedSize(28, 24)
        count.setStyleSheet(
            f"color: {C('accent')}; background: {C('accent_dim')};"
            " border-radius: 8px; font-weight: 700;"
        )
        hdr.addWidget(count)
        hdr.addStretch()
        lay.addLayout(hdr)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(10)
        for i, user in enumerate(users):
            card = UserCard(user, dep_map.get(user.get("department_id"), title), self._remove_user,
                            on_add_photos=self._add_photos)
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            grid.addWidget(card, i // 2, i % 2)
        lay.addLayout(grid)
        return section
