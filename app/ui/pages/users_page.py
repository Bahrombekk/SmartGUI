"""
UsersPage - hodimlar ro'yxati va bo'limlar bo'yicha ko'rinish.
"""

from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QScrollArea,
    QPushButton, QLineEdit, QComboBox, QFileDialog, QMessageBox,
    QGridLayout, QSizePolicy
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap, QPainter, QColor, QPen, QFont

from app.ui.theme import C


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
        p.setBrush(QColor("#1e293b"))
        p.drawRoundedRect(0, 0, self.width(), self.height(), 12, 12)
        p.setPen(QPen(QColor("#fb923c")))
        font = QFont("Segoe UI", 15, QFont.Weight.Bold)
        p.setFont(font)
        initials = ((self._first_name[:1] or "H") + (self._last_name[:1] or "")).upper()
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, initials)
        p.end()


class UserCard(QFrame):
    def __init__(self, user: dict, department_name: str, on_remove, parent=None):
        super().__init__(parent)
        self._user = user
        self._on_remove = on_remove
        self.setFixedHeight(112)
        self.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #0c151c,stop:1 #071016);
                border: 1px solid #1e293b;
                border-radius: 10px;
            }
            QFrame:hover {
                border-color: rgba(249,115,22,0.55);
            }
            QLabel { border: none; background: transparent; }
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
        name.setStyleSheet("color: #ffffff; font-size: 15px; font-weight: 700;")
        info.addWidget(name)

        emp_id = QLabel(f"ID: {user.get('employee_id', '')}")
        emp_id.setStyleSheet("color: #fb923c; font-size: 12px; font-weight: 600;")
        info.addWidget(emp_id)

        dep = QLabel(department_name or "Bo'limsiz")
        dep.setStyleSheet("color: #94a3b8; font-size: 12px;")
        info.addWidget(dep)
        info.addStretch()
        lay.addLayout(info, 1)

        remove_btn = QPushButton("Remove")
        remove_btn.setFixedSize(72, 30)
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
        lay.addWidget(remove_btn, 0, Qt.AlignmentFlag.AlignTop)


class UsersPage(QWidget):
    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.cfg = config_manager
        self._search_text = ""
        self._dept_combo_items: list[tuple[int, str]] = []
        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        self.setStyleSheet("background: #03070b;")
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(12)

        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("Users")
        title.setStyleSheet("color: #ffffff; font-size: 20px; font-weight: 800;")
        title_col.addWidget(title)
        subtitle = QLabel("Hodimlar rasmlari, ID raqamlari va bo'limlar bo'yicha ro'yxat")
        subtitle.setStyleSheet("color: #64748b; font-size: 12px;")
        title_col.addWidget(subtitle)
        header.addLayout(title_col)
        header.addStretch()

        self._total_badge = QLabel("0 users")
        self._total_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._total_badge.setFixedHeight(32)
        self._total_badge.setStyleSheet(
            "color: #34d399; background: rgba(52,211,153,0.08);"
            " border: 1px solid rgba(52,211,153,0.25); border-radius: 8px; padding: 0 12px;"
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
        panel.setStyleSheet("""
            QFrame#userForm {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #0c151c,stop:1 #071016);
                border: 1px solid #1e293b;
                border-radius: 12px;
            }
            QLabel { border: none; background: transparent; }
        """)

        lay = QVBoxLayout(panel)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        title = QLabel("Add Employee")
        title.setStyleSheet("color: #ffffff; font-size: 15px; font-weight: 800;")
        lay.addWidget(title)

        self._first_name = self._input("Ism")
        self._last_name = self._input("Familya")
        self._employee_id = self._input("Hodim ID")
        lay.addWidget(self._first_name)
        lay.addWidget(self._last_name)
        lay.addWidget(self._employee_id)

        self._department = QComboBox()
        self._department.setFixedHeight(36)
        lay.addWidget(self._department)

        photo_row = QHBoxLayout()
        self._photo_path = QLineEdit()
        self._photo_path.setPlaceholderText("Rasm path")
        self._photo_path.setFixedHeight(36)
        photo_row.addWidget(self._photo_path, 1)

        browse = QPushButton("...")
        browse.setFixedSize(42, 36)
        browse.clicked.connect(self._choose_photo)
        photo_row.addWidget(browse)
        lay.addLayout(photo_row)

        add_btn = QPushButton("+ Add Employee")
        add_btn.setFixedHeight(38)
        add_btn.setStyleSheet("""
            QPushButton {
                background: #f97316;
                color: #05090d;
                border: none;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 800;
            }
            QPushButton:hover { background: #fb923c; }
        """)
        add_btn.clicked.connect(self._add_user)
        lay.addWidget(add_btn)

        self._search = self._input("Search users...")
        self._search.textChanged.connect(self.set_search_text)
        lay.addWidget(self._search)
        lay.addStretch()

        hint = QLabel("Hodimlar mavjud kamera bo'limlariga biriktiriladi.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #64748b; font-size: 11px; line-height: 16px;")
        lay.addWidget(hint)
        return panel

    @staticmethod
    def _input(placeholder: str) -> QLineEdit:
        inp = QLineEdit()
        inp.setPlaceholderText(placeholder)
        inp.setFixedHeight(36)
        inp.setStyleSheet("""
            QLineEdit {
                background: rgba(2,6,23,0.72);
                color: #e2e8f0;
                border: 1px solid rgba(148,163,184,0.22);
                border-radius: 7px;
                padding: 0 10px;
                font-size: 13px;
            }
            QLineEdit:hover {
                background: rgba(15,23,42,0.70);
                border-color: rgba(148,163,184,0.38);
            }
            QLineEdit:focus {
                background: rgba(15,23,42,0.86);
                border: 1px solid rgba(251,146,60,0.74);
            }
        """)
        return inp

    def _choose_photo(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Rasm tanlash", "", "Images (*.png *.jpg *.jpeg *.bmp)"
        )
        if path:
            self._photo_path.setText(path)

    def _load_departments(self):
        self._department.clear()
        self._dept_combo_items = []
        for dep in self.cfg.get_departments():
            dep_id = dep.get("id")
            name = dep.get("name", "Bo'lim")
            self._dept_combo_items.append((dep_id, name))
            self._department.addItem(name, dep_id)

    def _add_user(self):
        try:
            dep_id = self._department.currentData()
            self.cfg.add_user(
                self._first_name.text(),
                self._last_name.text(),
                self._employee_id.text(),
                self._photo_path.text(),
                dep_id,
            )
            self.cfg.save()
            self._first_name.clear()
            self._last_name.clear()
            self._employee_id.clear()
            self._photo_path.clear()
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Users", str(exc))

    def _remove_user(self, user_id: int):
        if user_id is None:
            return
        self.cfg.remove_user(user_id)
        self.cfg.save()
        self.refresh()

    def set_search_text(self, text: str):
        self._search_text = (text or "").strip().lower()
        if hasattr(self, "_list_layout"):
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
        self._total_badge.setText(f"{len(users)} users")

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
            empty = QLabel("Hali hodim qo'shilmagan.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setMinimumHeight(220)
            empty.setStyleSheet(
                "color: #64748b; background: #071016; border: 1px solid #1e293b;"
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
        name.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: 800;")
        hdr.addWidget(name)
        count = QLabel(str(len(users)))
        count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        count.setFixedSize(28, 24)
        count.setStyleSheet(
            "color: #fb923c; background: rgba(249,115,22,0.16);"
            " border-radius: 8px; font-weight: 700;"
        )
        hdr.addWidget(count)
        hdr.addStretch()
        lay.addLayout(hdr)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(10)
        for i, user in enumerate(users):
            card = UserCard(user, dep_map.get(user.get("department_id"), title), self._remove_user)
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            grid.addWidget(card, i // 2, i % 2)
        lay.addLayout(grid)
        return section
