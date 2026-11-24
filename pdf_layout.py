"""Keep a block (the signatures) whole across a page break.

QTextDocument happily splits a block between two pages. A builder wraps the block it wants
kept together in keep(...); paginate() then lays the document out, and if the block would
not fit in the space left on the last page, starts it on a new page instead.
"""

from PySide6.QtCore import QSizeF
from PySide6.QtGui import QTextDocument

START = "<!--KEEP-->"
END = "<!--/KEEP-->"
_SAFETY_PX = 12          # a little slack so a block that only just fits is not clipped


def keep(html: str) -> str:
    return START + html + END


def _layout(html: str, page_size: QSizeF) -> QTextDocument:
    doc = QTextDocument()
    doc.setHtml("<html><body>" + html + "</body></html>")
    doc.setPageSize(QSizeF(page_size))
    return doc


def paginate(html: str, page_size) -> str:
    """Return `html` with the keep(...) block on its own page when it doesn't fit."""
    if START not in html:
        return html
    head, rest = html.split(START, 1)
    tail, after = rest.split(END, 1)
    page_h = float(page_size.height())

    main = _layout(head, page_size)
    rect = main.documentLayout().blockBoundingRect(main.lastBlock())
    used = rect.bottom() - int(rect.top() // page_h) * page_h      # on the last page
    need = _layout(tail, page_size).size().height()

    # (if the content already runs to the bottom of the page, the block starts the next
    # page by itself — forcing a break there would only leave a blank page)
    if used + need + _SAFETY_PX > page_h and used < page_h - 40 and need <= page_h:
        tail = "<div style='page-break-before: always;'>" + tail + "</div>"
    return head + tail + after
