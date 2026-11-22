from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QAction, QColor, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QStackedWidget, QTableWidget,
    QTableWidgetItem, QAbstractItemView, QHeaderView, QLineEdit,
    QComboBox, QFileDialog, QMessageBox,
    QScrollArea,
)

from cms.dialogs import AboutDialog, ProjectDialog, RecordDialog, RecordView
from cms.storage import display_value
from cms.i18n import t, set_language, direction, is_rtl, current_language, align_start
from cms.widgets import button, info_icon, label


def fa_digits(value):
    if current_language() == "en":
        return str(value)
    return str(value).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def format_bytes(size):
    size = max(0, int(size))
    units = ("unit.bytes", "unit.kb", "unit.mb", "unit.gb", "unit.tb")
    value = float(size)
    unit_key = units[0]
    for key in units[1:]:
        if value < 1024:
            break
        value /= 1024
        unit_key = key
    if unit_key == "unit.bytes":
        return f"{fa_digits(int(size))} {t(unit_key)}"
    number = f"{value:.1f}".rstrip("0").rstrip(".")
    if current_language() != "en":
        number = number.replace(".", "٫")
    return f"{fa_digits(number)} {t(unit_key)}"


class SortItem(QTableWidgetItem):
    def __lt__(self, other):
        left, right = self.data(Qt.ItemDataRole.UserRole + 1), other.data(Qt.ItemDataRole.UserRole + 1)
        if left is not None and right is not None:
            try:
                return left < right
            except TypeError:
                pass
        return self.text().casefold() < other.text().casefold()


class ResponsiveTable(QTableWidget):
    """A table whose columns always fill the viewport proportionally."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._column_weights = []
        self._applying_column_widths = False

    def setColumnWeights(self, weights):
        self._column_weights = [max(0.1, float(weight)) for weight in weights]
        self._apply_column_widths()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_column_widths()

    def _apply_column_widths(self):
        if self._applying_column_widths or self.columnCount() == 0:
            return
        available = self.viewport().width()
        if available <= 0:
            return
        weights = self._column_weights
        if len(weights) != self.columnCount():
            weights = [1.0] * self.columnCount()
        total = sum(weights)
        if total <= 0:
            return
        self._applying_column_widths = True
        try:
            header = self.horizontalHeader()
            for column in range(self.columnCount()):
                header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            widths = [int(available * weight / total) for weight in weights]
            # Put rounding remainder into the final column so the table has no
            # unused strip or horizontal overflow at any window size.
            widths[-1] += available - sum(widths)
            for column, width in enumerate(widths):
                self.setColumnWidth(column, max(1, width))
        finally:
            self._applying_column_widths = False


def configure_table(view):
    view.setAlternatingRowColors(True)
    view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    view.verticalHeader().hide()
    view.verticalHeader().setDefaultSectionSize(52)
    view.horizontalHeader().setStretchLastSection(False)
    view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    view.setShowGrid(False)
    return view


def table():
    return configure_table(QTableWidget())


class PageScrollArea(QScrollArea):
    """Main page viewport with vertical scrolling for growing page content."""
    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)


class MainWindow(QMainWindow):
    def __init__(self, store):
        super().__init__()
        self.store = store
        self.project_id = None
        self.rows, self.fields, self.visible_records = [], [], []
        self.setWindowTitle(t("app.title"))
        self.resize(1360, 880)
        self.setMinimumSize(1050, 680)
        host = QWidget()
        layout = QHBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(235)
        nav = QVBoxLayout(sidebar)
        nav.setContentsMargins(20, 30, 20, 20)
        nav.setSpacing(12)
        nav.addWidget(label(t("app.name"), "brand"))
        nav.addWidget(label(t("app.brand_sub"), "brandSub"))
        nav.addSpacing(24)
        nav.addWidget(button("▦   " + t("nav.all_projects"), self.home, "nav"))
        nav.addWidget(button("＋   " + t("nav.new_project"), self.new_project, "nav"))
        nav.addSpacing(15)
        nav.addWidget(label(t("nav.your_projects"), "brandSub"))
        self.project_nav = QListWidget()
        self.project_nav.setObjectName("projectNav")
        self.project_nav.itemClicked.connect(lambda item: self.open_project(item.data(Qt.ItemDataRole.UserRole)))
        nav.addWidget(self.project_nav, 1)
        nav.addWidget(button(t("nav.restore_backup"), self.restore, "nav"))
        nav.addWidget(button(t("nav.data_folder"), self.open_data, "nav"))
        nav.addWidget(button(t("action.settings"), self.show_settings, "nav"))
        nav.addWidget(button(t("nav.about"), self.show_about, "nav", icon=info_icon(20)))
        nav.addSpacing(10)
        nav.addWidget(label(t("nav.local_note"), "brandSub"))
        layout.addWidget(sidebar)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(host)
        self.build_home()
        self.build_records()
        self.statusBar().showMessage(t("app.ready"))
        refresh = QAction(t("action.refresh"), self)
        refresh.setShortcut(QKeySequence("F5"))
        refresh.triggered.connect(self.refresh)
        self.addAction(refresh)
        create = QAction(t("action.new_record"), self)
        create.setShortcut(QKeySequence("Ctrl+N"))
        create.triggered.connect(lambda: self.new_record() if self.project_id else self.new_project())
        self.addAction(create)
        self.home()

    def page_layout(self):
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(30, 28, 30, 22)
        layout.setSpacing(18)
        page = PageScrollArea()
        page.setWidget(content)
        self.stack.addWidget(page)
        return page, layout

    def build_home(self):
        self.home_page, layout = self.page_layout()
        top = QHBoxLayout()
        titles = QVBoxLayout()
        titles.addWidget(label(t("home.dashboard"), "title"))
        titles.addWidget(label(t("home.subtitle"), "subtitle"))
        top.addLayout(titles, 1)
        top.addWidget(button(t("home.new_project"), self.new_project, "primary"))
        layout.addLayout(top)
        stats = QHBoxLayout()
        self.stat_labels = []
        for title in (t("home.stat_projects"), t("home.stat_records"), t("home.stat_databases")):
            frame = QFrame()
            frame.setObjectName("stat")
            box = QHBoxLayout(frame)
            box.setContentsMargins(18, 9, 18, 9)
            box.setSpacing(13)
            box.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            number = label("۰", "number")
            self.stat_labels.append(number)
            box.addWidget(number)
            caption = label(title, "muted")
            box.addWidget(caption, 1)
            frame.setMinimumHeight(70)
            frame.setMaximumHeight(82)
            stats.addWidget(frame)
        layout.addLayout(stats)
        tools = QHBoxLayout()
        tools.addWidget(label(t("home.projects_db"), "section"))
        tools.addStretch()
        self.project_search = QLineEdit()
        self.project_search.setPlaceholderText(t("home.search_projects"))
        self.project_search.setMaximumWidth(330)
        self.project_search.textChanged.connect(self.filter_projects)
        tools.addWidget(self.project_search)
        layout.addLayout(tools)
        self.projects_table = table()
        self.projects_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.projects_table.setColumnCount(8)
        self.projects_table.setHorizontalHeaderLabels([
            t("home.col.name"), t("home.col.db"), t("home.col.records"), t("home.col.db_size"),
            t("home.col.media_count"), t("home.col.media_size"), t("home.col.desc"), t("home.col.created"),
        ])
        self.projects_table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.projects_table.horizontalHeader().setFixedHeight(46)
        self.projects_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.projects_table.cellDoubleClicked.connect(lambda *_: self.open_selected_project())
        layout.addWidget(self.projects_table, 0, Qt.AlignmentFlag.AlignTop)
        self.home_empty = label(t("home.empty"), "muted")
        self.home_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.home_empty)
        actions = QHBoxLayout()
        actions.addWidget(button(t("action.open_project"), self.open_selected_project, "primary"))
        actions.addWidget(button(t("action.edit_structure"), self.edit_selected_project))
        actions.addWidget(button(t("action.delete_project"), self.delete_selected_project, "danger"))
        actions.addStretch()
        actions.addWidget(button(t("action.export_all_json"), self.export_all_json))
        actions.addWidget(button(t("action.backup_all"), self.backup_all))
        actions.addWidget(button(t("action.refresh"), self.refresh))
        layout.addLayout(actions)

    def build_records(self):
        self.records_page, layout = self.page_layout()
        top = QHBoxLayout()
        titles = QVBoxLayout()
        self.project_title, self.project_subtitle = label("", "title"), label("", "subtitle")
        titles.addWidget(self.project_title)
        titles.addWidget(self.project_subtitle)
        top.addLayout(titles, 1)
        top.addWidget(button(t("records.register"), self.new_record, "primary"))
        layout.addLayout(top)
        tools = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(t("records.search"))
        self.search.textChanged.connect(self.populate_records)
        self.search_field = QComboBox()
        self.search_field.setMinimumWidth(150)
        self.search_field.currentIndexChanged.connect(self.populate_records)
        tools.addWidget(self.search, 1)
        tools.addWidget(self.search_field)
        tools.addWidget(button(t("records.structure"), self.edit_current_project))
        layout.addLayout(tools)
        self.records_table = configure_table(ResponsiveTable())
        self.records_table.setObjectName("recordsTable")
        self.records_table.setLayoutDirection(direction())
        self.records_table.verticalHeader().setDefaultSectionSize(56)
        records_header = self.records_table.horizontalHeader()
        records_header.setDefaultAlignment(align_start())
        records_header.setFixedHeight(48)
        records_header.setMinimumSectionSize(1)
        records_header.setStretchLastSection(False)
        self.records_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.records_table.setSortingEnabled(True)
        self.records_table.cellDoubleClicked.connect(lambda *_: self.view_record())
        layout.addWidget(self.records_table, 1)
        self.records_empty = label("", "muted")
        self.records_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.records_empty)
        footer = QHBoxLayout()
        footer.addWidget(button(t("action.view"), self.view_record))
        footer.addWidget(button(t("action.edit"), self.edit_record))
        footer.addWidget(button(t("action.delete_selected"), self.delete_records, "danger"))
        footer.addStretch()
        footer.addWidget(button(t("action.export_csv"), self.export_csv))
        footer.addWidget(button(t("action.export_json"), self.export_project_json))
        footer.addWidget(button(t("action.backup_project"), self.backup))
        layout.addLayout(footer)
        self.record_count = label("", "muted")
        layout.addWidget(self.record_count)

    def alert(self, exc):
        QMessageBox.warning(self, t("dialog.operation_failed"), str(exc))

    def show_about(self):
        AboutDialog(self).exec()

    def show_settings(self):
        from cms.dialogs import SettingsDialog
        dialog = SettingsDialog(self.store, self)
        if dialog.exec():
            # Rebuild UI so every label/layout reflects the new language.
            current_project = self.project_id
            self.close()
            new_window = MainWindow(self.store)
            new_window.setWindowIcon(self.windowIcon())
            if current_project:
                try:
                    new_window.open_project(current_project)
                except Exception:
                    new_window.home()
            new_window.showMaximized()
            app = QApplication.instance()
            if app is not None:
                app._main_window = new_window

    def refresh_projects(self):
        self.projects = self.store.projects()
        self.project_nav.clear()
        self.projects_table.setRowCount(len(self.projects))
        for index, project in enumerate(self.projects):
            item = QListWidgetItem(project["name"])
            item.setData(Qt.ItemDataRole.UserRole, project["id"])
            self.project_nav.addItem(item)
            created = project["created_at"][:10]
            if current_language() != "en":
                try:
                    import jdatetime
                    from datetime import date
                    created = jdatetime.date.fromgregorian(date=date.fromisoformat(created)).strftime("%Y/%m/%d")
                except Exception:
                    pass
                created = fa_digits(created)
            values = [
                project["name"], project["db_name"], fa_digits(project["count"]),
                format_bytes(project["db_size"]), fa_digits(project["media_count"]),
                format_bytes(project["media_size"]),
                project["error"] or project["description"] or "—", created,
            ]
            for col, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setData(Qt.ItemDataRole.UserRole, project["id"])
                cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                cell.setToolTip(value)
                self.projects_table.setItem(index, col, cell)
        # Keep the overview compact: its height follows its content, with a
        # sensible cap for long project lists. Columns share the full viewport.
        row_height = self.projects_table.verticalHeader().defaultSectionSize()
        visible_rows = min(max(len(self.projects), 1), 7)
        self.projects_table.setFixedHeight(self.projects_table.horizontalHeader().height() + visible_rows * row_height + 2)
        self.resize_project_columns()
        for index, value in enumerate((len(self.projects), sum(p["count"] for p in self.projects), len(self.projects))):
            self.stat_labels[index].setText(str(value).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")))
        self.home_empty.setVisible(not self.projects)
        self.filter_projects()

    def resize_project_columns(self):
        if not hasattr(self, "projects_table"):
            return
        widths = (1.05, 1.2, 0.8, 1.05, 0.85, 1.0, 1.6, 0.95)
        available = self.projects_table.viewport().width()
        if available <= 0:
            return
        total = sum(widths)
        used = 0
        for column, weight in enumerate(widths[:-1]):
            width = int(available * weight / total)
            self.projects_table.setColumnWidth(column, width)
            used += width
        self.projects_table.setColumnWidth(len(widths) - 1, max(1, available - used))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resize_project_columns()

    def filter_projects(self):
        query = self.project_search.text().strip().casefold()
        for row in range(self.projects_table.rowCount()):
            content = " ".join(self.projects_table.item(row, col).text() for col in range(self.projects_table.columnCount()))
            self.projects_table.setRowHidden(row, query not in content.casefold())

    def home(self):
        self.project_id = None
        self.refresh_projects()
        self.stack.setCurrentWidget(self.home_page)

    def refresh(self):
        if self.project_id:
            self.open_project(self.project_id)
        else:
            self.home()

    def selected_project(self):
        row = self.projects_table.currentRow()
        if row < 0 or self.projects_table.isRowHidden(row):
            self.statusBar().showMessage(t("project.select_first"), 4000)
            return None
        return self.projects_table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def open_selected_project(self):
        project_id = self.selected_project()
        if project_id:
            self.open_project(project_id)

    def new_project(self):
        dialog = ProjectDialog(self.store, parent=self)
        if dialog.exec():
            self.open_project(dialog.saved_id)

    def edit_selected_project(self):
        project_id = self.selected_project()
        if project_id:
            self.edit_project(project_id)

    def edit_current_project(self):
        if self.project_id:
            self.edit_project(self.project_id)

    def edit_project(self, project_id):
        try:
            dialog = ProjectDialog(self.store, project_id, self)
            if dialog.exec():
                self.open_project(project_id)
        except Exception as exc:
            self.alert(exc)

    def delete_selected_project(self):
        project_id = self.selected_project()
        if not project_id:
            return
        name = self.store.project(project_id)["name"]
        if QMessageBox.question(self, t("project.delete_title"), t("project.delete_confirm", name=name)) == QMessageBox.StandardButton.Yes:
            try:
                self.store.delete_project(project_id)
                self.home()
            except Exception as exc:
                self.alert(exc)

    def open_project(self, project_id):
        try:
            project = self.store.project(project_id)
            fields = self.store.fields(project_id)
            rows = self.store.records(project_id)
            self.project_id, self.fields, self.rows = project_id, fields, rows
            self.project_title.setText(project["name"])
            self.project_subtitle.setText(f"{project['db_name']}  •  {len(fields)} فیلد  •  {project['description'] or 'مدیریت رکوردها'}")
            self.search.blockSignals(True)
            self.search.clear()
            self.search.blockSignals(False)
            self.search_field.blockSignals(True)
            self.search_field.clear()
            self.search_field.addItem(t("records.all_fields"), None)
            for field in fields:
                self.search_field.addItem(field["label"], field["id"])
            self.search_field.blockSignals(False)
            self.populate_records()
            self.refresh_projects()
            self.stack.setCurrentWidget(self.records_page)
            self.statusBar().showMessage(f"دیتابیس: {self.store.database_path(project_id)}")
        except Exception as exc:
            self.alert(exc)

    def populate_records(self):
        query = self.search.text().strip().casefold()
        field_id = self.search_field.currentData()
        search_fields = [f for f in self.fields if not field_id or f["id"] == field_id]
        list_fields = [
            f for f in self.fields
            if f["type"] in {"short_text", "number"} and f.get("show_in_list", True)
        ]
        visible = sorted(
            (r for r in self.rows if not query or query in (str(r["id"]) + " " + " ".join(display_value(r["data"].get(f["id"]), f) for f in search_fields)).casefold()),
            key=lambda record: record["id"],
        )
        self.visible_records = visible
        self.records_table.setSortingEnabled(False)
        self.records_table.clear()
        self.records_table.setColumnCount(len(list_fields) + 1)
        self.records_table.setHorizontalHeaderLabels([("ID" if current_language() == "en" else "شناسه"), *[f["label"] for f in list_fields]])
        for col in range(self.records_table.columnCount()):
            header_item = self.records_table.horizontalHeaderItem(col)
            if header_item is not None:
                header_item.setTextAlignment(align_start())
        self.records_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.records_table.setRowCount(len(visible))
        for index, record in enumerate(visible):
            item = SortItem(str(record["id"]))
            item.setData(Qt.ItemDataRole.UserRole, record["id"])
            item.setData(Qt.ItemDataRole.UserRole + 1, record["id"])
            item.setTextAlignment(align_start())
            item.setForeground(QColor("#8b96ab"))
            self.records_table.setItem(index, 0, item)
            for col, field in enumerate(list_fields, 1):
                value = record["data"].get(field["id"])
                text = display_value(value, field)
                cell = SortItem(text.replace("\n", " ")[:180])
                cell.setTextAlignment(align_start())
                cell.setToolTip(text[:2000])
                if field["type"] in {"number", "decimal"} and value is not None:
                    from decimal import Decimal, InvalidOperation
                    try:
                        cell.setData(Qt.ItemDataRole.UserRole + 1, Decimal(str(value)))
                    except InvalidOperation:
                        pass
                self.records_table.setItem(index, col, cell)
        weights = [0.55]
        for field in list_fields:
            kind = field["type"]
            if kind in {"rich_text", "html", "long_text"}:
                weight = 2.1
            elif kind in {"image", "file", "pdf"}:
                weight = 1.25
            elif kind in {"date", "datetime"}:
                weight = 1.0
            elif kind in {"number", "decimal", "checkbox", "time"}:
                weight = 0.75
            else:
                weight = 1.25
            weights.append(weight)
        self.records_table.setColumnWeights(weights)
        self.records_table.setSortingEnabled(True)
        self.records_table.sortItems(0, Qt.SortOrder.AscendingOrder)
        self.records_empty.setText(t("records.empty_filtered") if self.rows else t("records.empty"))
        self.records_empty.setVisible(not visible)
        self.record_count.setText(t("records.count", visible=len(visible), total=len(self.rows)))

    def selected_records(self):
        return [self.records_table.item(index.row(), 0).data(Qt.ItemDataRole.UserRole) for index in self.records_table.selectionModel().selectedRows()]

    def selected_record(self):
        ids = self.selected_records()
        if not ids:
            self.statusBar().showMessage(t("records.select_first"), 4000)
            return None
        return next((r for r in self.rows if r["id"] == ids[0]), None)

    def new_record(self):
        if self.project_id:
            try:
                dialog = RecordDialog(self.store, self.project_id, parent=self)
                if dialog.exec():
                    self.reload_records()
            except Exception as exc:
                self.alert(exc)

    def reload_records(self):
        self.rows = self.store.records(self.project_id)
        self.populate_records()
        self.refresh_projects()

    def edit_record(self):
        record = self.selected_record()
        if record:
            self.edit_record_value(record)

    def edit_record_value(self, record):
        try:
            dialog = RecordDialog(self.store, self.project_id, record, self)
            if dialog.exec():
                self.reload_records()
        except Exception as exc:
            self.alert(exc)

    def view_record(self):
        record = self.selected_record()
        if record:
            try:
                records_by_id = {item["id"]: item for item in self.rows}
                displayed_records = []
                for row in range(self.records_table.rowCount()):
                    item = self.records_table.item(row, 0)
                    if item is not None and item.data(Qt.ItemDataRole.UserRole) in records_by_id:
                        displayed_records.append(records_by_id[item.data(Qt.ItemDataRole.UserRole)])
                dialog = RecordView(
                    self.store, self.project_id, record, self,
                    displayed_records or self.visible_records or [record],
                )
                dialog.exec()
                if dialog.edit_requested:
                    self.edit_record_value(dialog.record)
            except Exception as exc:
                self.alert(exc)

    def delete_records(self):
        ids = self.selected_records()
        if ids and QMessageBox.question(self, t("record.delete_title"), t("record.delete_confirm", count=len(ids))) == QMessageBox.StandardButton.Yes:
            try:
                self.store.delete_records(self.project_id, ids)
                self.reload_records()
            except Exception as exc:
                self.alert(exc)

    def backup(self):
        if not self.project_id:
            return
        project_name = self.store.project(self.project_id)["name"]
        safe_name = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in project_name).strip("_") or "project"
        path, _ = QFileDialog.getSaveFileName(self, t("backup.save_project"), f"{safe_name}-backup.zip", "ZIP (*.zip)")
        if path:
            try:
                self.store.backup(self.project_id, path)
                self.statusBar().showMessage(t("backup.saved"), 6000)
            except Exception as exc:
                self.alert(exc)

    def backup_all(self):
        path, _ = QFileDialog.getSaveFileName(self, t("backup.save_all"), "daftar-full-backup.zip", "ZIP (*.zip)")
        if not path:
            return
        try:
            self.store.backup_all(path)
            self.statusBar().showMessage(t("backup.all_saved"), 7000)
        except Exception as exc:
            self.alert(exc)

    def restore(self):
        path, _ = QFileDialog.getOpenFileName(self, t("backup.restore_title"), "", "ZIP (*.zip)")
        if path:
            try:
                project_ids = self.store.restore_backup(path)
                self.refresh_projects()
                if project_ids:
                    self.open_project(project_ids[0])
                else:
                    self.home()
                settings = self.store.settings()
                set_language(settings.get("language", "fa"))
                QApplication.instance().setLayoutDirection(direction())
                self.setLayoutDirection(direction())
                # Rebuild for language/direction changes
                current = self.project_id
                self.close()
                new_window = MainWindow(self.store)
                new_window.setWindowIcon(self.windowIcon())
                if project_ids:
                    try:
                        new_window.open_project(project_ids[0])
                    except Exception:
                        new_window.home()
                else:
                    new_window.home()
                new_window.showMaximized()
                app = QApplication.instance()
                if app is not None:
                    app._main_window = new_window
                count = len(project_ids)
                new_window.statusBar().showMessage(
                    t("backup.restored", count=fa_digits(count)),
                    8000,
                )
                return
            except Exception as exc:
                self.alert(exc)

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, t("export.csv_title"), "records.csv", "CSV (*.csv)")
        if path:
            try:
                self.store.export_csv(self.project_id, path)
                self.statusBar().showMessage(t("export.csv_saved"), 5000)
            except Exception as exc:
                self.alert(exc)

    def export_project_json(self):
        if not self.project_id:
            return
        project_name = self.store.project(self.project_id)["name"]
        safe_name = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in project_name).strip("_") or "project"
        path, _ = QFileDialog.getSaveFileName(
            self, t("export.json_project_title"), f"{safe_name}.json", "JSON (*.json)",
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            self.store.export_project_json(self.project_id, path)
            self.statusBar().showMessage(t("export.json_project_saved"), 6000)
        except Exception as exc:
            self.alert(exc)

    def export_all_json(self):
        path, _ = QFileDialog.getSaveFileName(
            self, t("export.json_all_title"), "daftar-export.json", "JSON (*.json)",
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            self.store.export_all_json(path)
            self.statusBar().showMessage(t("export.json_all_saved"), 7000)
        except Exception as exc:
            self.alert(exc)

    def open_data(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.store.root)))
