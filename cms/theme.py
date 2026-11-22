STYLESHEET = """
* { font-family: 'Vazirmatn'; font-size: 10pt; }
QMainWindow, QDialog { background: #f3f5f9; color: #17243b; }
QWidget { color: #17243b; }
QLabel { background: transparent; }
QLabel#title { font-size: 23pt; font-weight: 700; color: #17243b; }
QLabel#subtitle, QLabel#muted { color: #738097; }
QLabel#section { font-size: 13pt; font-weight: 600; }
QLabel#brand { color: white; font-size: 24pt; font-weight: 700; }
QLabel#brandSub { color: #9aacca; font-size: 9pt; }
QFrame#sidebar { background: #152239; border: none; }
QFrame#card, QFrame#stat { background: white; border: 1px solid #e3e8f0; border-radius: 12px; }
QLabel#aboutBadge { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #8272f5, stop:1 #5443c4); color: white; border-radius: 16px; font-size: 24pt; font-weight: 700; }
QLabel#aboutName { font-size: 18pt; font-weight: 700; color: #17243b; }
QFrame#aboutCard { background: #f8f9fd; border: 1px solid #e6eaf3; border-radius: 12px; }
QLabel#aboutKey { color: #7b879c; font-size: 9pt; }
QLabel#aboutValue { color: #24344f; font-weight: 600; }
QLabel#aboutEmail { color: #5142b4; font-weight: 600; }
QFrame#datePanel, QFrame#attachmentPreview { background: white; border: 1px solid #e3e8f0; border-radius: 10px; }
QFrame#attachmentPreview:hover { border-color: #938be9; }
QLabel#attachmentThumbnail { background: #f7f8fc; border: 1px solid #e6eaf2; border-radius: 8px; }
QToolButton#attachmentIconButton { background: rgba(255,255,255,0.95); border: 1px solid #dce2ec; border-radius: 17px; padding: 5px; }
QToolButton#attachmentIconButton:hover { background: #eeebff; border-color: #8171df; }
QToolButton#attachmentDeleteButton { background: rgba(255,255,255,0.97); border: 1px solid #f1c5cc; border-radius: 17px; padding: 5px; }
QToolButton#attachmentDeleteButton:hover { background: #fff0f2; border-color: #d94358; }
QToolButton#clockValue { min-width: 62px; padding: 5px 10px; color: #5746c8; background: #eeebff; border: 1px solid #dcd6ff; border-radius: 8px; font-size: 19pt; font-weight: 700; }
QToolButton#recordFirstButton, QToolButton#recordPreviousButton, QToolButton#recordNextButton, QToolButton#recordLastButton, QToolButton#recordGoButton {
 background: #f7f8fd; border: 1px solid #dce2ec; border-radius: 10px; padding: 7px;
}
QToolButton#recordFirstButton:hover, QToolButton#recordPreviousButton:hover, QToolButton#recordNextButton:hover, QToolButton#recordLastButton:hover, QToolButton#recordGoButton:hover {
 background: #eeebff; border-color: #8171df;
}
QToolButton#recordFirstButton:pressed, QToolButton#recordPreviousButton:pressed, QToolButton#recordNextButton:pressed, QToolButton#recordLastButton:pressed, QToolButton#recordGoButton:pressed {
 background: #ddd7ff;
}
QToolButton#recordFirstButton:disabled, QToolButton#recordPreviousButton:disabled, QToolButton#recordNextButton:disabled, QToolButton#recordLastButton:disabled {
 background: #f1f2f6; border-color: #e7e9ef;
}
QSpinBox#recordPositionSpin { min-height: 28px; background: white; color: #5142b4; border: 1px solid #dcd6ff; border-radius: 9px; padding: 4px 8px; font-weight: 600; }
QFrame#stat { border-radius: 10px; }
QFrame#stat QLabel#number { font-size: 21pt; font-weight: 700; color: #635bdf; }
QWidget#richToolbar { background: #f8f9fd; border: 1px solid #e1e6ef; border-radius: 8px; }
QWidget#richToolbar QToolButton { color: #45546d; background: transparent; border: 1px solid transparent; border-radius: 6px; font-weight: 600; min-width: 34px; min-height: 32px; }
QWidget#richToolbar QToolButton:hover { color: #5746c8; background: #eeebff; border-color: #dcd6ff; }
QWidget#richToolbar QToolButton:pressed { background: #ddd7ff; }
QWidget#richToolbar QToolButton:focus { color: #5142b4; background: #eeebff; border-color: #8171df; }
QWidget#richToolbar QLabel { background: transparent; }
QWidget#richToolbar QPushButton { padding: 6px 10px; }
QFrame#richToolbarSeparator { color: #d9dfeb; }
QPushButton { background: white; border: 1px solid #dbe1eb; border-radius: 7px; padding: 9px 15px; color: #34435d; }
QPushButton:hover { border-color: #938be9; background: #f1efff; }
QPushButton:pressed { background: #e3dfff; }
QPushButton:disabled { color: #a7b1c0; background: #edf0f5; border-color: #e1e5ec; }
QPushButton#primary { background: #6757db; border-color: #6757db; color: white; font-weight: 600; }
QPushButton#primary:hover { background: #5746c8; }
QPushButton#danger { color: #c83e56; background: #fff2f4; border-color: #f4d2d9; }
QPushButton#nav { background: transparent; border: 1px solid transparent; border-radius: 9px; color: #e5ebf6; text-align: right; padding: 0; }
QPushButton#nav QLabel { background: transparent; color: #e5ebf6; }
QPushButton#nav QLabel#navIcon { color: #a99cfb; font-size: 13pt; font-weight: 700; }
QPushButton#nav:hover { background: #243550; border-color: #2b3e5c; }
QPushButton#nav:pressed { background: #304565; }
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTimeEdit {
 background: white; border: 1px solid #dce2ec; border-radius: 6px; padding: 8px; selection-background-color: #dcd7ff;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border: 1px solid #8171df; }
QLineEdit[invalid="true"], QFrame[invalid="true"] { border: 1px solid #d54a61; }
QLineEdit:read-only { background: #f8f9fc; }
QComboBox::drop-down { border: none; width: 25px; }
QTableWidget { background: white; alternate-background-color: #fafbfe; border: 1px solid #e3e8f0; border-radius: 8px; gridline-color: #eef1f6; selection-background-color: #ece8ff; selection-color: #392e84; }
QTableWidget::item { padding: 8px; border-bottom: 1px solid #eef1f6; }
QTableWidget#recordsTable { background: white; alternate-background-color: #fbfcff; border: 1px solid #e3e8f0; border-radius: 12px; selection-background-color: #ece8ff; selection-color: #392e84; }
QTableWidget#recordsTable::item { padding: 10px 16px; border: none; border-bottom: 1px solid #f1f3f9; }
QTableWidget#recordsTable::item:hover { background: #f7f5ff; }
QTableWidget#recordsTable::item:selected { background: #ece8ff; color: #392e84; }
QTableWidget#recordsTable QHeaderView::section { background: #f6f8fc; color: #64718a; border: none; border-bottom: 1px solid #e3e8f0; padding: 12px 16px; font-weight: 700; }
QTableWidget#recordsTable QHeaderView::section:first { border-top-right-radius: 12px; }
QTableWidget#recordsTable QHeaderView::section:last { border-top-left-radius: 12px; }
QTableWidget#recordsTable QTableCornerButton::section { background: #f6f8fc; border: none; }
QHeaderView::section { background: #f8f9fc; border: none; border-bottom: 1px solid #e3e8f0; padding: 12px 8px; color: #66748b; font-weight: 600; }
QListWidget { border: 1px solid #e0e6ef; background: white; border-radius: 8px; outline: none; padding: 5px; }
QListWidget::item { padding: 11px; border-radius: 6px; margin: 2px; }
QListWidget::item:selected { background: #ece8ff; color: #5142b4; }
QListWidget#projectNav { background: transparent; border: none; color: #c5d0e2; }
QListWidget#projectNav::item:selected { background: #344464; color: white; }
QListWidget#projectNav::item:hover { background: #24344f; }
QTabWidget::pane { border: 1px solid #e0e6ef; border-radius: 8px; background: white; padding: 8px; }
QTabBar::tab { padding: 11px 22px; background: #e9edf5; border: none; color: #65738a; }
QTabBar::tab:selected { background: white; color: #6353cc; border-bottom: 2px solid #6757db; }
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollArea#attachmentPreviewArea { background: transparent; }
QScrollBar:vertical { background: #eef1f6; width: 9px; margin: 0; border-radius: 4px; }
QScrollBar::handle:vertical { background: #c4cbd9; min-height: 35px; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QCheckBox, QRadioButton { padding: 5px; spacing: 8px; }
QCheckBox::indicator { width: 18px; height: 18px; }
QStatusBar { background: white; color: #718098; border-top: 1px solid #e3e8f0; }
QToolTip { color: #fff; background: #24344f; border: none; padding: 6px; }
QSplitter::handle { background: #e5e9f1; width: 2px; }
"""
