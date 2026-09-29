"""Theme-aware colours for status banners (ok / warn / bad)."""

import db
from ui import style

_TINTS = {
    "light": {
        "ok":   ("#e4f3e8", "#136b34"),
        "warn": ("#fbf1d9", "#8a5a06"),
        "bad":  ("#fbe6e3", "#a51f13"),
    },
    "dark": {
        "ok":   ("#15291f", "#7ddaa0"),
        "warn": ("#2b2416", "#e0bd6b"),
        "bad":  ("#2e1a17", "#f4a79a"),
    },
}


def banner_qss(kind: str) -> str:
    theme = db.get_setting("ui_theme", "light")
    bg, fg = _TINTS.get(theme, _TINTS["light"]).get(kind, _TINTS["light"]["ok"])
    return (
        "font-size: 14px; font-weight: 700; padding: 9px 14px; border-radius: 8px;"
        f" background: {bg}; color: {fg};"
    )
