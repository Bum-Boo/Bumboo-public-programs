"""The authoritative palette. Keep docs/STYLE_GUIDE.md in sync."""

PALETTES = {
    "night": dict(
        background="#1E1E2E",
        surface="#282839",
        elevated="#313244",
        text="#CDD6F4",
        muted="#A6ADC8",
        accent="#CBA6F7",
        audio="#94E2D5",
        success="#A6E3A1",
        attention="#F9E2AF",
        error="#F38BA8",
        line="#45475A",
    ),
    "dawn": dict(
        background="#EFF1F5",
        surface="#E6E9EF",
        elevated="#DCE0E8",
        text="#4C4F69",
        muted="#5C5F77",
        accent="#7040B0",
        audio="#14766B",
        success="#356A35",
        attention="#775619",
        error="#B62C50",
        line="#ACB0BE",
    ),
}


def stylesheet(p):
    return f"""
    QWidget {{ background: {p["background"]}; color: {p["text"]};
      font-family: 'Noto Sans CJK KR', 'Noto Sans'; font-size: 14px; }}
    QMainWindow, QDialog {{ background: {p["background"]}; }}
    QLabel {{ background: transparent; }}
    QLabel#brand {{ font-family: 'Noto Serif', serif; font-size: 26px; font-weight: 600; }}
    QLabel#title {{ font-size: 23px; font-weight: 600; }}
    QLabel#subtitle, QLabel#muted {{ color: {p["muted"]}; font-size: 12px; }}
    QLabel#section {{ font-size: 16px; font-weight: 600; }}
    QLabel#eyebrow {{ color: {p["accent"]}; font-size: 11px; font-weight: 600; }}
    QFrame#panel {{ background: {p["surface"]}; border-radius: 16px; }}
    QFrame#taskrow {{ background: {p["surface"]}; border-radius: 12px; }}
    QPushButton {{ background: {p["elevated"]}; border: 1px solid transparent;
      border-radius: 8px; padding: 8px 14px; min-height: 20px; }}
    QPushButton:hover {{ border-color: {p["accent"]}; }}
    QPushButton:pressed {{ background: {p["line"]}; }}
    QPushButton:focus, QLineEdit:focus, QComboBox:focus {{ border: 2px solid {p["accent"]}; }}
    QPushButton#primary {{ background: {p["accent"]}; color: {p["background"]}; font-weight: 600; }}
    QPushButton:disabled {{ color: {p["muted"]}; background: {p["surface"]}; }}
    QTabWidget::pane {{ border: none; }}
    QTabBar::tab {{ color: {p["muted"]}; padding: 10px 18px; margin-right: 4px;
      border-bottom: 2px solid transparent; }}
    QTabBar::tab:selected {{ color: {p["accent"]}; border-bottom-color: {p["accent"]}; }}
    QTabBar::tab:hover {{ color: {p["text"]}; }}
    QLineEdit, QComboBox {{ background: {p["elevated"]}; border: 1px solid {p["line"]};
      border-radius: 8px; padding: 8px; selection-background-color: {p["accent"]};
      selection-color: {p["background"]}; }}
    QComboBox QAbstractItemView {{ background: {p["elevated"]}; color: {p["text"]};
      selection-background-color: {p["accent"]}; selection-color: {p["background"]}; }}
    QCheckBox {{ spacing: 12px; background: transparent; padding: 5px 0; }}
    QCheckBox::indicator {{ width: 20px; height: 20px; border-radius: 6px;
      background: {p["elevated"]}; border: 1px solid {p["line"]}; }}
    QCheckBox::indicator:checked {{ background: {p["accent"]}; border-color: {p["accent"]}; }}
    QCheckBox:focus {{ color: {p["accent"]}; }}
    QSlider::groove:horizontal {{ height: 5px; background: {p["line"]}; border-radius: 2px; }}
    QSlider::handle:horizontal {{ background: {p["accent"]}; width: 16px;
      margin: -6px 0; border-radius: 8px; }}
    QPlainTextEdit {{ background: {p["surface"]}; color: {p["text"]}; padding: 12px;
      border: 1px solid {p["line"]}; border-radius: 8px;
      selection-background-color: {p["accent"]}; selection-color: {p["background"]}; }}
    QScrollArea {{ border: none; }}
    QScrollBar:vertical {{ width: 8px; background: {p["background"]}; }}
    QScrollBar::handle:vertical {{ background: {p["line"]}; min-height: 26px; border-radius: 4px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QMenu {{ background: {p["surface"]}; color: {p["text"]}; border: 1px solid {p["line"]}; padding: 5px; }}
    QMenu::item {{ padding: 8px 20px; border-radius: 5px; }}
    QMenu::item:selected {{ background: {p["elevated"]}; color: {p["accent"]}; }}
    QToolTip {{ background: {p["elevated"]}; color: {p["text"]}; border: 1px solid {p["line"]}; padding: 6px; }}
    QMessageBox QLabel {{ min-width: 280px; }}
    """
