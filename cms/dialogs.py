from __future__ import annotations

import copy
import uuid
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt, QUrl, QSize
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout, QLineEdit, QPlainTextEdit,
    QSpinBox,
    QComboBox, QCheckBox, QDialogButtonBox, QListWidget, QListWidgetItem,
    QMessageBox, QScrollArea, QWidget, QFrame, QTextBrowser, QLabel, QToolButton,
    QAbstractItemView, QSplitter, QStyle,
)

from cms.storage import FIELD_TYPES, FILE_TYPES, display_value, validate_schema
from cms.i18n import t, current_language, set_language, direction
from cms.widgets import button, info_icon, label, FieldInput, Attachment


class FieldDialog(QDialog):
    def __init__(self, field=None, parent=None):
        super().__init__(parent)
        self.original = field
        self.result_field = None
        self.setLayoutDirection(direction())
        self.setWindowTitle(t("field.edit") if field else t("field.add"))
        self.resize(580, 640)
        layout = QVBoxLayout(self)
        layout.addWidget(label(t("field.define"), "section"))
        form = QFormLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText(t("field.name_ph"))
        self.kind = QComboBox()
        for key, title in FIELD_TYPES.items():
            self.kind.addItem(title, key)
        self.required = QCheckBox(t("field.required"))
        self.show_in_list = QCheckBox(t("field.show_in_list"))
        self.show_in_list.setChecked(True)
        self.unique = QCheckBox(t("field.unique"))
        self.unique.setToolTip(t("field.unique_tip"))
        self.help = QLineEdit()
        self.placeholder = QLineEdit()
        self.placeholder_label = label(t("field.placeholder"))
        self.minimum_value = QLineEdit()
        self.minimum_value.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.minimum_value.setPlaceholderText(t("field.no_min"))
        self.maximum_value = QLineEdit()
        self.maximum_value.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.maximum_value.setPlaceholderText(t("field.no_max"))
        value_range_row = QHBoxLayout()
        value_range_row.setContentsMargins(0, 0, 0, 0)
        value_range_row.setSpacing(8)
        value_range_row.addWidget(label(t("field.min_value")))
        value_range_row.addWidget(self.minimum_value)
        value_range_row.addSpacing(8)
        value_range_row.addWidget(label(t("field.max_value")))
        value_range_row.addWidget(self.maximum_value)
        self.value_range_widget = QWidget()
        self.value_range_widget.setLayout(value_range_row)
        self.minimum_length = QSpinBox()
        self.maximum_length = QSpinBox()
        for control in (self.minimum_length, self.maximum_length):
            control.setRange(0, 1_000_000)
            control.setToolTip(t("field.no_limit"))
            control.setFixedWidth(92)
        self.exact_digits = QSpinBox()
        self.exact_digits.setRange(0, 1_000_000)
        self.exact_digits.setToolTip(t("field.exact_digits_tip"))
        self.exact_digits.setFixedWidth(108)
        length_row = QHBoxLayout()
        length_row.setContentsMargins(0, 0, 0, 0)
        length_row.setSpacing(8)
        length_row.addWidget(label(t("field.min")))
        length_row.addWidget(self.minimum_length)
        length_row.addSpacing(8)
        length_row.addWidget(label(t("field.max")))
        length_row.addWidget(self.maximum_length)
        length_row.addStretch()
        self.length_widget = QWidget()
        self.length_widget.setLayout(length_row)
        self.options = QPlainTextEdit()
        self.options.setPlaceholderText(t("field.options_ph"))
        self.options.setMaximumHeight(145)
        self.calendar = QComboBox()
        self.calendar.addItem(t("field.calendar_jalali"), "jalali")
        self.calendar.addItem(t("field.calendar_gregorian"), "gregorian")
        self.allowed_extensions = QLineEdit()
        self.allowed_extensions.setPlaceholderText(t("field.extensions_ph"))
        self.allowed_extensions.setToolTip(t("field.extensions_tip"))
        self.exact_digits_label = label(t("field.exact_digits"))
        self.options_label = label(t("field.options"))
        self.calendar_label = label(t("field.calendar"))
        self.allowed_extensions_label = label(t("field.extensions"))
        self.value_range_label = label(t("field.value_range"))
        self.length_label = label(t("field.length_range"))
        form.addRow(t("field.name"), self.name)
        form.addRow(t("field.type"), self.kind)
        form.addRow("", self.required)
        form.addRow("", self.show_in_list)
        form.addRow("", self.unique)
        form.addRow(t("field.help"), self.help)
        form.addRow(self.placeholder_label, self.placeholder)
        form.addRow(self.length_label, self.length_widget)
        form.addRow(self.value_range_label, self.value_range_widget)
        form.addRow(self.exact_digits_label, self.exact_digits)
        form.addRow(self.options_label, self.options)
        form.addRow(self.calendar_label, self.calendar)
        form.addRow(self.allowed_extensions_label, self.allowed_extensions)
        layout.addLayout(form)
        self.note = label(t("field.type_change_note"), "muted")
        layout.addWidget(self.note)
        self.note.setVisible(bool(field))
        layout.addStretch()
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(button(t("action.cancel"), self.reject))
        row.addWidget(button(t("field.save"), self.save, "primary"))
        layout.addLayout(row)
        if field:
            self.name.setText(field["label"])
            self.kind.setCurrentIndex(self.kind.findData(field["type"]))
            self.required.setChecked(field.get("required", False))
            self.show_in_list.setChecked(field.get("show_in_list", True))
            self.unique.setChecked(field.get("unique", False))
            self.help.setText(field.get("help", ""))
            self.placeholder.setText(field.get("placeholder", ""))
            self.minimum_value.setText(self._range_text(field.get("min_value")))
            self.maximum_value.setText(self._range_text(field.get("max_value")))
            self.minimum_length.setValue(field.get("min_length", 0) or 0)
            self.maximum_length.setValue(field.get("max_length", 0) or 0)
            self.exact_digits.setValue(field.get("exact_digits", 0) or 0)
            self.options.setPlainText("\n".join(field.get("options", [])))
            self.calendar.setCurrentIndex(self.calendar.findData(field.get("calendar", "jalali")))
            self.allowed_extensions.setText(", ".join(field.get("allowed_extensions", [])))
        self.kind.currentIndexChanged.connect(self.update_controls)
        self.exact_digits.valueChanged.connect(self.update_controls)
        self.update_controls()

    def update_controls(self):
        kind = self.kind.currentData()
        supports_options = kind in {"radio", "select"}
        supports_calendar = kind in {"date", "datetime"}
        supports_extensions = kind in {"file", "image"}
        supports_exact_digits = kind == "number"
        supports_numeric_range = kind in {"number", "decimal"}
        supports_list = kind in {"short_text", "number"}
        supports_unique = kind in {"short_text", "number"}
        self.show_in_list.setVisible(supports_list)
        self.unique.setVisible(supports_unique)
        supports_placeholder = kind in {"short_text", "long_text", "number"}
        self.placeholder_label.setVisible(supports_placeholder)
        self.placeholder.setVisible(supports_placeholder)
        self.value_range_label.setVisible(supports_numeric_range)
        self.value_range_widget.setVisible(supports_numeric_range)
        self.minimum_value.setVisible(supports_numeric_range)
        self.maximum_value.setVisible(supports_numeric_range)
        for control, visible in (
            (self.options_label, supports_options), (self.options, supports_options),
            (self.calendar_label, supports_calendar), (self.calendar, supports_calendar),
            (self.allowed_extensions_label, supports_extensions), (self.allowed_extensions, supports_extensions),
            (self.exact_digits_label, supports_exact_digits), (self.exact_digits, supports_exact_digits),
        ):
            control.setVisible(visible)
        self.options.setEnabled(supports_options)
        self.calendar.setEnabled(supports_calendar)
        self.allowed_extensions.setEnabled(supports_extensions)
        supports_length = kind in {"short_text", "long_text", "number"}
        self.length_label.setVisible(supports_length)
        self.length_widget.setVisible(supports_length)
        self.placeholder.setEnabled(supports_length)
        self.exact_digits.setEnabled(supports_exact_digits)
        exact = kind == "number" and self.exact_digits.value() > 0
        if exact:
            self.minimum_length.setValue(0)
            self.maximum_length.setValue(0)
        self.minimum_length.setEnabled(supports_length and not exact)
        self.maximum_length.setEnabled(supports_length and not exact)

    def save(self):
        maximum = self.maximum_length.value()
        supports_length = self.kind.currentData() in {"short_text", "long_text", "number"}
        exact_digits = self.exact_digits.value() if self.kind.currentData() == "number" else 0
        exact = exact_digits > 0
        kind = self.kind.currentData()
        supports_list = kind in {"short_text", "number"}
        supports_unique = supports_list
        try:
            min_value = self._parse_range_value(self.minimum_value.text(), kind)
            max_value = self._parse_range_value(self.maximum_value.text(), kind)
        except ValueError as exc:
            QMessageBox.warning(self, t("field.invalid_range"), str(exc))
            return
        field = {"id": self.original["id"] if self.original else uuid.uuid4().hex,
                 "label": self.name.text().strip(), "type": kind,
                 "required": self.required.isChecked(), "show_in_list": self.show_in_list.isChecked() if supports_list else False,
                 "unique": self.unique.isChecked() if supports_unique else False,
                 "help": self.help.text().strip(),
                 "placeholder": self.placeholder.text() if kind in {"short_text", "long_text", "number"} else "",
                 "calendar": self.calendar.currentData(),
                 "min_length": self.minimum_length.value() if supports_length and not exact else 0,
                 "max_length": (maximum or None) if supports_length and not exact else None,
                 "min_value": min_value if kind in {"number", "decimal"} else None,
                 "max_value": max_value if kind in {"number", "decimal"} else None,
                 "exact_digits": exact_digits,
                 "allowed_extensions": sorted({extension.strip().lower().lstrip(".") for extension in self.allowed_extensions.text().split(",") if extension.strip()}) if self.kind.currentData() in {"file", "image"} else [],
                 "options": [x.strip() for x in self.options.toPlainText().splitlines() if x.strip()]}
        try:
            validate_schema([field])
        except ValueError as exc:
            QMessageBox.warning(self, t("field.invalid"), str(exc))
            return
        self.result_field = field
        self.accept()

    @staticmethod
    def _range_text(value):
        return "" if value is None else str(value)

    @staticmethod
    def _parse_range_value(raw, kind):
        if kind not in {"number", "decimal"}:
            return None
        raw = raw.strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٫", "01234567890123456789."))
        if not raw:
            return None
        try:
            if kind == "number":
                if not raw.lstrip("+-").isdigit():
                    raise ValueError
                return int(raw)
            value = Decimal(raw)
            if not value.is_finite():
                raise ValueError
            return str(value)
        except (ValueError, InvalidOperation):
            expected = "عدد صحیح" if kind == "number" else "عدد اعشاری"
            raise ValueError(f"محدوده باید یک {expected} معتبر باشد.") from None


def templates():
    return [
        {"id": "library", "title": t("tpl.library"), "db": "library", "fields": [
            (t("tpl.library.book_title"), "short_text", True), (t("tpl.library.author"), "short_text", False),
            (t("tpl.library.isbn"), "short_text", False), (t("tpl.library.copies"), "number", False),
            (t("tpl.library.status"), "select", False), (t("tpl.library.cover"), "image", False), (t("tpl.library.notes"), "long_text", False)],
         "select_options": [t("tpl.library.opt_available"), t("tpl.library.opt_borrowed"), t("tpl.library.opt_reserved")]},
        {"id": "clinic", "title": t("tpl.clinic"), "db": "clinic", "fields": [
            (t("tpl.clinic.name"), "short_text", True), (t("tpl.clinic.national_id"), "short_text", False),
            (t("tpl.clinic.phone"), "short_text", False), (t("tpl.clinic.visit_date"), "date", True),
            (t("tpl.clinic.appointment"), "time", False), (t("tpl.clinic.exam"), "rich_text", False),
            (t("tpl.clinic.lab"), "pdf", False), (t("tpl.clinic.paid"), "checkbox", False)],
         "select_options": []},
        {"id": "archive", "title": t("tpl.archive"), "db": "documents", "fields": [
            (t("tpl.archive.title"), "short_text", True), (t("tpl.archive.number"), "short_text", False),
            (t("tpl.archive.category"), "select", False), (t("tpl.archive.date"), "date", False),
            (t("tpl.archive.file"), "pdf", True), (t("tpl.archive.tags"), "short_text", False), (t("tpl.archive.note"), "long_text", False)],
         "select_options": [t("tpl.archive.opt_admin"), t("tpl.archive.opt_financial"), t("tpl.archive.opt_personal")]},
    ]


class ProjectDialog(QDialog):
    def __init__(self, store, project_id=None, parent=None):
        super().__init__(parent)
        self.setLayoutDirection(direction())
        self.store, self.project_id = store, project_id
        self.saved_id = None
        self.fields = copy.deepcopy(store.fields(project_id)) if project_id else []
        self.setWindowTitle(t("project.design_title"))
        self.resize(900, 710)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.addWidget(label(t("project.design_title") if project_id else t("project.new_title"), "title"))
        layout.addWidget(label(t("project.new_subtitle"), "subtitle"))
        form = QFormLayout()
        self.name, self.db_name, self.description = QLineEdit(), QLineEdit(), QLineEdit()
        self.name.setPlaceholderText(t("project.name_ph"))
        self.db_name.setPlaceholderText(t("project.db_ph"))
        self.db_name.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        form.addRow(t("project.name"), self.name)
        form.addRow(t("project.db_name"), self.db_name)
        form.addRow(t("project.description"), self.description)
        layout.addLayout(form)
        if project_id:
            project = store.project(project_id)
            self.name.setText(project["name"])
            self.db_name.setText(project["db_name"])
            self.description.setText(project["description"])
        else:
            presets = QHBoxLayout()
            presets.addWidget(label(t("project.quick_start")))
            for tpl in templates():
                presets.addWidget(button(tpl["title"], lambda checked=False, tpl_id=tpl["id"]: self.template(tpl_id)))
            presets.addStretch()
            layout.addLayout(presets)
        row = QHBoxLayout()
        row.addWidget(label(t("project.fields"), "section"))
        row.addStretch()
        row.addWidget(button(t("project.add_field"), self.add_field, "primary"))
        layout.addLayout(row)
        self.list = QListWidget()
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list.setDragEnabled(True)
        self.list.setAcceptDrops(True)
        self.list.setDropIndicatorShown(True)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list.model().rowsMoved.connect(self.sync_order)
        self.list.itemDoubleClicked.connect(lambda *_: self.edit_field())
        layout.addWidget(self.list, 1)
        controls = QHBoxLayout()
        controls.addWidget(button(t("project.edit_field"), self.edit_field))
        controls.addWidget(button(t("project.delete_field"), self.remove_field, "danger"))
        for step_dir, icon, title in (
            (-1, QStyle.StandardPixmap.SP_ArrowUp, t("project.move_up")),
            (1, QStyle.StandardPixmap.SP_ArrowDown, t("project.move_down")),
        ):
            move_button = button("", lambda checked=False, step=step_dir: self.move(step))
            move_button.setIcon(self.style().standardIcon(icon))
            move_button.setIconSize(QSize(20, 20))
            move_button.setFixedSize(40, 40)
            move_button.setToolTip(title)
            move_button.setAccessibleName(title)
            controls.addWidget(move_button)
        controls.addStretch()
        layout.addLayout(controls)
        layout.addWidget(label(t("project.order_hint"), "muted"))
        footer = QHBoxLayout()
        footer.addStretch()
        footer.addWidget(button(t("action.cancel"), self.reject))
        footer.addWidget(button(t("project.save") if project_id else t("project.create"), self.save, "primary"))
        layout.addLayout(footer)
        self.refresh()

    def refresh(self, selected=None):
        self.list.clear()
        for index, field in enumerate(self.fields):
            item = QListWidgetItem(self.field_summary(index, field))
            item.setData(Qt.ItemDataRole.UserRole, field["id"])
            self.list.addItem(item)
        if selected is not None:
            self.list.setCurrentRow(selected)

    def sync_order(self, *_):
        mapping = {f["id"]: f for f in self.fields}
        self.fields = [mapping[self.list.item(i).data(Qt.ItemDataRole.UserRole)] for i in range(self.list.count())]
        for index, field in enumerate(self.fields):
            self.list.item(index).setText(self.field_summary(index, field))

    @staticmethod
    def field_summary(index, field):
        required = "   *" if field.get("required") else ""
        list_supported = field["type"] in {"short_text", "number"}
        visible = f"   ·   {t('field.in_table')}" if list_supported and field.get("show_in_list", True) else f"   ·   {t('field.only_form')}" 
        unique = f"   ·   {t('field.unique_tag')}" if field.get("unique", False) else "" 
        return f"{index + 1:02d}   {field['label']}   ·   {FIELD_TYPES[field['type']]}{required}{visible}{unique}"

    def template(self, tpl_id):
        if self.fields and QMessageBox.question(self, t("project.replace_fields"), t("project.replace_confirm")) != QMessageBox.StandardButton.Yes:
            return
        tpl = next((item for item in templates() if item["id"] == tpl_id), None)
        if tpl is None:
            return
        self.fields = []
        for name, kind, required in tpl["fields"]:
            options = list(tpl["select_options"]) if kind == "select" else []
            self.fields.append({"id": uuid.uuid4().hex, "label": name, "type": kind,
                                "required": required, "options": options, "calendar": "jalali"})
        if not self.name.text():
            self.name.setText(tpl["title"])
        if not self.db_name.text():
            self.db_name.setText(tpl["db"])
        self.refresh()

    def add_field(self):
        dialog = FieldDialog(parent=self)
        if dialog.exec():
            self.fields.append(dialog.result_field)
            self.refresh(len(self.fields) - 1)

    def edit_field(self):
        index = self.list.currentRow()
        if index < 0:
            return
        dialog = FieldDialog(self.fields[index], self)
        if dialog.exec():
            self.fields[index] = dialog.result_field
            self.refresh(index)

    def remove_field(self):
        index = self.list.currentRow()
        if index >= 0 and QMessageBox.question(self, t("project.remove_field_title"), t("project.remove_field_confirm", label=self.fields[index]["label"])) == QMessageBox.StandardButton.Yes:
            self.fields.pop(index)
            self.refresh(min(index, len(self.fields) - 1))

    def move(self, direction):
        index = self.list.currentRow()
        target = index + direction
        if index >= 0 and 0 <= target < len(self.fields):
            self.fields[index], self.fields[target] = self.fields[target], self.fields[index]
            self.refresh(target)

    def save(self):
        try:
            args = (self.name.text(), self.db_name.text(), self.description.text(), self.fields)
            if self.project_id:
                self.store.update_project(self.project_id, *args)
                self.saved_id = self.project_id
            else:
                self.saved_id = self.store.create(*args)
        except Exception as exc:
            QMessageBox.warning(self, t("dialog.save_failed"), str(exc))
            return
        self.accept()


class RecordDialog(QDialog):
    def __init__(self, store, project_id, record=None, parent=None):
        super().__init__(parent)
        self.setLayoutDirection(direction())
        self.store, self.project_id, self.record = store, project_id, record
        self.saved_id = None
        self.setWindowTitle(t("record.edit") if record else t("record.new"))
        self.resize(800, 760)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.addWidget(label(t("record.edit_title") if record else t("record.new_title"), "title"))
        layout.addWidget(label(t("record.subtitle", project=store.project(project_id)["name"]), "subtitle"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        form = QVBoxLayout(body)
        self.inputs = []
        values = record["data"] if record else {}
        for field in store.fields(project_id):
            input_widget = FieldInput(field, store, project_id, values.get(field["id"]))
            self.inputs.append(input_widget)
            form.addWidget(input_widget)
        form.addStretch()
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)
        self.scroll = scroll
        self.error = label("")
        self.error.setStyleSheet("color: #c83e56;")
        layout.addWidget(self.error)
        footer = QHBoxLayout()
        footer.addStretch()
        footer.addWidget(button(t("action.cancel"), self.reject))
        footer.addWidget(button(t("record.save_edit") if record else t("record.save_new"), self.save, "primary"))
        layout.addLayout(footer)

    def save(self):
        values = dict(self.record["data"]) if self.record else {}
        current = None
        try:
            for current in self.inputs:
                current.setProperty("invalid", False)
                current.style().unpolish(current)
                current.style().polish(current)
                value = current.value()
                if current.field.get("required") and (value is None or value == "" or value == [] or (current.field["type"] == "checkbox" and value is not True)):
                    raise ValueError(f"فیلد «{current.field['label']}» الزامی است.")
                values[current.field["id"]] = value
            self.store.validate_record(
                self.project_id,
                values,
                self.record["id"] if self.record else None,
            )
            for current in self.inputs:
                if isinstance(current.widget, Attachment):
                    values[current.field["id"]] = current.widget.commit()
            self.saved_id = self.store.save_record(self.project_id, values, self.record["id"] if self.record else None)
        except Exception as exc:
            self.error.setText(str(exc))
            if current:
                current.setProperty("invalid", True)
                current.style().unpolish(current)
                current.style().polish(current)
                self.scroll.ensureWidgetVisible(current)
            return
        self.accept()


class RecordView(QDialog):
    def __init__(self, store, project_id, record, parent=None, records=None):
        super().__init__(parent)
        self.setLayoutDirection(direction())
        self.store, self.project_id = store, project_id
        self.records = sorted(
            list(records) if records else [record],
            key=lambda item: item["id"],
        )
        self.current_index = next(
            (index for index, item in enumerate(self.records) if item["id"] == record["id"]),
            0,
        )
        self.record = self.records[self.current_index]
        self.edit_requested = False
        self.setWindowTitle(t("record.view", id=self.record["id"]))
        self.resize(760, 740)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        self.record_title = label("", "title")
        self.project_title = label(store.project(project_id)["name"], "subtitle")
        layout.addWidget(self.record_title)
        layout.addWidget(self.project_title)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        self.fields_layout = QVBoxLayout(body)
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)

        navigation = QHBoxLayout()
        navigation.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.previous_button = self._navigation_button(
            QStyle.StandardPixmap.SP_ArrowRight,
            t("record.prev"),
            "recordPreviousButton",
            self.previous_record,
        )
        self.position_spin = QSpinBox(self)
        self.position_spin.setObjectName("recordPositionSpin")
        self.position_spin.setRange(1, len(self.records))
        self.position_spin.setPrefix(t("record.position"))
        self.position_spin.setSuffix(t("record.of", total=len(self.records)))
        self.position_spin.setFixedWidth(156)
        self.position_spin.setToolTip(t("record.goto_tip"))
        self.position_spin.setKeyboardTracking(False)
        self.position_spin.editingFinished.connect(self.go_to_position)
        self.go_button = self._navigation_button(
            QStyle.StandardPixmap.SP_DialogApplyButton,
            t("record.goto"),
            "recordGoButton",
            self.go_to_position,
        )
        self.next_button = self._navigation_button(
            QStyle.StandardPixmap.SP_ArrowLeft,
            t("record.next"),
            "recordNextButton",
            self.next_record,
        )
        self.last_button = self._navigation_button(
            QStyle.StandardPixmap.SP_MediaSkipBackward,
            t("record.last"),
            "recordLastButton",
            self.last_record,
        )
        self.first_button = self._navigation_button(
            QStyle.StandardPixmap.SP_MediaSkipForward,
            t("record.first"),
            "recordFirstButton",
            self.first_record,
        )
        navigation.addWidget(self.first_button)
        navigation.addWidget(self.previous_button)
        navigation.addWidget(self.position_spin)
        navigation.addWidget(self.go_button)
        navigation.addWidget(self.next_button)
        navigation.addWidget(self.last_button)
        layout.addLayout(navigation)

        footer = QHBoxLayout()
        footer.addStretch()
        footer.addWidget(button(t("action.close"), self.reject))
        footer.addWidget(button(t("record.edit_btn"), self.edit, "primary"))
        layout.addLayout(footer)
        self._render_record()

    def _navigation_button(self, icon, tooltip, object_name, handler):
        control = QToolButton(self)
        control.setObjectName(object_name)
        control.setIcon(self.style().standardIcon(icon))
        control.setIconSize(QSize(24, 24))
        control.setFixedSize(46, 42)
        control.setToolTip(tooltip)
        control.setAccessibleName(tooltip)
        control.setCursor(Qt.CursorShape.PointingHandCursor)
        control.clicked.connect(handler)
        return control

    def _clear_fields(self):
        while self.fields_layout.count():
            item = self.fields_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

    def _render_record(self):
        record = self.record
        self.setWindowTitle(t("record.view", id=record["id"]))
        self.record_title.setText(t("record.view_title", id=record["id"]))
        self.position_spin.blockSignals(True)
        self.position_spin.setValue(self.current_index + 1)
        self.position_spin.blockSignals(False)
        self.first_button.setEnabled(self.current_index > 0)
        self.previous_button.setEnabled(self.current_index > 0)
        self.next_button.setEnabled(self.current_index < len(self.records) - 1)
        self.last_button.setEnabled(self.current_index < len(self.records) - 1)
        self.go_button.setEnabled(len(self.records) > 0)
        self._clear_fields()
        for field in self.store.fields(self.project_id):
            card = QFrame()
            card.setObjectName("card")
            row = QVBoxLayout(card)
            row.addWidget(label(field["label"], "muted"))
            value = record["data"].get(field["id"])
            if field["type"] in {"rich_text", "html"} and value:
                view = QTextBrowser()
                view.setOpenExternalLinks(False)
                view.setOpenLinks(False)
                view.setHtml(value)
                view.setMinimumHeight(150)
                row.addWidget(view)
            elif field["type"] in FILE_TYPES and value:
                from cms.storage import attachment_items
                for attachment in attachment_items(value):
                    try:
                        path = self.store.attachment_path(self.project_id, attachment)
                        attachment_card = QFrame()
                        attachment_card.setObjectName("attachmentCard")
                        item_layout = QVBoxLayout(attachment_card)
                        item_layout.addWidget(label(attachment["name"]))
                        item_layout.addWidget(button("باز کردن پیوست", lambda checked=False, path=path: QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))))
                        if field["type"] == "image" and path.exists():
                            image = QLabel()
                            image.setAlignment(Qt.AlignmentFlag.AlignCenter)
                            image.setPixmap(QPixmap(str(path)).scaled(550, 300, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                            item_layout.addWidget(image)
                        elif field["type"] == "pdf" and path.exists():
                            from PySide6.QtPdf import QPdfDocument
                            from PySide6.QtPdfWidgets import QPdfView
                            document = QPdfDocument(self)
                            document.load(str(path))
                            viewer = QPdfView()
                            viewer.setDocument(document)
                            viewer.setPageMode(QPdfView.PageMode.MultiPage)
                            viewer.setZoomMode(QPdfView.ZoomMode.FitToWidth)
                            viewer.setMinimumHeight(400)
                            item_layout.addWidget(viewer)
                        row.addWidget(attachment_card)
                    except (ValueError, ImportError) as exc:
                        row.addWidget(label(str(exc), "muted"))
            else:
                text = label(display_value(value, field))
                text.setTextFormat(Qt.TextFormat.PlainText)
                text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                row.addWidget(text)
            self.fields_layout.addWidget(card)
        self.fields_layout.addWidget(label(t("record.created_utc", created=record["created_at"], updated=record["updated_at"]), "muted"))
        self.fields_layout.addStretch()
        self.fields_layout.itemAt(0).widget().setFocus() if self.fields_layout.count() else None

    def previous_record(self):
        if self.current_index > 0:
            self._set_record_index(self.current_index - 1)

    def next_record(self):
        if self.current_index < len(self.records) - 1:
            self._set_record_index(self.current_index + 1)

    def first_record(self):
        self._set_record_index(0)

    def last_record(self):
        self._set_record_index(len(self.records) - 1)

    def go_to_position(self):
        self._set_record_index(self.position_spin.value() - 1)

    def _set_record_index(self, index):
        if not 0 <= index < len(self.records):
            return
        self.current_index = index
        self.record = self.records[index]
        self._render_record()

    def edit(self):
        self.edit_requested = True
        self.accept()


class AboutDialog(QDialog):
    """Product card with the developer, contact details and release year."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayoutDirection(direction())
        self.setWindowTitle(t("about.title"))
        self.setObjectName("aboutDialog")
        self.setWindowIcon(info_icon(32, "#6757db"))
        self.setFixedWidth(450)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 18)
        layout.setSpacing(16)

        header = QHBoxLayout()
        header.setSpacing(14)
        badge = QLabel("د")
        badge.setObjectName("aboutBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedSize(60, 60)
        header.addWidget(badge)
        titles = QVBoxLayout()
        titles.setSpacing(3)
        titles.addWidget(label("دفتر", "aboutName"))
        titles.addWidget(label(t("about.subtitle"), "subtitle"))
        header.addLayout(titles)
        header.addStretch()
        layout.addLayout(header)

        card = QFrame()
        card.setObjectName("aboutCard")
        rows = QGridLayout(card)
        rows.setContentsMargins(20, 18, 20, 18)
        rows.setHorizontalSpacing(16)
        rows.setVerticalSpacing(13)
        email = QLabel(
            '<a href="mailto:drhsaadat@gmail.com" '
            'style="color:#5142b4; text-decoration:none;">drhsaadat@gmail.com</a>'
        )
        email.setObjectName("aboutEmail")
        email.setTextFormat(Qt.TextFormat.RichText)
        email.setOpenExternalLinks(True)
        email.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        email.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        entries = (
            ("طراحی و توسعه", label(t("about.developer_name"), "aboutValue")),
            ("آدرس", label(t("about.address_value"), "aboutValue")),
            ("ایمیل", email),
            ("سال", label(t("about.year_value"), "aboutValue")),
        )
        for row, (title, value) in enumerate(entries):
            key_label = label(title, "aboutKey")
            key_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            rows.addWidget(key_label, row, 0)
            if isinstance(value, QLabel):
                value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if value is not email:
                    value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            rows.addWidget(value, row, 1)
        rows.setColumnStretch(1, 1)
        layout.addWidget(card)

        footer = QHBoxLayout()
        footer.addStretch()
        close_button = button(t("action.close"), self.accept, "primary")
        close_button.setMinimumWidth(110)
        footer.addWidget(close_button)
        layout.addLayout(footer)


class SettingsDialog(QDialog):
    """Language and layout settings."""

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle(t("settings.title"))
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(14)
        layout.addWidget(label(t("settings.title"), "title"))
        form = QFormLayout()
        self.language = QComboBox()
        self.language.addItem(t("settings.lang_fa"), "fa")
        self.language.addItem(t("settings.lang_en"), "en")
        idx = self.language.findData(current_language())
        self.language.setCurrentIndex(max(0, idx))
        form.addRow(t("settings.language"), self.language)
        layout.addLayout(form)
        hint = label(t("settings.restart_hint"), "muted")
        layout.addWidget(hint)
        layout.addStretch()
        footer = QHBoxLayout()
        footer.addStretch()
        footer.addWidget(button(t("action.cancel"), self.reject))
        footer.addWidget(button(t("action.save"), self.save, "primary"))
        layout.addLayout(footer)

    def save(self):
        lang = self.language.currentData() or "fa"
        settings = self.store.settings()
        settings["language"] = lang
        settings["layout_direction"] = "ltr" if lang == "en" else "rtl"
        self.store.save_settings(settings)
        set_language(lang)
        app = QApplication.instance()
        if app is not None:
            app.setLayoutDirection(direction())
        self.accept()
