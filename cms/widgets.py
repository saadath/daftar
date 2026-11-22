from __future__ import annotations

import math
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import jdatetime
from PySide6.QtCore import Qt, QDate, QTime, QUrl, Signal, QRegularExpression, QRectF
from PySide6.QtGui import (
    QDesktopServices, QFont, QTextListFormat, QRegularExpressionValidator,
    QTextBlockFormat, QTextCharFormat, QTextCursor, QImageReader, QPixmap,
    QPainter, QPen, QColor, QIcon,
)
from PySide6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QLineEdit, QPlainTextEdit, QTextEdit, QTextBrowser, QComboBox, QSpinBox,
    QCalendarWidget, QDialog, QDialogButtonBox, QFileDialog,
    QMessageBox, QCheckBox, QButtonGroup, QRadioButton, QStackedWidget,
    QToolButton, QFormLayout, QScrollArea, QStyle,
)
from PySide6.QtCore import QSize

from cms.storage import attachment_items, validate_attachment_name
from cms.i18n import t, direction, is_rtl, current_language


def info_icon(size=20, color="#c9c0ff"):
    """A crisp painted "information" badge used by navigation controls."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    accent = QColor(color)
    painter.setBrush(QColor(accent.red(), accent.green(), accent.blue(), 44))
    painter.setPen(QPen(accent, max(1.2, size * 0.065)))
    margin = size * 0.055
    painter.drawEllipse(QRectF(margin, margin, size - 2 * margin, size - 2 * margin))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(accent)
    dot = max(1.7, size * 0.115)
    painter.drawEllipse(QRectF((size - dot) / 2, size * 0.285, dot, dot))
    painter.drawRoundedRect(QRectF((size - dot) / 2, size * 0.465, dot, size * 0.265), dot / 2, dot / 2)
    painter.end()
    return QIcon(pixmap)


def button(text, callback=None, kind=None, icon=None):
    result = QPushButton("" if kind == "nav" else text)
    result.setCursor(Qt.CursorShape.PointingHandCursor)
    if kind:
        result.setObjectName(kind)
    if kind == "nav":
        raw = text.strip()
        if raw.startswith("▦"):
            glyph, caption_text = "▦", raw[1:].strip()
        elif raw.startswith("＋"):
            glyph, caption_text = "＋", raw[1:].strip()
        elif raw.startswith("بازیابی"):
            glyph, caption_text = "↶", raw
        elif raw.startswith("پوشه") or raw.lower().startswith("data"):
            glyph, caption_text = "▣", raw
        elif raw.startswith("تنظیمات") or raw.lower().startswith("settings"):
            glyph, caption_text = "⚙", raw
        else:
            glyph, caption_text = "•", raw
        result.setLayoutDirection(direction())
        result.setAccessibleName(caption_text)
        result.setMinimumHeight(48)
        result.setFlat(True)
        content = QHBoxLayout(result)
        content.setContentsMargins(12, 5, 12, 5)
        content.setSpacing(10)
        glyph_label = QLabel(glyph, result)
        glyph_label.setObjectName("navIcon")
        glyph_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        glyph_label.setFixedWidth(24)
        glyph_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        if icon is not None:
            glyph_label.setText("")
            glyph_label.setPixmap(icon.pixmap(20, 20))
        content.addWidget(glyph_label)
        caption = QLabel(caption_text, result)
        caption.setObjectName("navText")
        caption.setAlignment((Qt.AlignmentFlag.AlignRight if is_rtl() else Qt.AlignmentFlag.AlignLeft) | Qt.AlignmentFlag.AlignVCenter)
        caption.setLayoutDirection(direction())
        caption.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        content.addWidget(caption, 1)
    if callback:
        result.clicked.connect(callback)
    return result


def label(text, name=None):
    result = QLabel(text)
    result.setTextFormat(Qt.TextFormat.PlainText)
    if name:
        result.setObjectName(name)
    result.setWordWrap(True)
    return result


class DatePicker(QWidget):
    """Paired Jalali and Gregorian date controls backed by one ISO value."""
    def __init__(self, value=None, calendar="gregorian", parent=None):
        super().__init__(parent)
        self.selected = date.fromisoformat(value[:10]) if value else None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        calendars = QHBoxLayout()
        calendars.setSpacing(12)

        jalali_panel = QFrame()
        jalali_panel.setObjectName("datePanel")
        jalali_layout = QVBoxLayout(jalali_panel)
        jalali_layout.setContentsMargins(12, 10, 12, 10)
        jalali_layout.addWidget(label(t("date.jalali"), "section"))
        self.jalali_button = button("", lambda: self.popup("jalali"))
        self.jalali_button.setAccessibleName(t("date.select_jalali"))
        jalali_layout.addWidget(self.jalali_button)

        gregorian_panel = QFrame()
        gregorian_panel.setObjectName("datePanel")
        gregorian_layout = QVBoxLayout(gregorian_panel)
        gregorian_layout.setContentsMargins(12, 10, 12, 10)
        gregorian_layout.addWidget(label(t("date.gregorian"), "section"))
        self.gregorian_button = button("", lambda: self.popup("gregorian"))
        self.gregorian_button.setAccessibleName(t("date.select_gregorian"))
        gregorian_layout.addWidget(self.gregorian_button)
        panels = (jalali_panel, gregorian_panel) if calendar == "jalali" else (gregorian_panel, jalali_panel)
        for panel in panels:
            calendars.addWidget(panel, 1)
        layout.addLayout(calendars)
        self.clear_button = button(t("date.clear"), lambda: self.set_date(None))
        footer = QHBoxLayout()
        footer.addWidget(button(t("date.today"), lambda: self.set_date(date.today())))
        footer.addWidget(self.clear_button)
        footer.addStretch()
        layout.addLayout(footer)
        self.set_date(self.selected)

    def set_date(self, value):
        self.selected = value
        jalali = t("date.select")
        if value:
            try:
                jalali = jdatetime.date.fromgregorian(date=value).strftime("%Y/%m/%d")
            except ValueError:
                jalali = t("date.out_of_range")
        self.jalali_button.setText(jalali)
        self.gregorian_button.setText(value.isoformat() if value else t("date.select"))
        self.clear_button.setEnabled(value is not None)

    def today(self):
        self.set_date(date.today())

    def popup(self, kind="jalali"):
        current = self.selected or date.today()
        if kind == "jalali":
            try:
                dialog = JalaliCalendar(current, self)
            except ValueError:
                dialog = JalaliCalendar(date.today(), self)
            if dialog.exec():
                self.set_date(dialog.selected.togregorian())
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(t("date.pick_gregorian_title"))
        layout = QVBoxLayout(dialog)
        calendar = QCalendarWidget()
        calendar.setDateRange(QDate(1, 1, 1), QDate(9999, 12, 31))
        calendar.setSelectedDate(QDate(current.year, current.month, current.day))
        layout.addWidget(calendar)
        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        actions.accepted.connect(dialog.accept)
        actions.rejected.connect(dialog.reject)
        calendar.clicked.connect(lambda *_: dialog.accept())
        calendar.activated.connect(lambda *_: dialog.accept())
        layout.addWidget(actions)
        if dialog.exec():
            self.set_date(calendar.selectedDate().toPython())

    def get_date(self):
        return self.selected

    def value(self):
        return self.selected.isoformat() if self.selected else None


class JalaliCalendar(QDialog):
    """Saturday-first month grid with real Jalali month boundaries."""
    MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]

    def __init__(self, value, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("date.pick_jalali_title"))
        self.setLayoutDirection(direction())
        self.selected = jdatetime.date.fromgregorian(date=value)
        self.year, self.month = self.selected.year, self.selected.month
        self.setMinimumWidth(450)
        layout = QVBoxLayout(self)
        navigation = QHBoxLayout()
        navigation.addWidget(button(t("date.prev_month"), lambda: self.navigate(-1)))
        self.month_picker = QComboBox()
        self.month_picker.addItems(self.MONTHS)
        self.month_picker.setAccessibleName(t("date.jalali_month"))
        self.year_picker = QSpinBox()
        self.year_picker.setRange(1, 9377)
        self.year_picker.setKeyboardTracking(False)
        self.year_picker.setAccessibleName(t("date.jalali_year"))
        self.year_picker.setToolTip(t("date.year_tooltip"))
        navigation.addWidget(self.month_picker, 1)
        navigation.addWidget(self.year_picker)
        navigation.addWidget(button(t("date.next_month"), lambda: self.navigate(1)))
        layout.addLayout(navigation)
        self.grid = QGridLayout()
        layout.addLayout(self.grid)
        footer = QHBoxLayout()
        footer.addWidget(button(t("date.today"), self.select_today))
        footer.addStretch()
        footer.addWidget(button(t("action.cancel"), self.reject))
        layout.addLayout(footer)
        self.render()
        self.year_picker.valueChanged.connect(self.jump)
        self.month_picker.currentIndexChanged.connect(self.jump)

    def jump(self):
        self.year = self.year_picker.value()
        self.month = self.month_picker.currentIndex() + 1
        self.render()

    def render(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for control, setter, value in ((self.year_picker, self.year_picker.setValue, self.year),
                                       (self.month_picker, self.month_picker.setCurrentIndex, self.month - 1)):
            control.blockSignals(True)
            setter(value)
            control.blockSignals(False)
        for col, name in enumerate(t("date.weekdays")):
            title = label(name, "muted")
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.grid.addWidget(title, 0, col)
        first = jdatetime.date(self.year, self.month, 1)
        offset = first.weekday()
        count = 31 if self.month <= 6 else (30 if self.month <= 11 or first.isleap() else 29)
        today = jdatetime.date.today()
        for day in range(1, count + 1):
            value = jdatetime.date(self.year, self.month, day)
            cell = button(str(day), lambda checked=False, value=value: self.choose(value), "primary" if value == self.selected else None)
            if value == today:
                cell.setToolTip(t("date.today"))
                if value != self.selected:
                    cell.setStyleSheet("border: 2px solid #8272df; color: #6353cc;")
            cell.setMinimumSize(45, 38)
            position = offset + day - 1
            self.grid.addWidget(cell, position // 7 + 1, position % 7)

    def navigate(self, step):
        month_index = self.year * 12 + self.month - 1 + step
        year, month = divmod(month_index, 12)
        if 1 <= year <= 9377:
            self.year, self.month = year, month + 1
            self.render()

    def choose(self, value):
        self.selected = value
        self.accept()

    def select_today(self):
        self.choose(jdatetime.date.today())


class RichEditor(QWidget):
    def __init__(self, value="", html_mode=False):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        toolbar_widget = QWidget()
        toolbar_widget.setObjectName("richToolbar")
        toolbar_container = QVBoxLayout(toolbar_widget)
        toolbar_container.setContentsMargins(5, 5, 5, 5)
        toolbar_container.setSpacing(4)
        toolbar_row = QWidget(toolbar_widget)
        toolbar = QGridLayout(toolbar_row)
        toolbar.setContentsMargins(5, 5, 5, 5)
        toolbar.setHorizontalSpacing(4)
        toolbar.setVerticalSpacing(4)
        toolbar.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._toolbar_slot = 0
        self.editor = QTextEdit()
        self.editor.setMinimumHeight(180)
        self.editor.setAcceptRichText(True)
        self.editor.setAcceptRichText(True)
        self.editor.setHtml(value or "")
        self._tool(toolbar, "↦", t("rich.rtl"), lambda: self.set_direction(Qt.LayoutDirection.RightToLeft))
        self._tool(toolbar, "↤", t("rich.ltr"), lambda: self.set_direction(Qt.LayoutDirection.LeftToRight))
        self._separator(toolbar)
        self._tool(toolbar, "≡", t("rich.align_right"), lambda: self.set_alignment(Qt.AlignmentFlag.AlignRight))
        self._tool(toolbar, "☰", t("rich.align_center"), lambda: self.set_alignment(Qt.AlignmentFlag.AlignHCenter))
        self._tool(toolbar, "≡", t("rich.align_left"), lambda: self.set_alignment(Qt.AlignmentFlag.AlignLeft))
        self._separator(toolbar)
        self._tool(toolbar, "B", t("rich.bold"), self.bold, bold=True, shortcut="Ctrl+B")
        self._tool(toolbar, "I", t("rich.italic"), self.italic, italic=True, shortcut="Ctrl+I")
        self._tool(toolbar, "U", t("rich.underline"), self.underline, underline=True, shortcut="Ctrl+U")
        self._separator(toolbar)
        for level in range(1, 7):
            # QToolButton.clicked carries a checked bool; consume it explicitly
            # so it cannot replace the captured heading level.
            self._tool(
                toolbar, f"H{level}", t("rich.heading", level=level),
                lambda checked=False, level=level: self.set_heading(level),
            )
        self._separator(toolbar)
        self._tool(toolbar, "•≡", t("rich.bullets"), lambda: self.insert_list(QTextListFormat.Style.ListDisc))
        self._tool(toolbar, "1≡", t("rich.numbers"), lambda: self.insert_list(QTextListFormat.Style.ListDecimal))
        self._tool(toolbar, "―", t("rich.hr"), self.insert_horizontal_rule)
        self._tool(toolbar, "🔗", t("rich.link"), self.insert_link)
        self._tool(toolbar, "▦", t("rich.table"), self.insert_table)
        self.stack = QStackedWidget()
        self.source = QPlainTextEdit()
        self.source.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.source.setMinimumHeight(180)
        self.stack.addWidget(self.editor)
        self.stack.addWidget(self.source)
        self.toggle = button(t("rich.edit_html"), self.toggle_source)
        self.toggle.setToolTip(t("rich.html_tooltip"))
        toolbar_container.addWidget(toolbar_row)
        toggle_row = QHBoxLayout()
        toggle_row.setContentsMargins(0, 0, 0, 0)
        toggle_row.addWidget(self.toggle, 0, Qt.AlignmentFlag.AlignLeft)
        toggle_row.addStretch()
        toolbar_container.addLayout(toggle_row)
        layout.addWidget(toolbar_widget)
        layout.addWidget(self.stack)
        if html_mode:
            self.source.setPlainText(value or "")
            self.editor.setHtml(value or "")

    def _tool(self, layout, glyph, tooltip, callback, bold=False, italic=False, underline=False, shortcut=None):
        tool = QToolButton(self)
        tool.setText(glyph)
        tool.setToolTip(tooltip + (f"  ({shortcut})" if shortcut else ""))
        tool.setAccessibleName(tooltip)
        tool.setCursor(Qt.CursorShape.PointingHandCursor)
        tool.setFixedSize(34, 32)
        tool.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        tool.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        font = tool.font()
        font.setBold(bold or glyph.startswith("H"))
        font.setItalic(italic)
        font.setUnderline(underline)
        tool.setFont(font)
        tool.clicked.connect(callback)
        layout.addWidget(tool, self._toolbar_slot // 10, self._toolbar_slot % 10)
        self._toolbar_slot += 1
        return tool

    @staticmethod
    def _separator(layout):
        # The two-row grid keeps the complete toolbar visible even on narrower
        # windows; spacing between groups replaces tall separator widgets.
        return None

    def _apply_block_format(self, block_format):
        cursor = self.editor.textCursor()
        cursor.beginEditBlock()
        cursor.mergeBlockFormat(block_format)
        self.editor.setTextCursor(cursor)
        cursor.endEditBlock()

    def set_direction(self, direction):
        block_format = QTextBlockFormat()
        block_format.setLayoutDirection(direction)
        self._apply_block_format(block_format)

    def set_alignment(self, alignment):
        block_format = QTextBlockFormat()
        block_format.setAlignment(alignment)
        self._apply_block_format(block_format)

    def set_heading(self, level):
        level = max(1, min(6, int(level)))
        editor = self.editor
        cursor = editor.textCursor()
        selected = cursor.hasSelection()
        start, end = cursor.selectionStart(), cursor.selectionEnd()
        sizes = {1: 24, 2: 20, 3: 17, 4: 15, 5: 13, 6: 11}
        char_format = QTextCharFormat()
        char_format.setFontPointSize(sizes[level])
        char_format.setFontWeight(QFont.Weight.Bold)
        cursor.beginEditBlock()
        first_block = editor.document().findBlock(start)
        last_block = editor.document().findBlock(end if selected else start)
        block = first_block
        while block.isValid():
            block_cursor = QTextCursor(block)
            block_format = block.blockFormat()
            block_format.setHeadingLevel(level)
            block_cursor.setBlockFormat(block_format)
            block_cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
            block_cursor.mergeCharFormat(char_format)
            if block.position() >= last_block.position():
                break
            block = block.next()
        cursor.endEditBlock()
        if selected:
            cursor.setPosition(start)
            cursor.setPosition(end, cursor.MoveMode.KeepAnchor)
        editor.setTextCursor(cursor)
        editor.setFocus(Qt.FocusReason.OtherFocusReason)

    def insert_list(self, style):
        cursor = self.editor.textCursor()
        cursor.createList(style)
        self.editor.setTextCursor(cursor)

    def insert_horizontal_rule(self):
        cursor = self.editor.textCursor()
        cursor.insertHtml("<hr>")
        self.editor.setTextCursor(cursor)

    def insert_link(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(t("rich.link_title"))
        form = QFormLayout(dialog)
        url = QLineEdit()
        url.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        url.setPlaceholderText("https://example.com")
        text = QLineEdit(self.editor.textCursor().selectedText())
        text.setPlaceholderText(t("rich.link_ph"))
        form.addRow(t("rich.link_url"), url)
        form.addRow(t("rich.link_text"), text)
        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        actions.accepted.connect(dialog.accept)
        actions.rejected.connect(dialog.reject)
        form.addRow(actions)
        if not dialog.exec() or not url.text().strip():
            return
        href = url.text().strip()
        display = text.text().strip() or href
        cursor = self.editor.textCursor()
        char_format = QTextCharFormat()
        char_format.setAnchor(True)
        char_format.setAnchorHref(href)
        char_format.setForeground(self.editor.palette().link())
        char_format.setFontUnderline(True)
        cursor.insertText(display, char_format)
        self.editor.setTextCursor(cursor)

    def insert_table(self):
        from PySide6.QtWidgets import QInputDialog
        rows, accepted = QInputDialog.getInt(self, t("rich.table"), t("rich.table_rows"), 3, 1, 50)
        if not accepted:
            return
        columns, accepted = QInputDialog.getInt(self, t("rich.table"), t("rich.table_cols"), 3, 1, 20)
        if not accepted:
            return
        self.insert_table_dimensions(rows, columns)

    def insert_table_dimensions(self, rows, columns):
        rows = max(1, min(50, int(rows)))
        columns = max(1, min(20, int(columns)))
        cursor = self.editor.textCursor()
        cursor.insertTable(rows, columns)
        self.editor.setTextCursor(cursor)

    def bold(self):
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Weight.Bold if self.editor.fontWeight() < QFont.Weight.Bold else QFont.Weight.Normal)
        self.editor.mergeCurrentCharFormat(fmt)

    def italic(self):
        fmt = QTextCharFormat()
        fmt.setFontItalic(not self.editor.fontItalic())
        self.editor.mergeCurrentCharFormat(fmt)

    def underline(self):
        fmt = QTextCharFormat()
        fmt.setFontUnderline(not self.editor.fontUnderline())
        self.editor.mergeCurrentCharFormat(fmt)

    def toggle_source(self):
        if self.stack.currentIndex() == 0:
            self.source.setPlainText(self._html_fragment(self.editor.toHtml()))
            self.stack.setCurrentIndex(1)
            self.toggle.setText(t("rich.show_editor"))
        else:
            self.editor.setHtml(self._html_fragment(self.source.toPlainText()))
            self.stack.setCurrentIndex(0)
            self.toggle.setText(t("rich.edit_html"))

    @staticmethod
    def _html_fragment(content):
        """Return only document-body markup, keeping HTML fields as fragments."""
        content = str(content or "").strip()
        body = re.search(r"<body\b[^>]*>(.*?)</body\s*>", content, re.IGNORECASE | re.DOTALL)
        if body:
            return body.group(1).strip()
        content = re.sub(r"<!doctype\b[^>]*>", "", content, flags=re.IGNORECASE)
        content = re.sub(r"<head\b[^>]*>.*?</head\s*>", "", content, flags=re.IGNORECASE | re.DOTALL)
        content = re.sub(r"</?html\b[^>]*>", "", content, flags=re.IGNORECASE)
        content = re.sub(r"</?body\b[^>]*>", "", content, flags=re.IGNORECASE)
        return content.strip()

    def value(self):
        raw_content = self.source.toPlainText() if self.stack.currentIndex() else self.editor.toHtml()
        content = self._html_fragment(raw_content)
        check = QTextEdit()
        check.setHtml(content)
        return content if check.toPlainText().strip() or "<img" in content.lower() else ""


class _ClockFace(QWidget):
    valueSelected = Signal(QTime)

    def __init__(self, value, mode="hour", parent=None):
        super().__init__(parent)
        self.value = value
        self.mode = mode
        self.setMinimumSize(280, 280)
        self.setMaximumSize(340, 340)

    def set_value(self, value):
        self.value = value
        self.update()

    def set_mode(self, mode):
        self.mode = mode
        self.update()

    def _center(self):
        side = min(self.width(), self.height())
        return self.width() / 2, self.height() / 2, side * 0.43

    def _selected_point(self):
        cx, cy, radius = self._center()
        if self.mode == "hour":
            hour = self.value.hour()
            ring = radius if hour < 12 else radius * 0.63
            hour %= 12
            angle = math.radians(hour * 30 - 90)
        else:
            minute = self.value.minute()
            ring = radius
            angle = math.radians(minute * 6 - 90)
        return cx + math.cos(angle) * ring, cy + math.sin(angle) * ring

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy, radius = self._center()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#f0effb"))
        painter.drawEllipse(int(cx - radius), int(cy - radius), int(2 * radius), int(2 * radius))
        sx, sy = self._selected_point()
        painter.setPen(QPen(QColor("#7566d8"), 2))
        painter.drawLine(int(cx), int(cy), int(sx), int(sy))

        if self.mode == "hour":
            values = range(24)
            for value in values:
                ring = radius if value < 12 else radius * 0.63
                angle = math.radians((value % 12) * 30 - 90)
                x, y = cx + math.cos(angle) * ring, cy + math.sin(angle) * ring
                selected = value == self.value.hour()
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor("#7566d8") if selected else QColor("#ffffff"))
                dot = 28 if value < 12 else 25
                painter.drawEllipse(int(x - dot / 2), int(y - dot / 2), dot, dot)
                painter.setPen(QColor("#ffffff") if selected else QColor("#34435d"))
                painter.setFont(QFont("Vazirmatn", 9, QFont.Weight.DemiBold if selected else QFont.Weight.Normal))
                painter.drawText(int(x - 17), int(y - 12), 34, 24, Qt.AlignmentFlag.AlignCenter, f"{value:02d}")
        else:
            for value in range(60):
                angle = math.radians(value * 6 - 90)
                x, y = cx + math.cos(angle) * radius, cy + math.sin(angle) * radius
                selected = value == self.value.minute()
                if value % 5 == 0 or selected:
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor("#7566d8") if selected else QColor("#ffffff"))
                    dot = 27 if selected else 23
                    painter.drawEllipse(int(x - dot / 2), int(y - dot / 2), dot, dot)
                    painter.setPen(QColor("#ffffff") if selected else QColor("#34435d"))
                    painter.setFont(QFont("Vazirmatn", 8, QFont.Weight.DemiBold if selected else QFont.Weight.Normal))
                    painter.drawText(int(x - 15), int(y - 11), 30, 22, Qt.AlignmentFlag.AlignCenter, f"{value:02d}")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#7566d8"))
        painter.drawEllipse(int(cx - 5), int(cy - 5), 10, 10)

    def mousePressEvent(self, event):
        cx, cy, radius = self._center()
        dx, dy = event.position().x() - cx, event.position().y() - cy
        distance = math.hypot(dx, dy)
        angle = (math.degrees(math.atan2(dy, dx)) + 90) % 360
        if self.mode == "hour":
            hour = int(round(angle / 30)) % 12
            if distance < radius * 0.80:
                hour += 12
            updated = QTime(self.value)
            updated.setHMS(hour, self.value.minute(), 0)
            self.value = updated
        else:
            minute = int(round(angle / 6)) % 60
            updated = QTime(self.value)
            updated.setHMS(self.value.hour(), minute, 0)
            self.value = updated
        self.update()
        self.valueSelected.emit(self.value)
        super().mousePressEvent(event)


class ClockTimeDialog(QDialog):
    def __init__(self, value, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("time.select"))
        self.setMinimumWidth(360)
        self.value = value if value.isValid() else QTime.currentTime()
        self.mode = "hour"
        layout = QVBoxLayout(self)
        # Keep the displayed order explicit even though the application is RTL:
        # the hour is always on the left and the minute on the right.
        self.clock_header = QWidget(self)
        self.clock_header.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        clock_header = QHBoxLayout(self.clock_header)
        clock_header.setDirection(QHBoxLayout.Direction.LeftToRight)
        self.hour_button = QToolButton()
        self.hour_button.setObjectName("clockValue")
        self.hour_button.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.minute_button = QToolButton()
        self.minute_button.setObjectName("clockValue")
        self.minute_button.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        colon = label(":", "section")
        clock_header.addStretch()
        clock_header.addWidget(self.hour_button)
        clock_header.addWidget(colon)
        clock_header.addWidget(self.minute_button)
        clock_header.addStretch()
        layout.addWidget(self.clock_header)
        self.face = _ClockFace(self.value)
        self.face.valueSelected.connect(self._clock_selected)
        layout.addWidget(self.face, 0, Qt.AlignmentFlag.AlignCenter)
        self.phase = label(t("time.hour_first"), "muted")
        self.phase.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.phase)
        footer = QHBoxLayout()
        footer.addWidget(button(t("time.now"), self.set_now))
        footer.addStretch()
        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        actions.accepted.connect(self.accept)
        actions.rejected.connect(self.reject)
        footer.addWidget(actions)
        layout.addLayout(footer)
        self.hour_button.clicked.connect(lambda: self.set_mode("hour"))
        self.minute_button.clicked.connect(lambda: self.set_mode("minute"))
        self._refresh()

    def _refresh(self):
        self.hour_button.setText(self.value.toString("HH"))
        self.minute_button.setText(self.value.toString("mm"))
        self.face.set_value(self.value)
        self.face.set_mode(self.mode)
        self.phase.setText(t("time.hour") if self.mode == "hour" else t("time.minute"))

    def set_mode(self, mode):
        self.mode = mode
        self._refresh()

    def _clock_selected(self, value):
        self.value = value
        if self.mode == "hour":
            self.mode = "minute"
        self._refresh()

    def set_now(self):
        self.value = QTime.currentTime()
        self._refresh()


class ClockTimeInput(QLineEdit):
    timeChanged = Signal(QTime)

    def __init__(self, value=None, parent=None):
        super().__init__(parent)
        self._time = value if isinstance(value, QTime) and value.isValid() else QTime.currentTime()
        self.setReadOnly(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setPlaceholderText("--:--")
        self._display()

    def _display(self):
        self.setText(self._time.toString("HH:mm"))

    def displayFormat(self):
        return "HH:mm"

    def time(self):
        return self._time

    def setTime(self, value):
        if value.isValid():
            self._time = value
            self._display()
            self.timeChanged.emit(value)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            dialog = ClockTimeDialog(self._time, self)
            if dialog.exec():
                self.setTime(dialog.value)
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            dialog = ClockTimeDialog(self._time, self)
            if dialog.exec():
                self.setTime(dialog.value)
            return
        super().keyPressEvent(event)


class Attachment(QWidget):
    def __init__(self, store, project_id, kind, value=None, field=None):
        super().__init__()
        self.store, self.project_id, self.kind = store, project_id, kind
        from cms.storage import attachment_items
        self.field = field or {"type": kind}
        self.existing = attachment_items(value)
        self.pending = []
        self._icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.name = label("", "muted")
        row.addWidget(self.name, 1)
        row.addWidget(button(t("attach.add"), self.choose))
        row.addWidget(button(t("attach.clear"), self.clear))
        layout.addLayout(row)
        self.preview_area = QScrollArea()
        self.preview_area.setWidgetResizable(True)
        self.preview_area.setObjectName("attachmentPreviewArea")
        self.preview_area.setMinimumHeight(350)
        self.preview_area.setMaximumHeight(430)
        self.preview_body = QWidget()
        self.preview_layout = QGridLayout(self.preview_body)
        self.preview_layout.setContentsMargins(4, 4, 4, 4)
        self.preview_layout.setSpacing(8)
        self.preview_area.setWidget(self.preview_body)
        layout.addWidget(self.preview_area)
        self.show_preview()

    def _allowed_extensions(self):
        from cms.storage import attachment_extensions
        return attachment_extensions(self.field)

    def _filter(self):
        allowed = self._allowed_extensions()
        if not allowed:
            return t("attach.all_files")
        patterns = " ".join(f"*.{extension}" for extension in sorted(allowed))
        return t("attach.allowed", patterns=patterns)

    def choose(self):
        paths, _ = QFileDialog.getOpenFileNames(self, t("attach.pick"), "", self._filter())
        for path in paths:
            try:
                self._validate_path(path)
                if path not in self.pending:
                    self.pending.append(path)
            except ValueError as exc:
                QMessageBox.warning(self, t("attach.invalid"), str(exc))
        self.show_preview()

    def _validate_path(self, path):
        from cms.storage import validate_attachment_name
        validate_attachment_name(self.field, Path(path).name)
        if self.kind == "image":
            reader = QImageReader(path)
            if not reader.canRead():
                raise ValueError(f"فایل «{Path(path).name}» تصویر قابل‌خواندن نیست.")

    def _entries(self):
        return [("existing", index, item) for index, item in enumerate(self.existing)] + [
            ("pending", index, {"name": Path(path).name, "source": path})
            for index, path in enumerate(self.pending)
        ]

    def show_preview(self):
        while self.preview_layout.count():
            item = self.preview_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        entries = self._entries()
        self.name.setText(t("attach.count", count=len(entries)) if entries else t("attach.none"))
        for position, (bucket, index, attachment) in enumerate(entries):
            card = QFrame()
            card.setObjectName("attachmentPreview")
            card.setMinimumSize(232, 288)
            card_layout = QGridLayout(card)
            card_layout.setContentsMargins(8, 8, 8, 8)
            card_layout.setSpacing(4)
            preview_container = QWidget(card)
            preview_container.setFixedSize(210, 205)
            preview_grid = QGridLayout(preview_container)
            preview_grid.setContentsMargins(0, 0, 0, 0)
            preview_grid.setSpacing(0)

            preview = QLabel()
            preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
            preview.setFixedSize(210, 205)
            preview.setObjectName("attachmentThumbnail")
            path = self._entry_path(bucket, attachment)
            pixmap = QPixmap()
            if self.kind == "image" and path and path.is_file():
                pixmap = QPixmap(str(path))
                if not pixmap.isNull():
                    preview.setPixmap(pixmap.scaled(preview.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            if pixmap.isNull():
                preview.setPixmap(self._icon.pixmap(QSize(42, 42)))
            preview_grid.addWidget(preview, 0, 0)

            # This overlay belongs to the current thumbnail itself, so the
            # actions remain on the correct image/file instead of appearing
            # beside the card or in a shared toolbar.
            actions_overlay = QWidget(preview_container)
            actions_overlay.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            actions_overlay.setStyleSheet("background: transparent;")
            actions_overlay.setFixedSize(82, 46)
            actions_layout = QHBoxLayout(actions_overlay)
            actions_layout.setContentsMargins(3, 3, 3, 3)
            actions_layout.setSpacing(4)
            actions_layout.setDirection(QHBoxLayout.Direction.LeftToRight)
            open_button = QToolButton(actions_overlay)
            open_button.setIcon(self._open_icon())
            open_button.setToolTip(t("attach.open"))
            open_button.setAccessibleName(t("attach.open"))
            open_button.setObjectName("attachmentIconButton")
            open_button.setFixedSize(34, 34)
            open_button.clicked.connect(lambda checked=False, bucket=bucket, attachment=attachment: self.open_entry(bucket, attachment))
            actions_layout.addWidget(open_button)
            delete_button = QToolButton(actions_overlay)
            delete_button.setIcon(self._delete_icon())
            delete_button.setToolTip(t("attach.delete"))
            delete_button.setAccessibleName(t("attach.delete"))
            delete_button.setObjectName("attachmentDeleteButton")
            delete_button.setFixedSize(34, 34)
            delete_button.setIconSize(QSize(20, 20))
            delete_button.clicked.connect(lambda checked=False, bucket=bucket, index=index: self.remove(bucket, index))
            actions_layout.addWidget(delete_button)
            preview_grid.addWidget(actions_overlay, 0, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
            actions_overlay.raise_()
            actions_overlay.show()
            card_layout.addWidget(preview_container, 0, 0, 1, 3, Qt.AlignmentFlag.AlignCenter)
            name = label(attachment["name"])
            name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name.setToolTip(attachment["name"])
            card_layout.addWidget(name, 1, 0, 1, 3)
            self.preview_layout.addWidget(card, position // 3, position % 3)

    @staticmethod
    def _open_icon():
        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#5142b4"), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawRoundedRect(3, 8, 12, 12, 2, 2)
        painter.drawLine(11, 13, 20, 4)
        painter.drawLine(14, 4, 20, 4)
        painter.drawLine(20, 4, 20, 10)
        painter.end()
        return QIcon(pixmap)

    @staticmethod
    def _delete_icon():
        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#d94358"), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawLine(5, 7, 19, 7)
        painter.drawLine(9, 4, 15, 4)
        painter.drawLine(7, 8, 8, 20)
        painter.drawLine(17, 8, 16, 20)
        painter.drawLine(8, 20, 16, 20)
        painter.drawLine(11, 10, 11, 17)
        painter.drawLine(13, 10, 13, 17)
        painter.end()
        return QIcon(pixmap)

    def _entry_path(self, bucket, attachment):
        if bucket == "pending":
            return Path(attachment["source"])
        try:
            return self.store.attachment_path(self.project_id, attachment)
        except ValueError:
            return None

    def open_entry(self, bucket, attachment):
        path = self._entry_path(bucket, attachment)
        if path and path.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            QMessageBox.warning(self, t("attach.invalid"), t("attach.not_found"))

    def remove(self, bucket, index):
        (self.existing if bucket == "existing" else self.pending).pop(index)
        self.show_preview()

    def clear(self):
        self.existing, self.pending = [], []
        self.show_preview()

    def value(self):
        # Copy only after every other field passes validation.
        from cms.storage import validate_attachment_name
        result = list(self.existing)
        result.extend({"path": path, "name": Path(path).name} for path in self.pending)
        for item in result:
            validate_attachment_name(self.field, item["name"])
        return result

    def commit(self):
        self.existing.extend(self.store.attach(self.project_id, path) for path in self.pending)
        self.pending.clear()
        return list(self.existing)


class FieldInput(QFrame):
    def __init__(self, field, store, project_id, value=None):
        super().__init__()
        self.field = field
        kind = field["type"]
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 3, 0, 9)
        layout.addWidget(label(field["label"] + ("  *" if field.get("required") else "")))
        if field.get("help"):
            layout.addWidget(label(field["help"], "muted"))
        self.widget = None
        if kind == "short_text":
            self.widget = QLineEdit(str(value) if value is not None else "")
            self.widget.setPlaceholderText(field.get("placeholder", ""))
            self.set_text_maximum(self.widget)
        elif kind == "long_text":
            self.widget = QPlainTextEdit(str(value) if value is not None else "")
            self.widget.setMinimumHeight(110)
            self.widget.setMaximumHeight(220)
            self.widget.setPlaceholderText(field.get("placeholder", ""))
            self.widget.textChanged.connect(self.trim_long_text)
        elif kind in {"rich_text", "html"}:
            self.widget = RichEditor(value or "", kind == "html")
        elif kind in {"number", "decimal"}:
            self.widget = QLineEdit(str(value) if value is not None else "")
            self.widget.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            self.widget.setPlaceholderText(field.get("placeholder", "") or (t("field.number_ph") if kind == "number" else t("field.decimal_ph")))
            self.set_text_maximum(self.widget)
            if kind == "number" and field.get("exact_digits", 0):
                self.widget.setMaxLength(field["exact_digits"])
                self.widget.setValidator(QRegularExpressionValidator(QRegularExpression("[0-9۰-۹٠-٩]*"), self.widget))
        elif kind in {"file", "image", "pdf"}:
            self.widget = Attachment(store, project_id, kind, value, field)
        elif kind == "checkbox":
            self.widget = QCheckBox(t("field.yes_no"))
            self.widget.setChecked(bool(value))
        elif kind == "select":
            self.widget = QComboBox()
            self.widget.addItem(t("field.choose"), None)
            for option in field["options"]:
                self.widget.addItem(option, option)
            index = self.widget.findData(value)
            self.widget.setCurrentIndex(max(0, index))
        elif kind == "radio":
            self.widget = QWidget()
            options = QVBoxLayout(self.widget)
            options.setContentsMargins(0, 0, 0, 0)
            self.group = QButtonGroup(self)
            for option in field["options"]:
                radio = QRadioButton(option)
                radio.setChecked(value == option)
                self.group.addButton(radio)
                options.addWidget(radio)
            options.addWidget(button(t("field.clear_choice"), self.clear_radio))
        elif kind in {"date", "datetime"}:
            self.widget = DatePicker(value, field.get("calendar", "jalali"))
            if kind == "datetime":
                time_row = QHBoxLayout()
                self.time = ClockTimeInput(QTime.fromString(value[11:16], "HH:mm") if value else QTime.currentTime())
                self.time.setToolTip(t("time.24h"))
                time_row.addWidget(label(t("time.label")))
                time_row.addWidget(self.time)
                time_row.addWidget(button(t("time.now"), self.set_time_now))
                time_row.addStretch()
                self.widget.layout().addLayout(time_row)
        elif kind == "time":
            self.widget = QWidget()
            row = QHBoxLayout(self.widget)
            row.setContentsMargins(0, 0, 0, 0)
            self.time = ClockTimeInput(QTime.fromString(value[:5], "HH:mm") if value else QTime.currentTime())
            self._time_empty = False
            self.time.setToolTip(t("time.24h"))
            self.time.timeChanged.connect(lambda *_: setattr(self, "_time_empty", False))
            row.addWidget(label(t("time.label")))
            row.addWidget(self.time)
            row.addWidget(button(t("time.now"), self.set_time_now))
            self.clear_time_button = button(t("time.clear"), lambda: self.clear_time())
            self.clear_time_button.setEnabled(True)
            row.addWidget(self.clear_time_button)
            row.addStretch()
        layout.addWidget(self.widget)

    def set_text_maximum(self, widget):
        maximum = self.field.get("max_length") or None
        if maximum is not None:
            widget.setMaxLength(maximum)

    def trim_long_text(self):
        maximum = self.field.get("max_length") or None
        if maximum is None or getattr(self, "_trimming", False):
            return
        value = self.widget.toPlainText()
        if len(value) > maximum:
            self._trimming = True
            self.widget.setPlainText(value[:maximum])
            self._trimming = False

    def validate_length(self, value):
        if value in (None, ""):
            return
        exact = self.field.get("exact_digits", 0) if self.field["type"] == "number" else 0
        if exact:
            if not str(value).isascii() or not str(value).isdigit():
                raise ValueError(t("field.length_digits_only", label=self.field["label"]))
            if len(str(value)) != exact:
                raise ValueError(t("field.length_exact", label=self.field["label"], exact=exact))
            return
        minimum, maximum = self.field.get("min_length", 0), self.field.get("max_length") or None
        length = len(str(value))
        if length < minimum:
            raise ValueError(t("field.length_min", label=self.field["label"], min=minimum))
        if maximum is not None and length > maximum:
            raise ValueError(t("field.length_max", label=self.field["label"], max=maximum))

    def clear_radio(self):
        self.group.setExclusive(False)
        for radio in self.group.buttons():
            radio.setChecked(False)
        self.group.setExclusive(True)

    def set_time_now(self):
        self._time_empty = False
        self.time.setTime(QTime.currentTime())
        if hasattr(self, "clear_time_button"):
            self.clear_time_button.setEnabled(True)

    def clear_time(self):
        self._time_empty = True
        self.clear_time_button.setEnabled(False)

    def value(self):
        kind, widget = self.field["type"], self.widget
        if kind == "short_text":
            value = widget.text().strip()
            self.validate_length(value)
            return value
        if kind == "long_text":
            value = widget.toPlainText().strip()
            self.validate_length(value)
            return value
        if kind in {"rich_text", "html", "file", "image", "pdf"}:
            return widget.value()
        if kind in {"number", "decimal"}:
            raw = widget.text().strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٫", "01234567890123456789."))
            if not raw:
                return None
            self.validate_length(raw)
            try:
                if kind == "number":
                    if self.field.get("exact_digits", 0):
                        return raw
                    return int(raw)
                result = Decimal(raw)
                if not result.is_finite():
                    raise InvalidOperation
                return str(result)
            except (ValueError, InvalidOperation):
                raise ValueError(t("field.invalid_number", label=self.field["label"])) from None
        if kind == "checkbox":
            return widget.isChecked()
        if kind == "select":
            return widget.currentData()
        if kind == "radio":
            selected = self.group.checkedButton()
            return selected.text() if selected else None
        if kind in {"date", "datetime"}:
            result = widget.value()
            if result is not None and kind == "datetime":
                result += "T" + self.time.time().toString("HH:mm:ss")
            return result
        if kind == "time":
            return None if self._time_empty else self.time.time().toString("HH:mm:ss")
