from PySide6.QtCharts import (
    QChart, QChartView, QBarSeries, QBarSet, QBarCategoryAxis, QValueAxis,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QColor, QBrush, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QPushButton, QFrame, QGridLayout, QScrollArea,
)

import db
from ui import style

GROUP_OPTIONS = [
    ("PAP Name", "pap_name"),
    ("GAD Category", "gad_category"),
    ("Accounting Title", "accounting_title"),
    ("Mode of Procurement", "mode_of_procurement"),
]


class DashboardScreen(QWidget):
    go_to_records = Signal()
    plan_changed = Signal()

    def __init__(self):
        super().__init__()
        self._loading = False
        self._build_ui()
        self.refresh()

    def _reload_plans(self):
        self._loading = True
        active = db.get_active_batch()
        self.plan_combo.clear()
        for b in db.list_batches():
            plan = db.get_plan(b["id"])
            parts = []
            if plan["school_name"]:
                parts.append(plan["school_name"]
                             + (f" — {plan['level']}" if plan["level"] else ""))
            if b["label"]:
                parts.append(b["label"])
            self.plan_combo.addItem("  ·  ".join(parts) or b["file_name"], b["id"])
        idx = self.plan_combo.findData(active)
        self.plan_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._loading = False

    def _on_plan_changed(self, _idx):
        if self._loading:
            return
        bid = self.plan_combo.currentData()
        if bid is not None:
            db.set_active_batch(bid)
        self.refresh()
        self.plan_changed.emit()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)

        # ---- empty state ----
        self.empty_widget = QWidget()
        ev = QVBoxLayout(self.empty_widget)
        ev.setAlignment(Qt.AlignCenter)
        ev.setSpacing(16)
        el = QLabel("No plan loaded.\n\nGo to Records to select your school and import "
                    "its BPAS Excel file.")
        el.setObjectName("onBg")
        el.setAlignment(Qt.AlignCenter)
        el.setStyleSheet("font-size: 16px;")
        eb = QPushButton("Go to Records")
        eb.setMinimumSize(180, 44)
        eb.clicked.connect(self.go_to_records.emit)
        ev.addWidget(el)
        ev.addWidget(eb, alignment=Qt.AlignCenter)
        root.addWidget(self.empty_widget)

        self.main_widget = QWidget()
        root.addWidget(self.main_widget)
        root = QVBoxLayout(self.main_widget)
        root.setContentsMargins(0, 0, 0, 0)

        top_row = QHBoxLayout()
        _p = QLabel("School / Plan:"); _p.setObjectName("onBg"); _p.setStyleSheet("font-weight: bold;")
        top_row.addWidget(_p)
        self.plan_combo = QComboBox()
        self.plan_combo.setMinimumWidth(320)
        self.plan_combo.currentIndexChanged.connect(self._on_plan_changed)
        top_row.addWidget(self.plan_combo)

        _g = QLabel("Group by:"); _g.setObjectName("onBg"); _g.setStyleSheet("font-weight: bold;")
        top_row.addWidget(_g)
        self.group_combo = QComboBox()
        for label, _ in GROUP_OPTIONS:
            self.group_combo.addItem(label)
        self.group_combo.currentIndexChanged.connect(self.refresh)
        top_row.addWidget(self.group_combo)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        top_row.addWidget(refresh_btn)
        top_row.addStretch()
        root.addLayout(top_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        root.addWidget(scroll)

        content = QWidget()
        content.setObjectName("viewBg")
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setSpacing(12)

        layout.addWidget(self._build_checking_panel())

        # Charts
        self.month_chart = QChartView()
        self.month_chart.setRenderHint(QPainter.Antialiasing)
        self.month_chart.setMinimumHeight(300)
        self.month_chart.setStyleSheet("background: transparent; border: none;")
        self.month_chart.setFrameShape(QFrame.Shape.NoFrame)
        layout.addWidget(self.month_chart)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Group", "Total Amount", "% of Budget"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        self.table.horizontalHeader().setMinimumHeight(34)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        layout.addWidget(self.table)

    def _build_checking_panel(self):
        box = QFrame()
        box.setObjectName("checkPanel")
        v = QVBoxLayout(box)
        v.setContentsMargins(18, 16, 18, 16)
        v.setSpacing(10)

        banner_row = QHBoxLayout()
        self.check_banner = QLabel()
        self.check_banner.setWordWrap(True)
        self.check_banner.setStyleSheet(
            "font-size: 14px; font-weight: bold; border: none; padding: 8px 12px;"
            " border-radius: 6px;"
        )
        banner_row.addWidget(self.check_banner, 1)
        edit_btn = QPushButton("Edit allotment")
        edit_btn.setObjectName("secondary")
        edit_btn.clicked.connect(self._edit_allotment)
        banner_row.addWidget(edit_btn, 0, Qt.AlignTop)
        v.addLayout(banner_row)

        cols = QHBoxLayout()
        cols.setSpacing(28)
        v.addLayout(cols)

        # -- allotment / GAD --
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(4)
        for c, text in enumerate(["", "Allotment", "GAD"]):
            lab = QLabel(text)
            lab.setStyleSheet("font-weight: bold; border: none; background: transparent;")
            grid.addWidget(lab, 0, c)
        self.check_cells = {}
        for r, (key, label) in enumerate([
            ("total", "Total allotment"), ("allocated", "Allocated"),
            ("balance", "Balance for allocation"), ("percent", "% allocated"),
        ], start=1):
            name_lab = QLabel(label)
            name_lab.setStyleSheet("border: none; background: transparent;"
                                   + (" font-weight: bold;" if key == "balance" else ""))
            grid.addWidget(name_lab, r, 0)
            for c, side in ((1, "allotment"), (2, "gad")):
                cell = QLabel("--")
                cell.setStyleSheet("border: none; background: transparent;")
                grid.addWidget(cell, r, c)
                self.check_cells[(key, side)] = cell
        cols.addLayout(grid)

        sep = QFrame()
        sep.setObjectName("checkPanelSep")
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedWidth(1)
        cols.addWidget(sep)

        # -- Annual Procurement Plan checking --
        app_grid = QGridLayout()
        app_grid.setHorizontalSpacing(24)
        app_grid.setVerticalSpacing(4)
        hdr = QLabel("Annual Procurement Plan")
        hdr.setStyleSheet("font-weight: bold; border: none; background: transparent;")
        app_grid.addWidget(hdr, 0, 0, 1, 2)
        self.app_cells = {}
        for r, (key, label) in enumerate([
            ("part1", "Part I"), ("part2", "Part II"), ("other_cse", "Other Items"),
            ("total_cse", "Total CSE"), ("total_noncse", "Total Non-CSE"),
        ], start=1):
            is_total = key in ("total_cse", "total_noncse")
            name_lab = QLabel(label)
            name_lab.setStyleSheet("border: none; background: transparent;"
                                   + (" font-weight: bold;" if is_total else ""))
            app_grid.addWidget(name_lab, r, 0)
            cell = QLabel("--")
            cell.setStyleSheet(
                "border: none; background: transparent;"
                + (" font-weight: bold; color: #0d9488;" if is_total else ""))
            cell.setTextInteractionFlags(Qt.TextSelectableByMouse)
            app_grid.addWidget(cell, r, 1)
            self.app_cells[key] = cell
        cols.addLayout(app_grid)
        cols.addStretch()
        return box

    def _edit_allotment(self):
        bid = db.get_active_batch()
        if bid is None:
            return
        from ui.plan_dialog import PlanDialog
        if PlanDialog(bid, self).exec() == PlanDialog.Accepted:
            self.refresh()
            self.plan_changed.emit()

    def _refresh_checking(self, batch_id):
        st = db.checking_status(batch_id)
        pairs = {
            "allotment": (st["total_allotment"], st["allocated"], st["balance"]),
            "gad": (st["gad_allotment"], st["gad_allocated"], st["gad_balance"]),
        }
        for side, (target, allocated, balance) in pairs.items():
            pct = (allocated / target * 100) if target else 0.0
            self.check_cells[("total", side)].setText(f"₱{target:,.2f}")
            self.check_cells[("allocated", side)].setText(f"₱{allocated:,.2f}")
            bcell = self.check_cells[("balance", side)]
            bcell.setText(f"{balance:,.2f}")
            bcell.setStyleSheet(
                "border: none; background: transparent; font-weight: bold; color: #0d9488;")
            self.check_cells[("percent", side)].setText(f"{pct:.2f}%")

        ap = db.app_checking(batch_id)
        for key, cell in self.app_cells.items():
            cell.setText(f"₱{ap[key]:,.2f}")

        if not st["allotment_set"]:
            self._set_banner("amber", "Set Total Allotment and GAD Allotment in Setup to enable budget checking.")
        elif not st["has_plan"]:
            self._set_banner("amber", "Import a plan to check it against the allotment.")
        elif st["balanced"]:
            self._set_banner("green", "Plan is balanced!")
        else:
            msgs = []
            if st["balance"] != 0.0:
                msgs.append(f"Allotment off by ₱{st['balance']:,.2f}")
            if st["gad_balance"] != 0.0:
                msgs.append(f"GAD off by ₱{st['gad_balance']:,.2f}")
            self._set_banner("red", "Not balanced — " + "; ".join(msgs) + ".")

    def _set_banner(self, tone, text):
        from ui.status import banner_qss
        kind = {"green": "ok", "amber": "warn", "red": "bad"}.get(tone, "ok")
        self.check_banner.setStyleSheet(banner_qss(kind) + " border: none;")
        self.check_banner.setText(text)

    def _current_column(self):
        return GROUP_OPTIONS[self.group_combo.currentIndex()][1]

    def refresh(self):
        has_plans = bool(db.list_batches())
        self.empty_widget.setVisible(not has_plans)
        self.main_widget.setVisible(has_plans)
        if not has_plans:
            return

        self._reload_plans()
        batch_id = db.get_active_batch()
        column = self._current_column()

        self._chart_pal = style.chart_palette(db.get_setting("ui_theme", "light"))

        self._refresh_checking(batch_id)

        rows = db.totals_by(column, batch_id)
        grand = sum(r["total"] or 0 for r in rows) or 1

        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            total = row["total"] or 0
            label = str(row["label"] or "(blank)")
            g_item = QTableWidgetItem(label)
            g_item.setToolTip(label)
            self.table.setItem(i, 0, g_item)
            amt = QTableWidgetItem(f"{total:,.2f}")
            amt.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(i, 1, amt)
            pct = QTableWidgetItem(f"{total / grand * 100:.1f}%")
            pct.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(i, 2, pct)

        self._fit_table_height()

        self._render_bar(self.month_chart, db.monthly_totals(batch_id),
                         "Budget by Month", color_cycle=False)

    def _fit_table_height(self):
        """Size the table to show every row with no inner scrollbar; the page
        itself scrolls to reach it, same as the rest of the Dashboard."""
        t = self.table
        header_h = t.horizontalHeader().height()
        rows_h = sum(t.rowHeight(r) for r in range(t.rowCount()))
        frame = 2 * t.frameWidth()
        total = header_h + rows_h + frame + 2
        t.setMinimumHeight(total)
        t.setMaximumHeight(total)

    def _shorten(self, label):
        label = str(label or "(blank)")
        return label if len(label) <= 20 else label[:17] + "..."

    def _style_chart(self, chart):
        pal = getattr(self, "_chart_pal", None) or style.chart_palette("light")
        chart.setBackgroundBrush(QBrush(pal["bg"]))
        chart.setBackgroundRoundness(16)
        chart.setPlotAreaBackgroundBrush(QBrush(QColor(255, 255, 255, 0)))
        chart.setTitleBrush(QBrush(pal["title"]))
        chart.legend().setLabelColor(pal["label"])
        title_font = QFont()
        title_font.setPointSize(11)
        title_font.setBold(True)
        chart.setTitleFont(title_font)

    def _style_axis(self, axis):
        pal = getattr(self, "_chart_pal", None) or style.chart_palette("light")
        axis.setLabelsColor(pal["label"])
        axis.setTitleBrush(QBrush(pal["label"]))
        try:
            axis.setGridLineColor(pal["grid"])
        except AttributeError:
            pass

    def _render_bar(self, view, rows, title, color_cycle=True):
        top = rows[:15]
        bar_set = QBarSet("Total Amount")
        categories = []
        for row in top:
            bar_set.append(row["total"] or 0)
            categories.append(self._shorten(row["label"]))

        series = QBarSeries()
        series.append(bar_set)

        chart = QChart()
        chart.addSeries(series)
        chart.setTitle(title)
        chart.legend().hide()
        self._style_chart(chart)

        pal = getattr(self, "_chart_pal", None) or style.chart_palette("light")
        bar_set.setColor(pal["bar"])
        bar_set.setBorderColor(pal["bar"])

        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        axis_x.setLabelsAngle(-45)
        chart.addAxis(axis_x, Qt.AlignBottom)
        series.attachAxis(axis_x)
        self._style_axis(axis_x)

        axis_y = QValueAxis()
        max_val = max([row["total"] or 0 for row in top], default=0)
        axis_y.setRange(0, max_val * 1.1 if max_val else 1)
        axis_y.setLabelFormat("%'.0f")
        chart.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_y)
        self._style_axis(axis_y)

        view.setChart(chart)
