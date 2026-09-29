"""Shared application styling — finance theme, light + dark, glassmorphism."""

from PySide6.QtGui import QColor

# ---------------------------------------------------------------- palettes ----

# "Calm ledger" — flat surfaces, one hairline border, teal is the only brand hue,
# green/amber/red are status signals only, slate-teal neutrals.
PALETTES = {
    "light": {
        "grad": ("#f2f5f4", "#f2f5f4", "#f2f5f4"),   # kept for API; app bg is flat now
        "ground": "#f2f5f4",
        "on_bg": "#16211f",
        "surface": "#ffffff",
        "surface_border": "#dbe3e1",
        "text": "#16211f",
        "muted": "#576764",
        "faint": "#8a9a96",
        "heading": "#0a556a",
        "accent": "#0d7490",
        "accent_hover": "#0b6076",
        "accent_pressed": "#094a5c",
        "on_accent": "#ffffff",
        "input_bg": "#ffffff",
        "input_border": "#cdd7d4",
        "table_bg": "#ffffff",
        "table_alt": "#f5f8f7",
        "header_bg": "#eef3f2",
        "header_text": "#0a556a",
        "grid": "#e4eae8",
        "sel_bg": "#d7ecef",
        "sel_text": "#0c2f38",
        "nav_bg": "#eef2f1",
        "nav_text": "#43524f",
        "nav_hover_bg": "#e2ecec",
        "nav_active_bg": "#0d7490",
        "nav_active_text": "#ffffff",
        "secondary_bg": "#ffffff",
        "secondary_text": "#0a556a",
        "secondary_border": "#cdd7d4",
        "scroll": "rgba(22, 33, 31, 0.20)",
        "scroll_hover": "rgba(22, 33, 31, 0.38)",
        "msg_bg": "#ffffff",
        "editor_bg": "#ffffff",
        "disabled_bg": "#c8d2cf",
        "disabled_text": "#ffffff",
        "ok": "#157f3c",
        "warn": "#99690a",
        "danger": "#b42318",
        "danger_hover": "#8f160c",
    },
    "dark": {
        "grad": ("#0e1413", "#0e1413", "#0e1413"),
        "ground": "#0e1413",
        "on_bg": "#e4edea",
        "surface": "#151d1c",
        "surface_border": "#2a3634",
        "text": "#e4edea",
        "muted": "#9aaba7",
        "faint": "#6f807c",
        "heading": "#6ee7d3",
        "accent": "#17b3a4",
        "accent_hover": "#1cc7b6",
        "accent_pressed": "#139a8d",
        "on_accent": "#04211d",
        "input_bg": "#0f1717",
        "input_border": "#33403d",
        "table_bg": "#131b1a",
        "table_alt": "#182120",
        "header_bg": "#0f1716",
        "header_text": "#6ee7d3",
        "grid": "#26312f",
        "sel_bg": "#17403a",
        "sel_text": "#e9fbf6",
        "nav_bg": "#1a2322",
        "nav_text": "#9aaba7",
        "nav_hover_bg": "#21302d",
        "nav_active_bg": "#17b3a4",
        "nav_active_text": "#04211d",
        "secondary_bg": "#1a2322",
        "secondary_text": "#cfe0dc",
        "secondary_border": "#33403d",
        "scroll": "rgba(154, 171, 167, 0.30)",
        "scroll_hover": "rgba(154, 171, 167, 0.50)",
        "msg_bg": "#131b1a",
        "editor_bg": "#101817",
        "disabled_bg": "#2b3a37",
        "disabled_text": "#7f918d",
        "ok": "#56d07f",
        "warn": "#d8a63f",
        "danger": "#f0806f",
        "danger_hover": "#f6a89b",
    },
}


UI_FONT = "'Segoe UI', 'IBM Plex Sans', system-ui, -apple-system, sans-serif"


def _down_arrow_url(color: str) -> str:
    """Path of a small down-chevron PNG in `color` (QSS can't draw one itself)."""
    import os
    import tempfile
    from PySide6.QtCore import Qt, QPointF
    from PySide6.QtGui import QGuiApplication, QPixmap, QPainter, QPen

    if QGuiApplication.instance() is None:
        return ""
    folder = os.path.join(tempfile.gettempdir(), "bpas_ui")
    path = os.path.join(folder, f"down_{color.lstrip('#')}.png")
    try:
        if not os.path.exists(path):
            os.makedirs(folder, exist_ok=True)
            pm = QPixmap(28, 28)
            pm.fill(Qt.transparent)
            painter = QPainter(pm)
            painter.setRenderHint(QPainter.Antialiasing)
            pen = QPen(QColor(color), 3.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            painter.setPen(pen)
            painter.drawPolyline([QPointF(6, 10), QPointF(14, 18), QPointF(22, 10)])
            painter.end()
            pm.save(path)
    except OSError:
        return ""
    return path.replace("\\", "/")


def stylesheet(theme: str = "light") -> str:
    p = PALETTES.get(theme, PALETTES["light"])
    arrow = _down_arrow_url(p["muted"])
    combo_arrow = (f"QComboBox::down-arrow {{ image: url({arrow}); width: 14px; height: 14px; }}"
                   if arrow else "")
    return f"""
* {{
    font-size: 13px;
    font-family: {UI_FONT};
    color: {p['text']};
}}

QMainWindow, QDialog {{ background: {p['ground']}; }}
QWidget#appRoot {{ background: {p['ground']}; }}
QStackedWidget {{ background: transparent; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QWidget#viewBg {{ background: transparent; }}

QLabel#onBg {{ color: {p['on_bg']}; background: transparent; }}
QFrame#checkPanel QLabel {{ color: {p['text']}; background: transparent; }}
QFrame#checkPanelSep {{ background: {p['surface_border']}; border: none; }}

/* ---------- panels ---------- */
QFrame#glass, QFrame#statCard, QFrame#checkPanel {{
    background: {p['surface']};
    border: 1px solid {p['surface_border']};
    border-radius: 10px;
}}

QListWidget#setupNav {{
    background: transparent;
    border: none;
    outline: none;
    font-size: 13px;
}}
QListWidget#setupNav::item {{
    padding: 11px 14px;
    border-radius: 9px;
    margin: 2px 4px;
    color: {p['text']};
}}
QListWidget#setupNav::item:hover {{ background: {p['nav_hover_bg']}; }}
QListWidget#setupNav::item:selected {{
    background: {p['accent']};
    color: {p['on_accent']};
    font-weight: 700;
}}

QGroupBox {{
    background: {p['surface']};
    border: 1px solid {p['surface_border']};
    border-radius: 14px;
    margin-top: 14px;
    padding: 14px;
    font-weight: 700;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
    color: {p['heading']};
}}

/* ---------- primary buttons ---------- */
QPushButton {{
    background: {p['accent']};
    color: {p['on_accent']};
    border: none;
    border-radius: 10px;
    padding: 9px 18px;
    font-weight: 700;
}}
QPushButton:hover {{ background: {p['accent_hover']}; }}
QPushButton:pressed {{ background: {p['accent_pressed']}; }}
QPushButton:disabled {{ background: {p['disabled_bg']}; color: {p['disabled_text']}; }}

QPushButton#secondary {{
    background: {p['secondary_bg']};
    color: {p['secondary_text']};
    border: 1px solid {p['secondary_border']};
}}
QPushButton#secondary:hover {{ background: {p['nav_hover_bg']}; }}

QPushButton#danger {{ background: {p['danger']}; color: #ffffff; }}
QPushButton#danger:hover {{ background: {p['danger_hover']}; }}

/* ---------- nav strip ---------- */
QPushButton#nav {{
    background: {p['nav_bg']};
    color: {p['nav_text']};
    border: 1px solid {p['surface_border']};
    border-radius: 11px;
    padding: 9px 20px;
    font-weight: 700;
}}
QPushButton#nav:hover {{ background: {p['nav_hover_bg']}; }}
QPushButton#nav:checked {{
    background: {p['nav_active_bg']};
    color: {p['nav_active_text']};
    border: 1px solid {p['nav_active_bg']};
}}

/* ---------- inputs ---------- */
QLineEdit, QComboBox, QTextEdit, QAbstractSpinBox {{
    background: {p['input_bg']};
    color: {p['text']};
    border: 1px solid {p['input_border']};
    border-radius: 9px;
    padding: 7px 10px;
    selection-background-color: {p['accent']};
    selection-color: {p['on_accent']};
}}
QLineEdit:focus, QComboBox:focus, QTextEdit:focus {{
    border: 1px solid {p['accent']};
}}
QComboBox::drop-down {{ border: none; width: 28px; }}
{combo_arrow}
QAbstractSpinBox {{ padding-right: 22px; }}
QAbstractSpinBox::up-button {{
    subcontrol-origin: border; subcontrol-position: top right;
    width: 20px; border-left: 1px solid {p['input_border']};
    border-top-right-radius: 9px;
}}
QAbstractSpinBox::down-button {{
    subcontrol-origin: border; subcontrol-position: bottom right;
    width: 20px; border-left: 1px solid {p['input_border']};
    border-bottom-right-radius: 9px;
}}
QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {{
    background: {p['nav_hover_bg']};
}}
QAbstractSpinBox::up-arrow {{
    width: 0; height: 0; border-left: 4px solid transparent;
    border-right: 4px solid transparent; border-bottom: 6px solid {p['text']};
}}
QAbstractSpinBox::down-arrow {{
    width: 0; height: 0; border-left: 4px solid transparent;
    border-right: 4px solid transparent; border-top: 6px solid {p['text']};
}}
QComboBox QAbstractItemView {{
    background: {p['msg_bg']};
    color: {p['text']};
    border: 1px solid {p['input_border']};
    selection-background-color: {p['accent']};
    selection-color: {p['on_accent']};
}}

/* ---------- tables ---------- */
QTableWidget {{
    background: {p['table_bg']};
    color: {p['text']};
    alternate-background-color: {p['table_alt']};
    border: 1px solid {p['surface_border']};
    border-radius: 10px;
    gridline-color: {p['grid']};
    selection-background-color: {p['sel_bg']};
    selection-color: {p['sel_text']};
}}
QTableWidget::item {{ padding: 2px 8px; }}
QTableWidget::item:selected {{
    background: {p['sel_bg']};
    color: {p['sel_text']};
}}
QHeaderView::section {{
    background: {p['header_bg']};
    padding: 4px 8px;
    border: none;
    border-right: 1px solid {p['grid']};
    border-bottom: 1px solid {p['grid']};
    font-weight: 700;
    color: {p['header_text']};
}}
QHeaderView::section:vertical {{ padding: 2px 6px; }}
QTableCornerButton::section {{ background: {p['header_bg']}; border: none; }}

/* inline cell editor — opaque so the underlying text doesn't ghost through */
QTableWidget QLineEdit, QTableView QLineEdit, QAbstractItemView QLineEdit {{
    background: {p['editor_bg']};
    color: {p['text']};
    border: 2px solid {p['accent']};
    border-radius: 3px;
    padding: 1px 4px;
    selection-background-color: {p['accent']};
    selection-color: {p['on_accent']};
}}

/* ---------- tabs ---------- */
QTabWidget::pane {{
    border: 1px solid {p['surface_border']};
    border-radius: 8px;
    top: -1px;
}}
QTabBar {{ qproperty-drawBase: 0; }}
QTabBar::tab {{
    background: {p['nav_bg']};
    color: {p['nav_text']};
    padding: 6px 16px;
    border: 1px solid {p['surface_border']};
    border-bottom: none;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background: {p['accent']};
    color: {p['on_accent']};
    border-color: {p['accent']};
}}
QTabBar::tab:hover:!selected {{ background: {p['nav_hover_bg']}; }}

/* ---------- checkboxes / radios ---------- */
QCheckBox, QRadioButton {{ spacing: 6px; background: transparent; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {p['input_border']};
    background: {p['input_bg']};
}}
QCheckBox::indicator {{ border-radius: 3px; }}
QRadioButton::indicator {{ border-radius: 8px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: {p['accent']};
}}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {p['accent']};
    border-color: {p['accent']};
}}
QCheckBox::indicator:indeterminate {{
    background: {p['accent']};
    border-color: {p['accent']};
}}
QTableWidget::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {p['input_border']};
    border-radius: 3px;
    background: {p['input_bg']};
}}
QTableWidget::indicator:checked {{
    background: {p['accent']};
    border-color: {p['accent']};
}}

/* ---------- scrollbars ---------- */
QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
QScrollBar::handle:vertical {{
    background: {p['scroll']}; border-radius: 6px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {p['scroll_hover']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
QScrollBar::handle:horizontal {{
    background: {p['scroll']}; border-radius: 6px; min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{ background: {p['scroll_hover']}; }}

QMessageBox {{ background: {p['msg_bg']}; }}
QMessageBox QLabel {{ color: {p['text']}; }}
QToolTip {{
    background: {p['msg_bg']}; color: {p['text']};
    border: 1px solid {p['accent']};
}}
"""


# back-compat default (light)
APP_STYLESHEET = stylesheet("light")


def current_palette() -> dict:
    import db
    return PALETTES.get(db.get_setting("ui_theme", "light"), PALETTES["light"])


def chart_palette(theme: str = "light") -> dict:
    _pie_light = ["#0c4a5e", "#0e7490", "#0891b2", "#06b6d4", "#22d3ee",
                  "#0f766e", "#14b8a6", "#2dd4bf", "#5eead4"]
    _pie_dark = ["#22d3ee", "#06b6d4", "#0891b2", "#14b8a6", "#2dd4bf",
                 "#5eead4", "#0e7490", "#67e8f9", "#a5f3fc"]
    if theme == "dark":
        return {
            "bg": QColor("#151d1c"),
            "title": QColor("#6ee7d3"),
            "bar": QColor("#17b3a4"),
            "label": QColor("#9aaba7"),
            "grid": QColor(154, 171, 167, 40),
            "pie": [QColor(c) for c in _pie_dark],
        }
    return {
        "bg": QColor("#ffffff"),
        "title": QColor("#0a556a"),
        "bar": QColor("#0d7490"),
        "label": QColor("#576764"),
        "grid": QColor(22, 33, 31, 26),
        "pie": [QColor(c) for c in _pie_light],
    }
