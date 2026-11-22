"""Launch the local, serverless CMS."""
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from cms.i18n import t, set_language, direction, is_rtl, field_types
from cms.storage import Store
from cms.window import MainWindow
from cms.theme import STYLESHEET


def _base_path() -> Path:
    """Directory containing bundled read-only assets."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def _data_path() -> Path:
    """Writable data directory next to the app/executable."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "data"
    return Path(__file__).resolve().parent / "data"


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Daftar CMS")
    app.setOrganizationName("Daftar")
    base = _base_path()
    icon_path = base / "assets" / "app_icon.svg"
    app.setWindowIcon(QIcon(str(icon_path)))
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    font_dir = base / "assets" / "fonts"
    for font_path in font_dir.glob("*.ttf"):
        QFontDatabase.addApplicationFont(str(font_path))
    app.setFont(QFont("Vazirmatn", 10))
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
    # Keep user data beside the application/executable.
    root = _data_path()
    try:
        store = Store(root)
        settings = store.settings()
        set_language(settings.get("language", "fa"))
        app.setLayoutDirection(direction())
        window = MainWindow(store)
        window.setWindowIcon(QIcon(str(icon_path)))
    except Exception as exc:
        QMessageBox.critical(None, t("app.startup_error"), str(exc))
        return 1
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
