"""Shared helper so popup dialogs size themselves to their host window instead
of using their own default geometry (which can land partly under the taskbar)."""

from PySide6.QtGui import QGuiApplication


def fit_to_host(dialog):
    """Resize/position `dialog` to fill its parent window, staying within the
    screen's available area (above the taskbar). Call once from the dialog's
    showEvent, guarded by a `self._fitted` flag."""
    host = dialog.parent().window() if dialog.parent() else None
    scr = host.screen() if host else QGuiApplication.primaryScreen()
    avail = scr.availableGeometry()
    target = host.frameGeometry() if host else avail
    target = target.intersected(avail)
    deco_h = dialog.frameGeometry().height() - dialog.geometry().height()
    deco_w = dialog.frameGeometry().width() - dialog.geometry().width()
    dialog.resize(max(dialog.minimumWidth(), target.width() - deco_w),
                  max(dialog.minimumHeight(), target.height() - deco_h))
    dialog.move(target.x(), target.y())
