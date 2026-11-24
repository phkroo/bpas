"""Small layout helpers shared by screens."""


def arrange_filter_row(top_row, combo_row, search, combos, apply_btn, clear_btn, narrow: bool):
    """Records / Consolidation filters: ONE line when the window is wide
    (search, the four dropdowns, Search, Clear Filters); two lines when it is narrow
    (search + buttons on top, dropdowns below) so the window can still shrink to half a screen."""
    for lay in (top_row, combo_row):
        while lay.count():
            lay.takeAt(0)
    if narrow:
        top_row.addWidget(search, 1)
        top_row.addWidget(apply_btn)
        top_row.addWidget(clear_btn)
        for c in combos:
            combo_row.addWidget(c, 1)
    else:
        top_row.addWidget(search, 3)
        for c, stretch in zip(combos, (2, 2, 2, 3)):     # the Procurement Modes label is the longest
            # size by the share of free width, not by the longest list entry
            c.setSizeAdjustPolicy(c.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            c.setMinimumContentsLength(8)
            top_row.addWidget(c, stretch)
        top_row.addWidget(apply_btn)
        top_row.addWidget(clear_btn)


def arrange_bottom_bar(info_row, button_row, info_widgets, buttons, narrow: bool):
    """Records bottom bar: totals on the left and buttons on the right of ONE line when wide;
    totals on one line and the buttons on the line below when narrow."""
    for lay in (info_row, button_row):
        while lay.count():
            lay.takeAt(0)
    for w in info_widgets:
        info_row.addWidget(w)
    info_row.addStretch()
    target = button_row if narrow else info_row
    if narrow:
        button_row.addStretch()
    for b in buttons:
        target.addWidget(b)
