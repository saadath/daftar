"""SQLite persistence. Each project is a portable folder with its own database."""
from __future__ import annotations

import csv
import html
import json
import re
import shutil
import sqlite3
import tempfile
import uuid
import zipfile
from html.parser import HTMLParser
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path


from cms.i18n import t, field_types as _field_types


class _FieldTypes(dict):
    def _refresh(self):
        self.clear()
        self.update(_field_types())

    def __getitem__(self, key):
        self._refresh()
        return super().__getitem__(key)

    def get(self, key, default=None):
        self._refresh()
        return super().get(key, default)

    def items(self):
        self._refresh()
        return super().items()

    def values(self):
        self._refresh()
        return super().values()

    def keys(self):
        self._refresh()
        return super().keys()

    def __iter__(self):
        self._refresh()
        return super().__iter__()

    def __contains__(self, key):
        self._refresh()
        return super().__contains__(key)


FIELD_TYPES = _FieldTypes()
FIELD_TYPES._refresh()
FILE_TYPES = {"file", "image", "pdf"}

IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "bmp", "gif", "tif", "tiff", "ico"}
DEFAULT_APP_SETTINGS = {"language": "fa", "layout_direction": "rtl", "theme": "light"}


def attachment_items(value):
    if not value:
        return []
    return value if isinstance(value, list) else [value]


def attachment_extensions(field):
    configured = set(field.get("allowed_extensions", []))
    if field["type"] == "image":
        return configured or IMAGE_EXTENSIONS
    if field["type"] == "pdf":
        return {"pdf"}
    return configured


def validate_attachment_name(field, name):
    allowed = attachment_extensions(field)
    if allowed and Path(name).suffix.lower().lstrip(".") not in allowed:
        raise ValueError(f"نوع فایل «{name}» مجاز نیست. پسوندهای مجاز: {', '.join(sorted(allowed))}")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def validate_schema(fields):
    if not fields:
        raise ValueError(t("err.min_one_field"))
    names, ids = set(), set()
    for field in fields:
        name = str(field.get("label", "")).strip()
        if not name or name.casefold() in names:
            raise ValueError(t("err.field_names_unique"))
        names.add(name.casefold())
        if field.get("type") not in FIELD_TYPES:
            raise ValueError(t("err.field_type_invalid"))
        show_in_list = field.get("show_in_list", True)
        if not isinstance(show_in_list, bool):
            raise ValueError(t("err.show_in_list_invalid", name=name))
        unique = field.get("unique", False)
        if not isinstance(unique, bool):
            raise ValueError(t("err.unique_invalid", name=name))
        if unique and field["type"] not in {"short_text", "number"}:
            raise ValueError(t("err.unique_type_invalid", name=name))
        fid = field.get("id", "")
        if not re.fullmatch(r"[a-f0-9]{32}", fid) or fid in ids:
            raise ValueError(t("err.field_id_invalid"))
        ids.add(fid)
        extensions = field.get("allowed_extensions", [])
        if not isinstance(extensions, list) or any(not isinstance(ext, str) or not re.fullmatch(r"[a-z0-9]+", ext) for ext in extensions):
            raise ValueError(t("err.extensions_invalid", name=name))
        if field["type"] == "image" and set(extensions) - IMAGE_EXTENSIONS:
            raise ValueError(t("err.image_ext_only"))
        if field["type"] in {"radio", "select"}:
            options = field.get("options", [])
            if not options or any(not x.strip() for x in options) or len(set(options)) != len(options):
                raise ValueError(f"برای «{name}» گزینه‌های غیرخالی و بدون تکرار وارد کنید.")
        minimum = field.get("min_length", 0)
        maximum = field.get("max_length")
        exact_digits = field.get("exact_digits", 0)
        if maximum == 0:
            maximum = None
        if not isinstance(exact_digits, int) or isinstance(exact_digits, bool) or exact_digits < 0:
            raise ValueError(f"تعداد رقم دقیق فیلد «{name}» معتبر نیست.")
        if exact_digits and field["type"] != "number":
            raise ValueError(f"تعداد دقیق رقم فقط برای فیلد عددی «{name}» قابل استفاده است.")
        if not isinstance(minimum, int) or isinstance(minimum, bool) or minimum < 0:
            raise ValueError(t("err.min_length_invalid", name=name))
        if not exact_digits and maximum is not None and (not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < minimum):
            raise ValueError(t("err.max_length_invalid", name=name))
        if not exact_digits and field["type"] not in {"short_text", "long_text", "number"} and (minimum or maximum is not None):
                raise ValueError(t("err.length_type_invalid", name=name))
        min_value, max_value = field.get("min_value"), field.get("max_value")
        if field["type"] in {"number", "decimal"}:
            parsed = []
            for bound in (min_value, max_value):
                if bound is None:
                    parsed.append(None)
                    continue
                try:
                    if field["type"] == "number":
                        if isinstance(bound, bool) or not isinstance(bound, int):
                            raise ValueError
                        parsed.append(bound)
                    else:
                        decimal_bound = Decimal(str(bound))
                        if not decimal_bound.is_finite():
                            raise ValueError
                        parsed.append(decimal_bound)
                except (ValueError, InvalidOperation):
                    raise ValueError(t("err.num_range_invalid", name=name)) from None
            if parsed[0] is not None and parsed[1] is not None and parsed[0] > parsed[1]:
                raise ValueError(t("err.num_range_order", name=name))
        elif min_value is not None or max_value is not None:
            raise ValueError(t("err.num_range_type_invalid", name=name))


class _HTMLText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def _plain_text(value):
    parser = _HTMLText()
    parser.feed(value)
    parser.close()
    return " ".join("".join(parser.parts).split())


def _convert_field_value(value, old_field, new_field):
    if value is None or value == "":
        return value
    old_kind, new_kind = old_field["type"], new_field["type"]
    if old_kind == new_kind == "number" and new_field.get("exact_digits"):
        digits = new_field["exact_digits"]
        if old_field.get("exact_digits"):
            result = str(value)
        elif isinstance(value, int) and not isinstance(value, bool):
            result = str(value).zfill(digits)
        elif isinstance(value, str) and value.isascii() and value.isdigit():
            result = value
        else:
            raise ValueError("مقدار عددی برای طول دقیق قابل تبدیل نیست.")
        if len(result) != digits:
            raise ValueError(t("err.exact_digits", n=digits))
        return result
    if old_kind == new_kind == "number" and old_field.get("exact_digits") and not new_field.get("exact_digits"):
        try:
            return int(str(value))
        except ValueError:
            raise ValueError("مقدار کد عددی به عدد صحیح تبدیل نمی‌شود.") from None
    if old_kind == new_kind:
        return value
    text_kinds = {"short_text", "long_text", "rich_text", "html"}
    attachment_kinds = FILE_TYPES

    if old_kind in attachment_kinds and new_kind in attachment_kinds:
        return value
    if old_kind in text_kinds and new_kind in text_kinds:
        if old_kind in {"rich_text", "html"} and new_kind in {"short_text", "long_text"}:
            return _plain_text(value)
        if old_kind in {"short_text", "long_text"} and new_kind in {"rich_text", "html"}:
            return html.escape(value).replace("\n", "<br>")
        return value
    if old_kind == "number" and new_kind == "decimal":
        return str(value)
    if old_kind == "decimal" and new_kind == "number":
        try:
            decimal_value = Decimal(str(value))
            if decimal_value.is_finite() and decimal_value == decimal_value.to_integral_value():
                return int(decimal_value)
        except InvalidOperation:
            pass
        raise ValueError("عدد اعشاری بخش اعشاری دارد و به عدد صحیح تبدیل نمی‌شود.")
    if old_kind == "number" and new_kind in {"short_text", "long_text"}:
        return str(value)
    if old_kind == "decimal" and new_kind in {"short_text", "long_text"}:
        return str(value)
    if old_kind in {"short_text", "long_text"} and new_kind in {"number", "decimal"}:
        normalized = str(value).strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٫", "01234567890123456789."))
        from decimal import Decimal, InvalidOperation
        try:
            if new_kind == "number":
                if "." in normalized:
                    raise ValueError
                if new_field.get("exact_digits"):
                    if not normalized.isascii() or not normalized.isdigit():
                        raise ValueError
                    return normalized
                return int(normalized)
            number = Decimal(normalized)
            if number.is_finite():
                return str(number)
        except (ValueError, InvalidOperation):
            pass
        raise ValueError(f"مقدار «{value}» عدد معتبر برای نوع جدید نیست.")
    if old_kind == "checkbox" and new_kind in {"short_text", "long_text"}:
        return t("bool.yes") if value else t("bool.no")
    if old_kind in {"short_text", "long_text"} and new_kind == "checkbox":
        truthy = {"بله", "true", "1", "yes", "✓", "Yes"}
        falsy = {"خیر", "false", "0", "no", "✗"}
        normalized = str(value).strip().casefold()
        if normalized in truthy:
            return True
        if normalized in falsy:
            return False
        raise ValueError(f"مقدار «{value}» به کادر تأیید تبدیل نمی‌شود؛ از بله/خیر یا true/false استفاده کنید.")
    if old_kind in {"select", "radio"} and new_kind in {"short_text", "long_text"}:
        return str(value)
    if old_kind in {"short_text", "long_text"} and new_kind in {"select", "radio"}:
        if value in new_field.get("options", []):
            return value
        raise ValueError(f"مقدار «{value}» در گزینه‌های نوع جدید وجود ندارد.")
    if old_kind in {"select", "radio"} and new_kind in {"select", "radio"}:
        if value in new_field.get("options", []):
            return value
        raise ValueError(f"گزینهٔ «{value}» در گزینه‌های نوع جدید وجود ندارد.")
    if old_kind in {"date", "datetime"} and new_kind in {"short_text", "long_text"}:
        return str(value)
    if old_kind == "time" and new_kind in {"short_text", "long_text"}:
        return str(value)
    raise ValueError(t("err.type_convert_unsafe", old=FIELD_TYPES[old_kind], new=FIELD_TYPES[new_kind]))


def _validate_field_value(field, value):
    if value is None or value == "":
        return
    kind = field["type"]
    if kind in FILE_TYPES:
        for item in attachment_items(value):
            if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not isinstance(item.get("path"), str):
                raise ValueError(t("attach.invalid_data"))
            validate_attachment_name(field, item["name"])
    exact_digits = field.get("exact_digits", 0)
    if kind == "number" and exact_digits:
        if not isinstance(value, str) or not value.isascii() or not value.isdigit():
            raise ValueError(t("err.digits_only"))
        if len(value) != exact_digits:
            raise ValueError(t("err.exact_digits", n=exact_digits))
    elif kind == "number" and (not isinstance(value, int) or isinstance(value, bool)):
        raise ValueError(t("err.invalid_number"))
    if kind == "decimal":
        from decimal import Decimal, InvalidOperation
        try:
            numeric_value = Decimal(str(value))
            if not numeric_value.is_finite():
                raise InvalidOperation
        except InvalidOperation:
            raise ValueError(t("err.invalid_decimal")) from None
    elif kind == "number":
        numeric_value = int(value) if field.get("exact_digits") else value
    else:
        numeric_value = None
    if kind in {"number", "decimal"}:
        minimum, maximum = field.get("min_value"), field.get("max_value")
        if minimum is not None:
            lower = Decimal(str(minimum)) if kind == "decimal" else minimum
            if numeric_value < lower:
                raise ValueError(t("err.min_value", n=minimum))
        if maximum is not None:
            upper = Decimal(str(maximum)) if kind == "decimal" else maximum
            if numeric_value > upper:
                raise ValueError(t("err.max_value", n=maximum))
    if kind in {"short_text", "long_text", "number"} and not (kind == "number" and exact_digits):
        length = len(str(value))
        minimum, maximum = field.get("min_length", 0), field.get("max_length") or None
        if length < minimum:
            raise ValueError(t("err.min_chars", n=minimum))
        if maximum is not None and length > maximum:
            raise ValueError(t("err.max_chars", n=maximum))
    if kind in {"select", "radio"} and value not in field["options"]:
        raise ValueError(t("err.option_mismatch"))


class Store:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        if not self.settings_path.exists():
            self.save_settings(DEFAULT_APP_SETTINGS)
        with self.catalog() as con:
            con.execute("""CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, db_name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL)""")

    @property
    def settings_path(self):
        return self.root / "settings.json"

    def settings(self):
        try:
            value = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(t("err.settings_read", exc=exc)) from None
        if not isinstance(value, dict):
            raise ValueError("قالب تنظیمات برنامه معتبر نیست.")
        return value

    @staticmethod
    def _validate_settings(value):
        if not isinstance(value, dict):
            raise ValueError(t("err.settings_json_object"))
        if value.get("layout_direction", "rtl") not in {"rtl", "ltr"}:
            raise ValueError(t("err.settings_invalid"))
        if value.get("language", "fa") not in {"fa", "en"} or value.get("theme", "light") != "light":
            raise ValueError(t("err.settings_invalid"))

    def save_settings(self, value):
        self._validate_settings(value)
        temporary = self.settings_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.settings_path)

    @contextmanager
    def catalog(self):
        con = sqlite3.connect(self.root / "catalog.sqlite3", timeout=15)
        con.row_factory = sqlite3.Row
        try:
            with con:
                yield con
        finally:
            con.close()

    def folder(self, project_id):
        if not re.fullmatch(r"[a-f0-9]{32}", project_id):
            raise ValueError("شناسهٔ پروژه معتبر نیست.")
        return self.root / project_id

    def project(self, project_id):
        with self.catalog() as con:
            row = con.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if row is None:
            raise ValueError(t("err.project_not_found"))
        return dict(row)

    def database_path(self, project_id):
        p = self.project(project_id)
        return self.folder(project_id) / p["db_name"]

    @contextmanager
    def database(self, project_id):
        path = self.database_path(project_id)
        if not path.is_file():
            raise ValueError("فایل دیتابیس این پروژه پیدا نشد؛ مسیر داده‌ها را بررسی کنید.")
        con = sqlite3.connect(path, timeout=15)
        con.row_factory = sqlite3.Row
        try:
            with con:
                yield con
        finally:
            con.close()

    def projects(self):
        with self.catalog() as con:
            rows = [dict(r) for r in con.execute("SELECT * FROM projects ORDER BY created_at DESC")]
        for row in rows:
            folder = self.folder(row["id"])
            database_path = folder / row["db_name"]
            row["db_size"] = sum(
                path.stat().st_size for path in (database_path, Path(str(database_path) + "-wal"), Path(str(database_path) + "-shm"))
                if path.is_file()
            )
            media_root = folder / "assets"
            row["media_count"], row["media_size"] = 0, 0
            if media_root.is_dir():
                for path in media_root.rglob("*"):
                    try:
                        if path.is_file() and not path.is_symlink():
                            row["media_count"] += 1
                            row["media_size"] += path.stat().st_size
                    except OSError:
                        # Files can be moved externally while the dashboard refreshes.
                        continue
            try:
                with self.database(row["id"]) as con:
                    row["count"] = con.execute("SELECT COUNT(*) FROM records").fetchone()[0]
                row["error"] = ""
            except (sqlite3.Error, OSError, ValueError) as exc:
                row["count"] = 0
                row["error"] = str(exc)
        return rows

    @staticmethod
    def clean_db_name(name):
        name = name.strip()
        if name.lower().endswith((".sqlite3", ".sqlite", ".db")):
            name = name.rsplit(".", 1)[0]
        if not name or len(name) > 100 or re.search(r'[<>:"/\\|?*\x00-\x1f]', name) or name.endswith((".", " ")):
            raise ValueError("نام دیتابیس معتبر نیست؛ از حروف، اعداد، خط تیره و زیرخط استفاده کنید.")
        if name.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(10)), *(f"LPT{i}" for i in range(10))}:
            raise ValueError(t("err.db_name_reserved"))
        return name + ".sqlite3"

    def create(self, name, db_name, description, fields):
        name = name.strip()
        if not name:
            raise ValueError(t("err.project_name_required"))
        validate_schema(fields)
        db_name = self.clean_db_name(db_name)
        project_id = uuid.uuid4().hex
        folder = self.folder(project_id)
        folder.mkdir()
        try:
            con = sqlite3.connect(folder / db_name)
            try:
                with con:
                    con.execute("CREATE TABLE schema_info (id INTEGER PRIMARY KEY CHECK (id=1), fields TEXT NOT NULL)")
                    con.execute("INSERT INTO schema_info VALUES (1, ?)", (json.dumps(fields, ensure_ascii=False),))
                    con.execute("""CREATE TABLE records (id INTEGER PRIMARY KEY AUTOINCREMENT,
                        data TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
            finally:
                con.close()
            with self.catalog() as cat:
                cat.execute("INSERT INTO projects VALUES (?,?,?,?,?)", (project_id, name, db_name, description.strip(), now()))
        except Exception:
            shutil.rmtree(folder)
            raise
        return project_id

    def fields(self, project_id):
        with self.database(project_id) as con:
            return json.loads(con.execute("SELECT fields FROM schema_info WHERE id=1").fetchone()[0])

    def update_project(self, project_id, name, db_name, description, fields):
        if not name.strip():
            raise ValueError(t("err.project_name_required"))
        validate_schema(fields)
        old_fields = {f["id"]: f for f in self.fields(project_id)}
        new_fields = {f["id"]: f for f in fields}
        changed_fields = {
            field_id for field_id, field in new_fields.items()
            if field_id in old_fields and field != old_fields[field_id]
        }
        changed_types = {
            field_id for field_id in changed_fields
            if new_fields[field_id]["type"] != old_fields[field_id]["type"]
        }
        migrated_records = []
        if changed_fields:
            for record in self.records(project_id):
                data = record["data"]
                record_changed = False
                for field_id in changed_fields:
                    if field_id not in data:
                        continue
                    old_value = data[field_id]
                    old_field, new_field = old_fields[field_id], new_fields[field_id]
                    try:
                        if field_id in changed_types or old_field.get("exact_digits", 0) != new_field.get("exact_digits", 0):
                            data[field_id] = _convert_field_value(data[field_id], old_field, new_field)
                        _validate_field_value(new_field, data[field_id])
                    except (TypeError, ValueError) as exc:
                        raise ValueError(
                            f"تبدیل نوع فیلد «{new_field['label']}» در رکورد #{record['id']} انجام نشد: {exc} "
                            "\nنوع یا گزینه‌ها را طوری انتخاب کنید که مقدار قبلی قابل تبدیل باشد."
                        ) from None
                    record_changed = record_changed or data[field_id] != old_value or field_id in changed_types
                if record_changed:
                    migrated_records.append((json.dumps(data, ensure_ascii=False), now(), record["id"]))
        unique_fields = [field for field in fields if field.get("unique", False)]
        if unique_fields:
            records = self.records(project_id)
            migrated_by_id = {record_id: json.loads(data) for data, _, record_id in migrated_records}
            for record in records:
                if record["id"] in migrated_by_id:
                    record["data"] = migrated_by_id[record["id"]]
            self._validate_unique_values(unique_fields, records)
        db_name = self.clean_db_name(db_name)
        old_path = self.database_path(project_id)
        new_path = old_path.with_name(db_name)
        renamed = str(old_path) != str(new_path)
        if renamed and new_path.exists():
            raise ValueError(t("err.file_exists"))
        # Catalog transaction and compensating rename keep paths recoverable on errors.
        with self.catalog() as cat:
            if renamed:
                old_path.rename(new_path)
            try:
                con = sqlite3.connect(new_path)
                try:
                    with con:
                        if migrated_records:
                            con.executemany("UPDATE records SET data=?,updated_at=? WHERE id=?", migrated_records)
                        con.execute("UPDATE schema_info SET fields=? WHERE id=1", (json.dumps(fields, ensure_ascii=False),))
                        cat.execute("UPDATE projects SET name=?,db_name=?,description=? WHERE id=?",
                                    (name.strip(), db_name, description.strip(), project_id))
                finally:
                    con.close()
            except Exception:
                if renamed:
                    new_path.rename(old_path)
                raise

    def delete_project(self, project_id):
        # Move to a local trash first. Deletion is recoverable outside the UI.
        folder = self.folder(project_id)
        metadata = self.project(project_id)
        trash = self.root / "trash"
        trash.mkdir(exist_ok=True)
        target = trash / f"{project_id}_{uuid.uuid4().hex[:8]}"
        if folder.exists():
            (folder / "project.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
            folder.rename(target)
        try:
            with self.catalog() as con:
                con.execute("DELETE FROM projects WHERE id=?", (project_id,))
        except Exception:
            if target.exists():
                target.rename(folder)
            raise

    def records(self, project_id):
        with self.database(project_id) as con:
            return [{**dict(row), "data": json.loads(row["data"])}
                    for row in con.execute("SELECT * FROM records ORDER BY id DESC")]

    @staticmethod
    def _unique_value(field, value):
        if value is None or value == "":
            return None
        if field["type"] == "short_text":
            normalized = str(value).strip().casefold()
            return normalized or None
        if field.get("exact_digits"):
            return str(value)
        return int(value)

    @classmethod
    def _validate_unique_values(cls, fields, records, candidate=None, record_id=None):
        for field in fields:
            field_id = field["id"]
            values = {}
            for record in records:
                if record["id"] == record_id:
                    continue
                key = cls._unique_value(field, record["data"].get(field_id))
                if key is None:
                    continue
                values.setdefault(key, record["id"])
            if candidate is not None:
                key = cls._unique_value(field, candidate.get(field_id))
                if key is not None and key in values:
                    raise ValueError(t("err.unique_duplicate", label=field["label"], id=values[key]))
            else:
                duplicate = next(
                    ((key, first_id, record["id"]) for record in records
                     if (key := cls._unique_value(field, record["data"].get(field_id))) is not None
                     and (first_id := values.get(key)) is not None and first_id != record["id"]),
                    None,
                )
                if duplicate:
                    _, first_id, second_id = duplicate
                    raise ValueError(
                        f"نمی‌توان یکتایی فیلد «{field['label']}» را فعال کرد؛ "
                        f"مقدار تکراری در رکوردهای #{first_id} و #{second_id} وجود دارد."
                    )

    def validate_record(self, project_id, data, record_id=None):
        fields = self.fields(project_id)
        for field in fields:
            value = data.get(field["id"])
            missing = value is None or value == "" or value == [] or (field["type"] == "checkbox" and value is not True)
            if field.get("required") and missing:
                raise ValueError(t("err.field_required", label=field["label"]))
            try:
                _validate_field_value(field, value)
            except ValueError as exc:
                raise ValueError(f"«{field['label']}»: {exc}") from None
        unique_fields = [field for field in fields if field.get("unique", False)]
        if unique_fields:
            records = self.records(project_id)
            self._validate_unique_values(unique_fields, records, data, record_id)

    def save_record(self, project_id, data, record_id=None):
        self.validate_record(project_id, data, record_id)
        timestamp = now()
        with self.database(project_id) as con:
            if record_id is None:
                cur = con.execute("INSERT INTO records(data,created_at,updated_at) VALUES (?,?,?)",
                                  (json.dumps(data, ensure_ascii=False), timestamp, timestamp))
                return cur.lastrowid
            cur = con.execute("UPDATE records SET data=?,updated_at=? WHERE id=?",
                              (json.dumps(data, ensure_ascii=False), timestamp, record_id))
            if not cur.rowcount:
                raise ValueError(t("err.not_found_record"))
            return record_id

    def delete_records(self, project_id, ids):
        with self.database(project_id) as con:
            con.executemany("DELETE FROM records WHERE id=?", [(i,) for i in ids])

    def attach(self, project_id, source):
        source = Path(source)
        if not source.is_file():
            raise ValueError(f"فایل در دسترس نیست: {source.name}")
        folder = self.folder(project_id)
        assets = folder / "assets"
        assets.mkdir(exist_ok=True)
        # Preserve the original filename and extension; number collisions instead
        # of overwriting an attachment that may already belong to another record.
        name = source.name
        target = assets / name
        index = 1
        while target.exists():
            target = assets / f"{source.stem}_{index}{source.suffix}"
            index += 1
        relative = target.relative_to(folder)
        shutil.copy2(source, target)
        return {"path": relative.as_posix(), "name": target.name}

    def attachment_path(self, project_id, value):
        folder = self.folder(project_id).resolve()
        path = (folder / value["path"]).resolve()
        if not path.is_relative_to(folder / "assets"):
            raise ValueError("مسیر پیوست معتبر نیست.")
        return path

    def backup(self, project_id, destination):
        destination = Path(destination).resolve()
        folder = self.folder(project_id)
        if destination.is_relative_to(self.root):
            raise ValueError("نسخهٔ پشتیبان را بیرون از پوشهٔ داده‌ها ذخیره کنید.")
        metadata = self.project(project_id)
        # Online SQLite backup produces a consistent snapshot, including concurrent commits.
        with tempfile.TemporaryDirectory() as temp:
            snapshot = Path(temp) / metadata["db_name"]
            with self.database(project_id) as source:
                target = sqlite3.connect(snapshot)
                try:
                    source.backup(target)
                finally:
                    target.close()
            with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("manifest.json", json.dumps({
                    "format": "daftar-project-backup", "version": 1,
                }, ensure_ascii=False, indent=2))
                archive.writestr("project.json", json.dumps(metadata, ensure_ascii=False, indent=2))
                archive.write(snapshot, metadata["db_name"])
                assets = folder / "assets"
                if assets.exists():
                    for path in assets.rglob("*"):
                        if path.is_file():
                            archive.write(path, path.relative_to(folder).as_posix())

    def backup_all(self, destination):
        """Create one portable archive containing all projects and app settings."""
        destination = Path(destination).resolve()
        if destination.is_relative_to(self.root):
            raise ValueError("نسخهٔ پشتیبان را بیرون از پوشهٔ داده‌ها ذخیره کنید.")
        projects = self.projects()
        with tempfile.TemporaryDirectory() as temp:
            temp_root = Path(temp)
            catalog_snapshot = temp_root / "catalog.sqlite3"
            with self.catalog() as source:
                target = sqlite3.connect(catalog_snapshot)
                try:
                    source.backup(target)
                finally:
                    target.close()
            with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("manifest.json", json.dumps({
                    "format": "daftar-full-backup",
                    "version": 1,
                    "projects": [project["id"] for project in projects],
                }, ensure_ascii=False, indent=2))
                archive.writestr("settings.json", json.dumps(self.settings(), ensure_ascii=False, indent=2))
                archive.write(catalog_snapshot, "catalog.sqlite3")
                for metadata in projects:
                    project_id = metadata["id"]
                    folder = self.folder(project_id)
                    prefix = f"projects/{project_id}"
                    archive.writestr(f"{prefix}/project.json", json.dumps(metadata, ensure_ascii=False, indent=2))
                    snapshot = temp_root / f"{project_id}.sqlite3"
                    with self.database(project_id) as source:
                        target = sqlite3.connect(snapshot)
                        try:
                            source.backup(target)
                        finally:
                            target.close()
                    archive.write(snapshot, f"{prefix}/{metadata['db_name']}")
                    assets = folder / "assets"
                    if assets.exists():
                        for path in assets.rglob("*"):
                            if path.is_file() and not path.is_symlink():
                                archive.write(path, f"{prefix}/{path.relative_to(folder).as_posix()}")

    def restore(self, source):
        """Restore one legacy or project archive and return its new project ID."""
        try:
            with zipfile.ZipFile(source) as archive:
                manifest = json.loads(archive.read("manifest.json")) if "manifest.json" in archive.namelist() else {}
        except (OSError, zipfile.BadZipFile, KeyError, json.JSONDecodeError):
            manifest = {}
        if isinstance(manifest, dict) and manifest.get("format") == "daftar-full-backup":
            raise ValueError("برای پشتیبان چندپروژه‌ای از restore_backup استفاده کنید.")
        restored = self.restore_backup(source)
        if len(restored) != 1:
            raise ValueError("این فایل شامل چند پروژه است؛ از بازیابی پشتیبان کامل استفاده کنید.")
        return restored[0]

    @staticmethod
    def _validate_archive(archive):
        for item in archive.infolist():
            filename = item.filename
            target = Path(filename)
            if "\\" in filename or target.is_absolute() or ".." in target.parts or (target.parts and ":" in target.parts[0]):
                raise ValueError("مسیر نامعتبر در نسخهٔ پشتیبان.")

    @staticmethod
    def _validate_project_folder(folder, metadata):
        if not isinstance(metadata, dict) or not isinstance(metadata.get("name"), str):
            raise ValueError("مشخصات پروژه در نسخهٔ پشتیبان معتبر نیست.")
        db_name = Store.clean_db_name(metadata.get("db_name", ""))
        if db_name != metadata.get("db_name"):
            raise ValueError("نام دیتابیس پشتیبان معتبر نیست.")
        database_path = folder / db_name
        if not database_path.is_file():
            raise ValueError("فایل دیتابیس پروژه در نسخهٔ پشتیبان پیدا نشد.")
        con = sqlite3.connect(database_path)
        try:
            if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("دیتابیس پشتیبان آسیب دیده است.")
            validate_schema(json.loads(con.execute("SELECT fields FROM schema_info WHERE id=1").fetchone()[0]))
            con.execute("SELECT id,data,created_at,updated_at FROM records LIMIT 1")
        finally:
            con.close()
        return db_name

    def _install_project_folder(self, source_folder, name_suffix=" (بازیابی)"):
        metadata_path = source_folder / "project.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        db_name = self._validate_project_folder(source_folder, metadata)
        project_id = uuid.uuid4().hex
        folder = self.folder(project_id)
        try:
            shutil.copytree(source_folder, folder, ignore=shutil.ignore_patterns("manifest.json"))
            with self.catalog() as cat:
                cat.execute("INSERT INTO projects VALUES (?,?,?,?,?)", (project_id,
                            metadata["name"] + name_suffix, db_name, metadata.get("description", ""), now()))
        except Exception:
            if folder.exists():
                shutil.rmtree(folder)
            raise
        return project_id

    def restore_backup(self, source):
        """Restore a project archive or all projects from a full archive."""
        source = Path(source)
        if not source.is_file():
            raise ValueError(t("err.backup_not_found"))
        with tempfile.TemporaryDirectory() as temp:
            extracted = Path(temp)
            try:
                with zipfile.ZipFile(source) as archive:
                    self._validate_archive(archive)
                    archive.extractall(extracted)
            except zipfile.BadZipFile:
                raise ValueError(t("err.backup_invalid_zip")) from None

            manifest_path = extracted / "manifest.json"
            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    raise ValueError("فهرست فایل پشتیبان معتبر نیست.") from None
            else:
                manifest = {"format": "daftar-project-backup"}
            if not isinstance(manifest, dict):
                raise ValueError("فهرست فایل پشتیبان معتبر نیست.")

            archive_format = manifest.get("format")
            if archive_format == "daftar-project-backup":
                if not (extracted / "project.json").is_file():
                    raise ValueError("فایل project.json در پشتیبان پیدا نشد.")
                return [self._install_project_folder(extracted)]
            if archive_format != "daftar-full-backup":
                raise ValueError("نوع فایل پشتیبان پشتیبانی نمی‌شود.")
            if manifest.get("version") != 1 or not isinstance(manifest.get("projects"), list):
                raise ValueError("نسخهٔ پشتیبان کامل معتبر نیست.")
            project_folders = []
            seen_ids = set()
            for old_id in manifest["projects"]:
                if not isinstance(old_id, str) or not re.fullmatch(r"[a-f0-9]{32}", old_id) or old_id in seen_ids:
                    raise ValueError("شناسهٔ پروژه در پشتیبان معتبر نیست.")
                seen_ids.add(old_id)
                project_folder = extracted / "projects" / old_id
                if not project_folder.is_dir():
                    raise ValueError("پوشهٔ یکی از پروژه‌ها در پشتیبان پیدا نشد.")
                metadata_path = project_folder / "project.json"
                if not metadata_path.is_file():
                    raise ValueError("مشخصات یکی از پروژه‌ها در پشتیبان پیدا نشد.")
                try:
                    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                    self._validate_project_folder(project_folder, metadata)
                except (OSError, json.JSONDecodeError) as exc:
                    raise ValueError(f"مشخصات یکی از پروژه‌ها معتبر نیست: {exc}") from None
                project_folders.append(project_folder)

            settings_path = extracted / "settings.json"
            settings = None
            if settings_path.is_file():
                try:
                    settings = json.loads(settings_path.read_text(encoding="utf-8"))
                    self._validate_settings(settings)
                except (OSError, json.JSONDecodeError, ValueError) as exc:
                    raise ValueError(f"تنظیمات پشتیبان معتبر نیست: {exc}") from None
            restored = []
            previous_settings = self.settings()
            try:
                for project_folder in project_folders:
                    restored.append(self._install_project_folder(project_folder))
                if settings is not None:
                    self.save_settings(settings)
            except Exception:
                for project_id in restored:
                    try:
                        with self.catalog() as cat:
                            cat.execute("DELETE FROM projects WHERE id=?", (project_id,))
                    finally:
                        folder = self.folder(project_id)
                        if folder.exists():
                            shutil.rmtree(folder)
                self.save_settings(previous_settings)
                raise
            return restored

    def export_csv(self, project_id, destination):
        fields = self.fields(project_id)
        with open(destination, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(["شناسه", *[f["label"] for f in fields], "زمان ایجاد (UTC)"])
            for row in self.records(project_id):
                writer.writerow([row["id"], *[display_value(row["data"].get(f["id"]), f) for f in fields], row["created_at"]])

    def export_project_json(self, project_id, destination):
        """Export project metadata, field schema, and all records as UTF-8 JSON."""
        payload = {
            "format": "daftar-project-export",
            "version": 1,
            "project": self.project(project_id),
            "fields": self.fields(project_id),
            "records": self.records(project_id),
        }
        self._write_json_export(payload, destination)

    def export_all_json(self, destination):
        """Export all active projects, schemas, records, and app settings."""
        projects = []
        for metadata in self.projects():
            project_id = metadata["id"]
            projects.append({
                "project": self.project(project_id),
                "fields": self.fields(project_id),
                "records": self.records(project_id),
            })
        payload = {
            "format": "daftar-full-export",
            "version": 1,
            "exported_at": now(),
            "settings": self.settings(),
            "projects": projects,
        }
        self._write_json_export(payload, destination)

    @staticmethod
    def _write_json_export(payload, destination):
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".tmp")
        try:
            temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(destination)
        except Exception:
            if temporary.exists():
                temporary.unlink()
            raise


def display_value(value, field=None):
    if value is None or value == "" or value == []:
        return "—"
    if isinstance(value, list):
        return "، ".join(display_value(item) for item in value)
    if isinstance(value, bool):
        return t("bool.yes") if value else t("bool.no")
    if isinstance(value, dict):
        return value.get("name", "—")
    if field and field.get("type") in {"rich_text", "html"}:
        # GUI callers use QTextDocument for accurate HTML rendering; this is a text export.
        import html
        return html.unescape(re.sub("<[^>]+>", " ", str(value))).strip()
    if field and field.get("type") in {"date", "datetime"} and field.get("calendar") == "jalali":
        try:
            import jdatetime
            parsed = datetime.fromisoformat(value)
            date = jdatetime.date.fromgregorian(date=parsed.date()).strftime("%Y/%m/%d")
            return date + (" " + parsed.strftime("%H:%M") if field["type"] == "datetime" else "")
        except (ValueError, TypeError):
            pass
    return str(value)
