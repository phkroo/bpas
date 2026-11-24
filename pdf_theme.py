"""Table colours for the PPMP / SOB / APP PDFs, taken from the app's teal theme
(ui/style.py light palette) so a printed page looks like the screen."""

HEADER_BG = "#0d7490"      # column headers: the app's teal accent (the chart-bar colour)
HEADER_FG = "#000000"      # header text: black
NOTE_FG = "#0a556a"        # small notes: the app's heading teal
BORDER = "#444"            # outside table border colour (drawn thick)
SECTION_BG = "#eef3f2"     # group / section rows: the app's table-header grey-teal
MONTH_SHADE = "#a9cfda"    # PPMP month cells: teal tint

HEADER_STYLE = f"background:{HEADER_BG}; color:{HEADER_FG}"

TITLE_PT = 14      # page title, bold
BODY_PT = 12       # info lines, table, totals, notes, signatures
