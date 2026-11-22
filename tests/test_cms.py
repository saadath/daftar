import json
import os
import tempfile
import unittest
import uuid
import zipfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QFont, QTextListFormat
from PySide6.QtWidgets import QApplication, QHeaderView, QLabel, QPushButton, QStyle
from PySide6.QtWidgets import QToolButton
from PySide6.QtTest import QTest
from cms.storage import Store, FIELD_TYPES, display_value, attachment_items
from cms.widgets import Attachment, ClockTimeDialog, DatePicker, FieldInput, JalaliCalendar, RichEditor, button
from cms.dialogs import AboutDialog, RecordDialog, RecordView, ProjectDialog, FieldDialog
from cms.window import MainWindow, ResponsiveTable, format_bytes
from cms.theme import STYLESHEET


def field(kind="short_text", required=False):
    return {"id": uuid.uuid4().hex, "label": FIELD_TYPES[kind], "type": kind,
            "required": required, "options": ["اول", "دوم"], "calendar": "jalali"}


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "data")
        self.fields = [field(required=True), field("decimal")]
        self.pid = self.store.create("پروژه", "library", "توضیح", self.fields)

    def test_crud_schema_rename_and_isolation(self):
        data = {self.fields[0]["id"]: "کتاب", self.fields[1]["id"]: "123456789.123456789"}
        rid = self.store.save_record(self.pid, data)
        self.assertEqual(self.store.records(self.pid)[0]["data"], data)
        second = self.store.create("دوم", "library", "", [field()])
        self.assertEqual(self.store.records(second), [])
        self.fields.reverse()
        self.fields[1]["label"] = "عنوان جدید"
        self.store.update_project(self.pid, "ویرایش", "renamed.db", "", self.fields)
        self.assertTrue(self.store.database_path(self.pid).exists())
        self.assertEqual(self.store.database_path(self.pid).name, "renamed.sqlite3")
        self.assertEqual(self.store.fields(self.pid), self.fields)
        self.assertEqual(self.store.records(self.pid)[0]["data"], data)
        data[self.fields[1]["id"]] = "ویرایش کتاب"
        self.store.save_record(self.pid, data, rid)
        self.assertEqual(self.store.records(self.pid)[0]["data"], data)
        self.store.delete_records(self.pid, [rid])
        self.assertEqual(self.store.records(self.pid), [])

    def test_validation(self):
        with self.assertRaises(ValueError):
            self.store.save_record(self.pid, {})
        with self.assertRaises(ValueError):
            self.store.create("خطر", "../escape", "", self.fields)
        with self.assertRaises(ValueError):
            self.store.create("خطر", "CON", "", self.fields)
        changed = [dict(f) for f in self.fields]
        changed[0]["type"] = "number"
        self.store.update_project(self.pid, "نام", "library", "", changed)
        self.assertEqual(self.store.fields(self.pid)[0]["type"], "number")

    def test_field_type_change_migrates_values_and_rejects_unsafe_data(self):
        original = field("short_text")
        pid = self.store.create("تبدیل نوع", "migration", "", [original])
        good_id = self.store.save_record(pid, {original["id"]: "۱۲۳"})
        bad_id = self.store.save_record(pid, {original["id"]: "عدد نیست"})
        changed = [dict(original, type="number", placeholder="", min_length=0, max_length=None)]
        with self.assertRaisesRegex(ValueError, f"رکورد #{bad_id}"):
            self.store.update_project(pid, "تبدیل نوع", "migration", "", changed)
        # Failed conversion leaves schema, values, and SQLite untouched.
        self.assertEqual(self.store.fields(pid)[0]["type"], "short_text")
        self.assertEqual(self.store.records(pid)[0]["data"][original["id"]], "عدد نیست")
        self.store.delete_records(pid, [bad_id])
        self.store.update_project(pid, "تبدیل نوع", "migration", "", changed)
        migrated = self.store.records(pid)[0]
        self.assertEqual(migrated["id"], good_id)
        self.assertEqual(migrated["data"][original["id"]], 123)

        changed_again = [dict(changed[0], type="long_text", min_length=0, max_length=None)]
        self.store.update_project(pid, "تبدیل نوع", "migration", "", changed_again)
        self.assertEqual(self.store.records(pid)[0]["data"][original["id"]], "123")

    def test_text_and_integer_character_limits_are_enforced(self):
        short, long, number = field("short_text"), field("long_text"), field("number")
        short.update(min_length=2, max_length=4)
        long.update(min_length=3, max_length=5)
        number.update(min_length=2, max_length=3)
        schema = [short, long, number]
        pid = self.store.create("محدودیت", "limits", "", schema)
        with self.assertRaisesRegex(ValueError, "حداقل 2"):
            self.store.save_record(pid, {short["id"]: "ا", long["id"]: "abc", number["id"]: 12})
        with self.assertRaisesRegex(ValueError, "حداکثر 4"):
            self.store.save_record(pid, {short["id"]: "پنجحرف", long["id"]: "abc", number["id"]: 12})
        with self.assertRaisesRegex(ValueError, "حداکثر 3"):
            self.store.save_record(pid, {short["id"]: "متن", long["id"]: "abc", number["id"]: 1234})
        record_id = self.store.save_record(pid, {short["id"]: "نام", long["id"]: "متن", number["id"]: 123})
        self.assertIsNotNone(record_id)

    def test_unique_short_text_and_integer_values_are_enforced_on_create_and_edit(self):
        name, code = field("short_text"), field("number")
        name.update(label="نام یکتا", unique=True)
        code.update(label="کد یکتا", unique=True)
        pid = self.store.create("یکتایی", "unique_fields", "", [name, code])
        first = self.store.save_record(pid, {name["id"]: "کاربر اول", code["id"]: 101})
        second = self.store.save_record(pid, {name["id"]: "کاربر دوم", code["id"]: 102})

        with self.assertRaisesRegex(ValueError, "تکراری"):
            self.store.save_record(pid, {name["id"]: "کاربر اول", code["id"]: 103})
        with self.assertRaisesRegex(ValueError, "تکراری"):
            self.store.save_record(pid, {name["id"]: "کاربر سوم", code["id"]: 101})

        # An edit may retain its own existing values, but not copy another row.
        self.store.save_record(pid, {name["id"]: "کاربر اول", code["id"]: 101}, first)
        with self.assertRaisesRegex(ValueError, "تکراری"):
            self.store.save_record(pid, {name["id"]: "کاربر اول", code["id"]: 104}, second)
        self.assertEqual(len(self.store.records(pid)), 2)

    def test_enabling_unique_rejects_existing_duplicates_without_schema_change(self):
        name = field("short_text")
        pid = self.store.create("تکراری‌های قبلی", "legacy_duplicates", "", [name])
        self.store.save_record(pid, {name["id"]: "یکسان"})
        self.store.save_record(pid, {name["id"]: "یکسان"})
        changed = [dict(name, unique=True)]
        with self.assertRaisesRegex(ValueError, "رکوردهای"):
            self.store.update_project(pid, "تکراری‌های قبلی", "legacy_duplicates", "", changed)
        self.assertFalse(self.store.fields(pid)[0].get("unique", False))

    def test_exact_digit_integer_preserves_leading_zeroes_and_ignores_range(self):
        identity = field("number")
        identity.update(exact_digits=10, min_length=500, max_length=1)
        pid = self.store.create("شناسه", "identity", "", [identity])
        record_id = self.store.save_record(pid, {identity["id"]: "0012345678"})
        self.assertEqual(self.store.records(pid)[0]["data"][identity["id"]], "0012345678")
        with self.assertRaisesRegex(ValueError, "دقیقاً 10 رقم"):
            self.store.save_record(pid, {identity["id"]: "12345"})
        with self.assertRaisesRegex(ValueError, "فقط شامل رقم"):
            self.store.save_record(pid, {identity["id"]: "123456789a"})
        self.assertEqual(self.store.records(pid)[0]["id"], record_id)

    def test_integer_and_decimal_numeric_ranges_are_inclusive_and_enforced(self):
        integer = field("number")
        integer.update(label="تعداد", min_value=5, max_value=10)
        decimal = field("decimal")
        decimal.update(label="قیمت", min_value="1.25", max_value="9.75")
        pid = self.store.create("محدوده عددی", "numeric_ranges", "", [integer, decimal])

        first_id = self.store.save_record(pid, {integer["id"]: 5, decimal["id"]: "1.25"})
        self.store.save_record(pid, {integer["id"]: 10, decimal["id"]: "9.75"})
        with self.assertRaisesRegex(ValueError, "بزرگ‌تر یا مساوی 5"):
            self.store.save_record(pid, {integer["id"]: 4, decimal["id"]: "5.0"})
        with self.assertRaisesRegex(ValueError, "کوچک‌تر یا مساوی 10"):
            self.store.save_record(pid, {integer["id"]: 11, decimal["id"]: "5.0"})
        with self.assertRaisesRegex(ValueError, "بزرگ‌تر یا مساوی 1.25"):
            self.store.save_record(pid, {integer["id"]: 7, decimal["id"]: "1.249"})
        with self.assertRaisesRegex(ValueError, "کوچک‌تر یا مساوی 9.75"):
            self.store.save_record(pid, {integer["id"]: 7, decimal["id"]: "9.751"})
        self.assertEqual(len(self.store.records(pid)), 2)

        changed = [dict(integer, min_value=6), decimal]
        with self.assertRaisesRegex(ValueError, "رکورد #"):
            self.store.update_project(pid, "محدوده عددی", "numeric_ranges", "", changed)
        self.assertEqual(self.store.fields(pid)[0]["min_value"], 5)
        self.assertEqual(self.store.records(pid)[-1]["id"], first_id)

    def test_numeric_range_schema_requires_ordered_valid_bounds(self):
        integer = field("number")
        with self.assertRaisesRegex(ValueError, "نباید از حداکثر"):
            self.store.create("محدوده وارونه", "reversed_range", "", [dict(integer, min_value=10, max_value=2)])
        with self.assertRaisesRegex(ValueError, "محدودهٔ عددی"):
            self.store.create("محدوده نامعتبر", "invalid_range", "", [dict(integer, min_value="10")])

    def test_attachments_backup_restore_and_csv(self):
        attachment = field("file")
        self.fields.append(attachment)
        self.store.update_project(self.pid, "پروژه", "library", "", self.fields)
        source = self.root / "سند.txt"
        source.write_text("محتوای سند", encoding="utf-8")
        value = self.store.attach(self.pid, source)
        self.assertEqual(value["name"], "سند.txt")
        self.assertEqual(Path(value["path"]).name, "سند.txt")
        duplicate = self.store.attach(self.pid, source)
        self.assertEqual(duplicate["name"], "سند_1.txt")
        self.assertEqual(self.store.attachment_path(self.pid, duplicate).read_text(encoding="utf-8"), "محتوای سند")
        data = {self.fields[0]["id"]: "کتاب", attachment["id"]: value}
        self.store.save_record(self.pid, data)
        source.unlink()
        self.assertTrue(self.store.attachment_path(self.pid, value).exists())
        archive = self.root / "backup.zip"
        self.store.backup(self.pid, archive)
        restored = self.store.restore(archive)
        self.assertEqual(self.store.records(restored)[0]["data"], data)
        self.assertEqual(self.store.attachment_path(restored, value).read_text(encoding="utf-8"), "محتوای سند")
        self.assertEqual(self.store.attachment_path(restored, duplicate).read_text(encoding="utf-8"), "محتوای سند")
        destination = self.root / "export.csv"
        self.store.export_csv(restored, destination)
        self.assertIn("کتاب", destination.read_text(encoding="utf-8-sig"))
        self.store.delete_project(self.pid)
        self.assertEqual(len(self.store.projects()), 1)
        self.assertTrue(list((self.store.root / "trash").iterdir()))

    def test_full_backup_restores_multiple_projects_attachments_and_settings(self):
        attachment = field("file")
        pid_a = self.store.create("پروژه اول", "first", "توضیح اول", [attachment])
        source = self.root / "full-backup-attachment.txt"
        source.write_text("محتوای پشتیبان", encoding="utf-8")
        attached = self.store.attach(pid_a, source)
        self.store.save_record(pid_a, {attachment["id"]: attached})
        text_field = field("short_text")
        pid_b = self.store.create("پروژه دوم", "second", "توضیح دوم", [text_field])
        self.store.save_record(pid_b, {text_field["id"]: "دادهٔ دوم"})
        self.store.save_settings({"language": "fa", "layout_direction": "ltr", "theme": "light"})

        archive = self.root / "all-projects.zip"
        self.store.backup_all(archive)
        with zipfile.ZipFile(archive) as handle:
            manifest = json.loads(handle.read("manifest.json"))
            self.assertEqual(manifest["format"], "daftar-full-backup")
            self.assertEqual(len(manifest["projects"]), 3)  # fixture project plus two new projects
            self.assertIn("settings.json", handle.namelist())

        self.store.save_settings({"language": "fa", "layout_direction": "rtl", "theme": "light"})
        before = {project["id"] for project in self.store.projects()}
        restored_ids = self.store.restore_backup(archive)
        after = {project["id"] for project in self.store.projects()}
        self.assertEqual(len(restored_ids), 3)
        self.assertTrue(before.issubset(after))
        self.assertTrue(set(restored_ids).isdisjoint(before))
        self.assertEqual(self.store.settings()["layout_direction"], "ltr")

        restored_projects = [self.store.project(project_id) for project_id in restored_ids]
        restored_a = next(project for project in restored_projects if project["name"].startswith("پروژه اول"))
        restored_b = next(project for project in restored_projects if project["name"].startswith("پروژه دوم"))
        record_a = self.store.records(restored_a["id"])[0]
        self.assertEqual(record_a["data"][attachment["id"]], attached)
        self.assertEqual(self.store.attachment_path(restored_a["id"], attached).read_text(encoding="utf-8"), "محتوای پشتیبان")
        self.assertEqual(self.store.records(restored_b["id"])[0]["data"][text_field["id"]], "دادهٔ دوم")

    def test_legacy_single_project_archive_still_restores(self):
        legacy = self.root / "legacy-project.zip"
        metadata = self.store.project(self.pid)
        with zipfile.ZipFile(legacy, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("project.json", json.dumps(metadata, ensure_ascii=False))
            archive.write(self.store.database_path(self.pid), metadata["db_name"])
        restored_id = self.store.restore(legacy)
        self.assertEqual(self.store.project(restored_id)["name"], "پروژه (بازیابی)")

    def test_json_exports_include_project_records_and_full_app_settings(self):
        text = field("short_text")
        text["label"] = "نام فارسی"
        pid = self.store.create("پروژهٔ JSON", "json_project", "توضیح", [text])
        self.store.save_record(pid, {text["id"]: "نمونهٔ داده"})
        self.store.save_settings({"language": "fa", "layout_direction": "ltr", "theme": "light"})

        project_export = self.root / "exports" / "project.json"
        self.store.export_project_json(pid, project_export)
        project_payload = json.loads(project_export.read_text(encoding="utf-8"))
        self.assertEqual(project_payload["format"], "daftar-project-export")
        self.assertEqual(project_payload["project"]["name"], "پروژهٔ JSON")
        self.assertEqual(project_payload["fields"][0]["label"], "نام فارسی")
        self.assertEqual(project_payload["records"][0]["data"][text["id"]], "نمونهٔ داده")

        full_export = self.root / "exports" / "all.json"
        self.store.export_all_json(full_export)
        full_payload = json.loads(full_export.read_text(encoding="utf-8"))
        self.assertEqual(full_payload["format"], "daftar-full-export")
        self.assertEqual(full_payload["settings"]["layout_direction"], "ltr")
        project_names = {item["project"]["name"] for item in full_payload["projects"]}
        self.assertIn("پروژهٔ JSON", project_names)
        self.assertIn("پروژه", project_names)

    def test_multiple_attachments_and_allowed_extensions(self):
        image = field("image")
        image["allowed_extensions"] = ["jpg", "png"]
        pid = self.store.create("تصویرها", "images", "", [image])
        attachments = [
            {"path": "assets/a.png", "name": "a.png"},
            {"path": "assets/b.jpg", "name": "b.jpg"},
        ]
        self.store.save_record(pid, {image["id"]: attachments})
        value = self.store.records(pid)[0]["data"][image["id"]]
        self.assertEqual([item["name"] for item in attachment_items(value)], ["a.png", "b.jpg"])
        with self.assertRaisesRegex(ValueError, "پسوندهای مجاز"):
            self.store.save_record(pid, {image["id"]: [{"path": "assets/x.exe", "name": "x.exe"}]})
        self.assertEqual(display_value(value, image), "a.png، b.jpg")

    def test_untrusted_paths_rejected(self):
        with self.assertRaises(ValueError):
            self.store.attachment_path(self.pid, {"path": "../secret"})
        archive = self.root / "bad.zip"
        with zipfile.ZipFile(archive, "w") as handle:
            handle.writestr("../escape.txt", "bad")
        with self.assertRaises(ValueError):
            self.store.restore(archive)
        self.assertFalse((self.store.root / "escape.txt").exists())

    def test_project_database_and_media_sizes(self):
        folder = self.store.folder(self.pid)
        assets = folder / "assets" / "nested"
        assets.mkdir(parents=True)
        (assets / "image.jpg").write_bytes(b"1234567")
        (folder / (self.store.project(self.pid)["db_name"] + "-wal")).write_bytes(b"wal")
        row = self.store.projects()[0]
        self.assertEqual(row["media_count"], 1)
        self.assertEqual(row["media_size"], 7)
        self.assertGreaterEqual(row["db_size"], 3)
        self.assertIn("بایت", format_bytes(7))
        self.assertIn("کیلوبایت", format_bytes(2048))


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyleSheet(STYLESHEET)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "data")
        self.fields = [field(kind) for kind in FIELD_TYPES]
        self.pid = self.store.create("همه فیلدها", "all_fields", "", self.fields)

    def test_jalali_calendar_and_leap_days(self):
        picker = DatePicker("2024-03-20", "jalali")
        self.assertEqual(picker.value(), "2024-03-20")
        self.assertEqual(picker.jalali_button.text(), "1403/01/01")
        self.assertEqual(picker.gregorian_button.text(), "2024-03-20")
        picker.set_date(None)
        self.assertIsNone(picker.value())
        picker.today()
        self.assertIsNotNone(picker.value())
        picker.close()
        from datetime import date
        calendar = JalaliCalendar(date(2024, 3, 20))
        self.assertEqual(calendar.selected.year, 1403)
        self.assertEqual(calendar.grid.count(), 38)  # seven headings + 31 days
        calendar.year_picker.setValue(1402)
        calendar.month_picker.setCurrentIndex(11)
        self.assertEqual((calendar.year, calendar.month), (1402, 12))
        self.assertEqual(calendar.grid.count(), 36)
        calendar.close()

    def test_full_dynamic_form_save_edit_and_view(self):
        dialog = RecordDialog(self.store, self.pid)
        self.assertEqual(len(dialog.inputs), len(FIELD_TYPES))
        for item in dialog.inputs:
            kind = item.field["type"]
            if kind == "short_text":
                item.widget.setText("تست فارسی")
            elif kind == "number":
                item.widget.setText("۱۲۳")
            elif kind == "decimal":
                item.widget.setText("۱۲٫۳۴۵۶۷۸۹")
            elif kind == "checkbox":
                item.widget.setChecked(True)
            elif kind == "radio":
                item.group.buttons()[0].setChecked(True)
            elif kind == "select":
                item.widget.setCurrentIndex(1)
            elif kind in {"date", "datetime"}:
                item.widget.today()
            elif kind == "time":
                item.set_time_now()
            elif kind == "rich_text":
                item.widget.editor.setHtml("<b>متن غنی</b>")
            elif kind == "html":
                item.widget.source.setPlainText("<h2>HTML</h2>")
        dialog.save()
        self.assertIsNotNone(dialog.saved_id, dialog.error.text())
        record = self.store.records(self.pid)[0]
        values = {f["type"]: record["data"][f["id"]] for f in self.fields}
        self.assertEqual(values["number"], 123)
        self.assertEqual(values["decimal"], "12.3456789")
        self.assertRegex(values["time"], r"^\d{2}:\d{2}:\d{2}$")
        edit = RecordDialog(self.store, self.pid, record)
        self.assertEqual(edit.inputs[0].value(), "تست فارسی")
        edit.save()
        self.assertEqual(len(self.store.records(self.pid)), 1)
        viewer = RecordView(self.store, self.pid, record)
        viewer.show()
        self.app.processEvents()
        viewer.close()
        dialog.close()
        edit.close()

    def test_record_view_navigates_first_previous_next_last_and_position(self):
        title = self.fields[0]
        for value in ("رکورد الف", "رکورد ب", "رکورد پ"):
            self.store.save_record(self.pid, {title["id"]: value})
        records = self.store.records(self.pid)
        viewer = RecordView(self.store, self.pid, records[1], records=records)

        records = sorted(records, key=lambda item: item["id"])
        self.assertEqual(viewer.record["id"], records[1]["id"])
        self.assertEqual(viewer.position_spin.value(), 2)
        self.assertEqual(viewer.position_spin.suffix(), f" از {len(records)}")
        self.assertTrue(viewer.previous_button.isEnabled())
        self.assertTrue(viewer.next_button.isEnabled())
        self.assertTrue(viewer.first_button.isEnabled())
        self.assertTrue(viewer.last_button.isEnabled())
        for name in (
            "recordFirstButton", "recordPreviousButton", "recordNextButton",
            "recordLastButton", "recordGoButton",
        ):
            nav_button = viewer.findChild(QToolButton, name)
            self.assertIsNotNone(nav_button)
            self.assertFalse(nav_button.icon().isNull())

        self.assertNotEqual(
            viewer.first_button.icon().pixmap(24, 24).toImage().cacheKey(),
            viewer.last_button.icon().pixmap(24, 24).toImage().cacheKey(),
        )

        viewer.next_button.click()
        self.assertEqual(viewer.record["id"], records[2]["id"])
        self.assertEqual(viewer.position_spin.value(), 3)
        self.assertFalse(viewer.next_button.isEnabled())
        self.assertFalse(viewer.last_button.isEnabled())
        viewer.first_button.click()
        self.assertEqual(viewer.record["id"], records[0]["id"])
        self.assertEqual(viewer.position_spin.value(), 1)
        self.assertFalse(viewer.previous_button.isEnabled())
        self.assertFalse(viewer.first_button.isEnabled())
        viewer.position_spin.setValue(2)
        viewer.go_button.click()
        self.assertEqual(viewer.record["id"], records[1]["id"])
        viewer.last_button.click()
        self.assertEqual(viewer.record["id"], records[-1]["id"])
        self.assertEqual(viewer.position_spin.value(), len(records))
        viewer.close()

    def test_time_picker_is_24_hour_and_can_set_now_or_clear(self):
        editor = FieldInput(field("time"), self.store, self.pid)
        self.assertEqual(editor.time.displayFormat(), "HH:mm")
        self.assertRegex(editor.value(), r"^\d{2}:\d{2}:\d{2}$")
        editor.set_time_now()
        self.assertRegex(editor.value(), r"^\d{2}:\d{2}:\d{2}$")
        editor.clear_time()
        self.assertIsNone(editor.value())

    def test_attachment_widget_shows_multiple_items_and_preserves_legacy_single_value(self):
        source_a = self.store.root / "first.txt"
        source_b = self.store.root / "second.txt"
        source_a.write_text("one", encoding="utf-8")
        source_b.write_text("two", encoding="utf-8")
        first = self.store.attach(self.pid, source_a)
        second = self.store.attach(self.pid, source_b)
        legacy = Attachment(self.store, self.pid, "file", first)
        self.assertEqual(legacy.value(), [first])
        self.assertEqual(legacy.preview_layout.count(), 1)
        multi = Attachment(self.store, self.pid, "file", [first, second])
        self.assertEqual(multi.value(), [first, second])
        self.assertEqual(multi.preview_layout.count(), 2)
        self.assertGreaterEqual(multi.preview_area.minimumHeight(), 340)
        self.assertEqual(len(multi.findChildren(QToolButton, "attachmentIconButton")), 2)
        delete_buttons = multi.findChildren(QToolButton, "attachmentDeleteButton")
        self.assertEqual(len(delete_buttons), 2)
        self.assertTrue(all(not button.icon().isNull() for button in delete_buttons))
        self.assertTrue(all(button.accessibleName() == "حذف پیوست" for button in delete_buttons))
        open_buttons = multi.findChildren(QToolButton, "attachmentIconButton")
        self.assertTrue(all(not button.icon().isNull() for button in open_buttons))
        self.assertEqual(len({button.parentWidget() for button in delete_buttons + open_buttons}), 2)
        self.assertTrue(all(button.parentWidget().parentWidget().size().width() == 210 for button in delete_buttons + open_buttons))
        multi.remove("existing", 0)
        self.assertEqual(multi.value(), [second])

    def test_field_dialog_configures_placeholders_and_character_ranges(self):
        for kind in ("short_text", "long_text", "number"):
            dialog = FieldDialog()
            dialog.name.setText("فیلد محدود")
            dialog.kind.setCurrentIndex(dialog.kind.findData(kind))
            self.assertTrue(dialog.placeholder.isEnabled())
            self.assertTrue(dialog.minimum_length.isEnabled())
            self.assertTrue(dialog.maximum_length.isEnabled())
            dialog.placeholder.setText("نمونه ورودی")
            dialog.minimum_length.setValue(2)
            dialog.maximum_length.setValue(8)
            dialog.save()
            self.assertIsNotNone(dialog.result_field)
            self.assertEqual(dialog.result_field["placeholder"], "نمونه ورودی")
            self.assertEqual(dialog.result_field["min_length"], 2)
            self.assertEqual(dialog.result_field["max_length"], 8)
            dialog.close()

    def test_field_dialog_configures_integer_and_decimal_value_ranges(self):
        integer_dialog = FieldDialog()
        integer_dialog.name.setText("تعداد")
        integer_dialog.kind.setCurrentIndex(integer_dialog.kind.findData("number"))
        self.assertFalse(integer_dialog.value_range_label.isHidden())
        integer_dialog.minimum_value.setText("۱۰")
        integer_dialog.maximum_value.setText("۲۰")
        integer_dialog.save()
        self.assertEqual(integer_dialog.result_field["min_value"], 10)
        self.assertEqual(integer_dialog.result_field["max_value"], 20)
        integer_dialog.close()

        decimal_dialog = FieldDialog()
        decimal_dialog.name.setText("قیمت")
        decimal_dialog.kind.setCurrentIndex(decimal_dialog.kind.findData("decimal"))
        self.assertFalse(decimal_dialog.value_range_label.isHidden())
        decimal_dialog.minimum_value.setText("۱٫۲۵")
        decimal_dialog.maximum_value.setText("9.75")
        decimal_dialog.save()
        self.assertEqual(decimal_dialog.result_field["min_value"], "1.25")
        self.assertEqual(decimal_dialog.result_field["max_value"], "9.75")
        decimal_dialog.kind.setCurrentIndex(decimal_dialog.kind.findData("short_text"))
        self.assertTrue(decimal_dialog.value_range_label.isHidden())
        decimal_dialog.close()

    def test_field_dialog_can_toggle_list_visibility(self):
        original = field("short_text")
        original["show_in_list"] = False
        dialog = FieldDialog(original)
        self.assertFalse(dialog.show_in_list.isChecked())
        dialog.show_in_list.setChecked(True)
        dialog.save()
        self.assertTrue(dialog.result_field["show_in_list"])
        dialog.close()

    def test_list_visibility_and_unique_controls_only_apply_to_text_and_integer(self):
        for kind in ("short_text", "number"):
            dialog = FieldDialog()
            dialog.name.setText("فیلد قابل فهرست")
            dialog.kind.setCurrentIndex(dialog.kind.findData(kind))
            self.assertFalse(dialog.show_in_list.isHidden())
            self.assertFalse(dialog.unique.isHidden())
            dialog.show_in_list.setChecked(True)
            dialog.unique.setChecked(True)
            dialog.save()
            self.assertTrue(dialog.result_field["show_in_list"])
            self.assertTrue(dialog.result_field["unique"])
            dialog.close()

        for kind in ("long_text", "html", "rich_text", "date", "select"):
            dialog = FieldDialog()
            dialog.kind.setCurrentIndex(dialog.kind.findData(kind))
            self.assertTrue(dialog.show_in_list.isHidden())
            self.assertTrue(dialog.unique.isHidden())
            dialog.close()

    def test_short_text_field_hides_irrelevant_configuration_rows(self):
        dialog = FieldDialog()
        dialog.kind.setCurrentIndex(dialog.kind.findData("short_text"))
        for control in (
            dialog.exact_digits_label, dialog.exact_digits,
            dialog.options_label, dialog.options,
            dialog.calendar_label, dialog.calendar,
            dialog.allowed_extensions_label, dialog.allowed_extensions,
        ):
            self.assertTrue(control.isHidden())

        dialog.kind.setCurrentIndex(dialog.kind.findData("number"))
        self.assertFalse(dialog.exact_digits.isHidden())
        self.assertTrue(dialog.options.isHidden())
        dialog.kind.setCurrentIndex(dialog.kind.findData("select"))
        self.assertFalse(dialog.options.isHidden())
        self.assertTrue(dialog.calendar.isHidden())
        dialog.kind.setCurrentIndex(dialog.kind.findData("date"))
        self.assertFalse(dialog.calendar.isHidden())
        dialog.kind.setCurrentIndex(dialog.kind.findData("image"))
        self.assertFalse(dialog.allowed_extensions.isHidden())
        self.assertTrue(dialog.length_label.isHidden())
        self.assertTrue(dialog.length_widget.isHidden())
        dialog.kind.setCurrentIndex(dialog.kind.findData("short_text"))
        self.assertFalse(dialog.length_label.isHidden())
        self.assertFalse(dialog.length_widget.isHidden())
        dialog.kind.setCurrentIndex(dialog.kind.findData("html"))
        self.assertTrue(dialog.placeholder_label.isHidden())
        self.assertTrue(dialog.placeholder.isHidden())
        dialog.name.setText("HTML")
        dialog.placeholder.setText("legacy hint")
        dialog.save()
        self.assertEqual(dialog.result_field["placeholder"], "")
        dialog.close()

    def test_project_table_only_shows_fields_selected_for_list(self):
        title = field("short_text")
        title.update(label="عنوان کتاب", show_in_list=True)
        html_field = field("html")
        html_field.update(label="جزئیات HTML", show_in_list=True)
        project_id = self.store.create("کتابخانهٔ فهرست محدود", "list_columns", "", [title, html_field])
        self.store.save_record(project_id, {title["id"]: "کتاب اول", html_field["id"]: "<p>متن پنهان</p>"})
        window = MainWindow(self.store)
        window.open_project(project_id)
        self.assertEqual(window.records_table.columnCount(), 2)
        self.assertEqual(window.records_table.horizontalHeaderItem(1).text(), "عنوان کتاب")
        self.assertNotIn("جزئیات HTML", [window.records_table.horizontalHeaderItem(i).text() for i in range(window.records_table.columnCount())])
        self.assertEqual(len(RecordDialog(self.store, project_id).inputs), 2)
        window.close()

    def test_record_table_columns_stretch_to_fill_available_width(self):
        columns = [field(kind) for kind in ("short_text", "long_text", "number", "date", "time")]
        for index, item in enumerate(columns, 1):
            item["label"] = f"ستون {index}"
        project_id = self.store.create("ستون‌های کشسان", "stretch_columns", "", columns)
        self.store.save_record(project_id, {})
        window = MainWindow(self.store)
        window.show()
        window.open_project(project_id)
        self.app.processEvents()
        header = window.records_table.horizontalHeader()
        self.assertTrue(all(
            header.sectionResizeMode(column) == QHeaderView.ResizeMode.Fixed
            for column in range(window.records_table.columnCount())
        ))
        self.assertEqual(
            header.defaultAlignment(),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignAbsolute,
        )
        self.assertIsInstance(window.records_table, ResponsiveTable)
        self.assertEqual(window.records_table.columnCount(), 3)
        self.assertEqual(window.records_table.rowCount(), 1)
        for column in range(window.records_table.columnCount()):
            self.assertEqual(
                window.records_table.item(0, column).textAlignment(),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignAbsolute,
            )
        self.assertNotEqual(len(set(window.records_table._column_weights)), 1)
        self.assertGreater(window.records_table.columnWidth(1), window.records_table.columnWidth(2))
        self.assertAlmostEqual(
            window.records_table.columnWidth(1) / window.records_table.columnWidth(2),
            1.25 / 0.75,
            delta=0.05,
        )
        self.assertLessEqual(
            abs(sum(window.records_table.columnWidth(column) for column in range(window.records_table.columnCount()))
                - window.records_table.viewport().width()),
            2,
        )
        window.resize(window.width() + 240, window.height())
        self.app.processEvents()
        self.assertLessEqual(
            abs(sum(window.records_table.columnWidth(column) for column in range(window.records_table.columnCount()))
                - window.records_table.viewport().width()),
            2,
        )
        window.close()

    def test_existing_field_type_is_editable_and_constraints_reset(self):
        original = field("short_text")
        original.update(min_length=2, max_length=20, placeholder="متن")
        dialog = FieldDialog(original)
        self.assertTrue(dialog.kind.isEnabled())
        dialog.kind.setCurrentIndex(dialog.kind.findData("date"))
        dialog.save()
        self.assertEqual(dialog.result_field["type"], "date")
        self.assertEqual(dialog.result_field["min_length"], 0)
        self.assertIsNone(dialog.result_field["max_length"])
        dialog.close()

    def test_exact_digits_setting_disables_minimum_and_maximum(self):
        dialog = FieldDialog()
        dialog.name.setText("کد ملی")
        dialog.kind.setCurrentIndex(dialog.kind.findData("number"))
        dialog.minimum_length.setValue(3)
        dialog.maximum_length.setValue(20)
        dialog.exact_digits.setValue(10)
        self.assertFalse(dialog.minimum_length.isEnabled())
        self.assertFalse(dialog.maximum_length.isEnabled())
        self.assertEqual((dialog.minimum_length.value(), dialog.maximum_length.value()), (0, 0))
        dialog.save()
        self.assertEqual(dialog.result_field["exact_digits"], 10)
        self.assertEqual(dialog.result_field["min_length"], 0)
        self.assertIsNone(dialog.result_field["max_length"])
        self.assertEqual(dialog.minimum_length.specialValueText(), "")
        dialog.close()

    def test_field_inputs_apply_placeholder_and_maximum_length(self):
        short = field("short_text")
        short.update(placeholder="عنوان", min_length=2, max_length=4)
        widget = FieldInput(short, self.store, self.pid)
        self.assertEqual(widget.widget.placeholderText(), "عنوان")
        self.assertEqual(widget.widget.maxLength(), 4)
        widget.widget.setText("abcdef")
        self.assertEqual(widget.widget.text(), "abcd")
        with self.assertRaisesRegex(ValueError, "حداقل 2"):
            widget.validate_length("x")

        long = field("long_text")
        long.update(placeholder="توضیحات", max_length=5)
        editor = FieldInput(long, self.store, self.pid)
        self.assertEqual(editor.widget.placeholderText(), "توضیحات")
        editor.widget.setPlainText("12345678")
        self.app.processEvents()
        self.assertEqual(len(editor.widget.toPlainText()), 5)

        number = field("number")
        number.update(placeholder="شماره", max_length=3)
        numeric = FieldInput(number, self.store, self.pid)
        self.assertEqual(numeric.widget.placeholderText(), "شماره")
        self.assertEqual(numeric.widget.maxLength(), 3)

    def test_rich_editor_toolbar_features_generate_formatted_html(self):
        editor = RichEditor()
        editor.editor.setPlainText("نمونه متن")
        editor.set_direction(Qt.LayoutDirection.RightToLeft)
        self.assertEqual(editor.editor.textCursor().blockFormat().layoutDirection(), Qt.LayoutDirection.RightToLeft)
        editor.set_alignment(Qt.AlignmentFlag.AlignHCenter)
        self.assertEqual(editor.editor.textCursor().blockFormat().alignment(), Qt.AlignmentFlag.AlignHCenter)
        for level in range(1, 7):
            editor.set_heading(level)
            self.assertEqual(editor.editor.textCursor().blockFormat().headingLevel(), level)
            html = editor.value().lower()
            self.assertIn(f"<h{level}", html)
        editor.bold()
        editor.italic()
        editor.underline()
        char_format = editor.editor.currentCharFormat()
        self.assertEqual(char_format.fontWeight(), QFont.Weight.Bold)
        self.assertTrue(char_format.fontItalic())
        self.assertTrue(char_format.fontUnderline())
        editor.insert_horizontal_rule()
        self.assertIn("<hr", editor.editor.toHtml())
        editor.insert_list(QTextListFormat.Style.ListDecimal)
        self.assertIsNotNone(editor.editor.textCursor().currentList())
        editor.insert_table_dimensions(2, 3)
        table_cursor = editor.editor.textCursor()
        self.assertEqual(table_cursor.currentTable().rows(), 2)
        self.assertEqual(table_cursor.currentTable().columns(), 3)
        self.assertTrue(editor.value())
        self.assertNotIn("<html", editor.value().lower())
        self.assertNotIn("<head", editor.value().lower())
        self.assertNotIn("<body", editor.value().lower())
        self.assertGreaterEqual(len(editor.findChildren(QToolButton)), 18)
        editor.close()

    def test_html_source_mode_stores_only_the_markup_fragment(self):
        editor = RichEditor("<p>متن ذخیره‌شده</p>", html_mode=True)
        editor.toggle_source()
        source = editor.source.toPlainText()
        self.assertIn("متن ذخیره‌شده", source)
        self.assertNotIn("<html", source.lower())
        self.assertNotIn("<head", source.lower())
        self.assertNotIn("<body", source.lower())
        editor.source.setPlainText("<!doctype html><html><head><title>نادیده</title></head><body><section><h2>متن فارسی</h2></section></body></html>")
        self.assertEqual(editor.value(), "<section><h2>متن فارسی</h2></section>")
        editor.close()

    def test_clock_picker_popup_has_round_hour_and_minute_faces(self):
        from PySide6.QtCore import QTime
        dialog = ClockTimeDialog(QTime(13, 45))
        self.assertEqual(dialog.clock_header.layoutDirection(), Qt.LayoutDirection.LeftToRight)
        self.assertEqual(dialog.hour_button.text(), "13")
        self.assertEqual(dialog.minute_button.text(), "45")
        self.assertEqual(dialog.face.mode, "hour")
        dialog.set_mode("minute")
        self.assertEqual(dialog.face.mode, "minute")
        self.assertEqual(dialog.face.minimumSize().width(), dialog.face.minimumSize().height())
        dialog.close()

    def test_clock_face_click_selects_hour_then_minute(self):
        from PySide6.QtCore import QTime
        dialog = ClockTimeDialog(QTime(8, 20))
        dialog.show()
        self.app.processEvents()
        face = dialog.face
        cx, cy, radius = face._center()
        QTest.mouseClick(face, Qt.MouseButton.LeftButton, pos=QPoint(round(cx + radius), round(cy)))
        self.assertEqual(dialog.value.hour(), 3)
        self.assertEqual(dialog.mode, "minute")
        cx, cy, radius = face._center()
        QTest.mouseClick(face, Qt.MouseButton.LeftButton, pos=QPoint(round(cx), round(cy - radius)))
        self.assertEqual(dialog.value.minute(), 0)
        dialog.close()

    def test_form_html_field_heading_buttons_write_heading_tags(self):
        html_field = field("html")
        editor = FieldInput(html_field, self.store, self.pid)
        editor.widget.editor.setPlainText("تیتر")
        editor.widget.editor.setFocus()
        for level in range(1, 7):
            heading_button = next(
                item for item in editor.widget.findChildren(QToolButton)
                if item.accessibleName() == f"عنوان سطح {level}"
            )
            heading_button.click()
            self.assertEqual(editor.widget.editor.textCursor().blockFormat().headingLevel(), level)
            rendered_html = editor.value().lower()
            self.assertIn(f"<h{level}", rendered_html)
            self.assertIn(f"{ {1: 24, 2: 20, 3: 17, 4: 15, 5: 13, 6: 11}[level] }pt", rendered_html)

    def test_medical_rich_text_heading_icons_use_each_clicked_heading_level(self):
        medical_field = field("rich_text")
        medical_field["label"] = "شرح معاینه"
        editor = FieldInput(medical_field, self.store, self.pid)
        editor.widget.editor.setPlainText("یادداشت پزشکی")
        for level in range(1, 7):
            heading_button = next(
                item for item in editor.widget.findChildren(QToolButton)
                if item.accessibleName() == f"عنوان سطح {level}"
            )
            heading_button.click()
            self.assertEqual(editor.widget.editor.textCursor().blockFormat().headingLevel(), level)
            self.assertIn(f"<h{level}", editor.value().lower())

    def test_exact_digit_number_editor_preserves_zeroes_and_checks_length(self):
        number = field("number")
        number.update(exact_digits=10, min_length=0, max_length=None)
        numeric = FieldInput(number, self.store, self.pid)
        numeric.widget.setText("0012345678")
        self.assertEqual(numeric.value(), "0012345678")
        numeric.widget.setText("123")
        with self.assertRaisesRegex(ValueError, "دقیقاً 10 رقم"):
            numeric.value()

    def test_main_window_search_and_project_editor(self):
        window = MainWindow(self.store)
        window.show()
        window.open_project(self.pid)
        self.assertEqual(window.records_table.columnCount(), 3)
        title_id = self.fields[0]["id"]
        self.store.save_record(self.pid, {title_id: "کتاب اول"})
        self.store.save_record(self.pid, {title_id: "سند دوم"})
        window.reload_records()
        self.assertEqual(window.records_table.rowCount(), 2)
        window.search.setText("کتاب")
        self.assertEqual(window.records_table.rowCount(), 1)
        self.assertEqual(window.records_table.item(0, 1).text(), "کتاب اول")
        editor = ProjectDialog(self.store, self.pid)
        self.assertEqual(editor.list.count(), len(FIELD_TYPES))
        editor.list.setCurrentRow(0)
        editor.move(1)
        self.assertEqual(editor.fields[1]["id"], title_id)
        editor.close()
        self.app.processEvents()
        window.close()

    def test_about_dialog_shows_developer_details_and_sidebar_entry(self):
        dialog = AboutDialog()
        texts = " ".join(widget.text() for widget in dialog.findChildren(QLabel))
        for value in ("دکتر هوشنگ سعادت", "ایران، شیراز", "drhsaadat@gmail.com", "۱۴۰۵"):
            self.assertIn(value, texts)
        email = dialog.findChild(QLabel, "aboutEmail")
        self.assertTrue(email.openExternalLinks())
        self.assertIn("mailto:drhsaadat@gmail.com", email.text())
        dialog.close()

        window = MainWindow(self.store)
        about_buttons = [
            item for item in window.findChildren(QPushButton)
            if item.accessibleName() == "دربارهٔ برنامه"
        ]
        self.assertEqual(len(about_buttons), 1)
        self.assertFalse(about_buttons[0].findChild(QLabel, "navIcon").pixmap().isNull())
        window.close()

    def test_projects_table_columns_fit_without_horizontal_scroll(self):
        for index in range(8):
            self.store.create(f"پروژه {index}", f"project_{index}", "", [field()])
        window = MainWindow(self.store)
        window.show()
        self.app.processEvents()
        view = window.projects_table
        self.assertEqual(view.columnCount(), 8)
        self.assertEqual(view.horizontalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.assertNotEqual(view.verticalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.assertLessEqual(view.height(), view.horizontalHeader().height() + 7 * 52 + 4)
        self.assertLessEqual(sum(view.columnWidth(i) for i in range(view.columnCount())), view.viewport().width() + 2)
        self.assertEqual(view.horizontalHeader().sectionSize(0), view.columnWidth(0))
        self.assertGreater(view.verticalScrollBar().maximum(), 0)
        window.close()

    def test_sidebar_navigation_button_is_right_aligned(self):
        item = button("＋   پروژهٔ جدید", kind="nav")
        self.assertTrue(item.layoutDirection() == Qt.LayoutDirection.RightToLeft)
        from PySide6.QtWidgets import QLabel
        caption = item.findChild(QLabel, "navText")
        icon = item.findChild(QLabel, "navIcon")
        self.assertEqual(caption.text(), "پروژهٔ جدید")
        self.assertTrue(caption.alignment() & Qt.AlignmentFlag.AlignRight)
        self.assertEqual(icon.text(), "＋")
        self.assertEqual(item.layout().contentsMargins().right(), 12)
        self.assertEqual(item.accessibleName(), "پروژهٔ جدید")
        for title, expected_icon in (("▦   همهٔ پروژه‌ها", "▦"), ("بازیابی نسخهٔ پشتیبان", "↶"), ("پوشهٔ داده‌ها", "▣")):
            nav_item = button(title, kind="nav")
            self.assertIsNotNone(nav_item.findChild(QLabel, "navText"))
            self.assertEqual(nav_item.findChild(QLabel, "navIcon").text(), expected_icon)

    def test_main_pages_are_vertically_scrollable_and_cards_are_compact(self):
        from PySide6.QtWidgets import QFrame, QLabel
        window = MainWindow(self.store)
        self.assertEqual(window.stack.widget(0).__class__.__name__, "PageScrollArea")
        self.assertEqual(window.stack.widget(1).__class__.__name__, "PageScrollArea")
        for index in range(window.stack.count()):
            page = window.stack.widget(index)
            self.assertEqual(page.horizontalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.assertEqual(page.verticalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        title = window.home_page.widget().findChildren(QLabel, "title")[0]
        self.assertEqual(title.text(), "داشبورد")
        cards = window.home_page.widget().findChildren(QFrame, "stat")
        self.assertEqual(len(cards), 3)
        self.assertTrue(all(card.maximumHeight() <= 82 for card in cards))
        window.close()


if __name__ == "__main__":
    unittest.main()
