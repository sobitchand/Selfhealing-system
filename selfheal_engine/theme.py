"""
Presentation layer for the dashboard: typography, palette, and the small HTML
components Streamlit doesn't give us in a usable form.

The typeface is Libertinus Serif -- the maintained fork of Linux Libertine, same
design, metric-compatible. The four weights live in assets/ and are inlined as
base64 data URIs rather than pulled from a CDN, so the dashboard renders
identically on a machine with no network (which is the situation you want during
a defence, not the one you want to discover during it).
"""

import base64
import functools
import html
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

# --- palette ---------------------------------------------------------------
INK = "#16181d"
MUTED = "#6b7280"
RULE = "#e6e8eb"
PAGE = "#ffffff"
PANEL = "#fbfbfc"
GREEN = "#17693f"
AMBER = "#a35d00"
RED = "#a3231f"

STATUS_COLORS = {"success": GREEN, "warning": AMBER, "failed": RED}

# Libertine renders beautifully but is not installed on most machines; the local
# webfont covers that, and the system serifs are ordered by how close they sit
# to Libertine's proportions.
FONT_STACK = (
    "'Linux Libertine', 'Linux Libertine O', 'Libertinus Serif', "
    "Constantia, Cambria, Georgia, 'Times New Roman', serif"
)

_FONT_FILES = [
    ("libertinus-serif-latin-400-normal.woff2", 400, "normal"),
    ("libertinus-serif-latin-400-italic.woff2", 400, "italic"),
    ("libertinus-serif-latin-600-normal.woff2", 600, "normal"),
    ("libertinus-serif-latin-700-normal.woff2", 700, "normal"),
]


@functools.lru_cache(maxsize=1)
def _font_faces():
    """@font-face rules with the woff2 payloads inlined. Missing files are
    skipped -- the stack falls through to Constantia/Cambria/Georgia."""
    faces = []
    for filename, weight, style in _FONT_FILES:
        path = os.path.join(ASSETS_DIR, filename)
        try:
            with open(path, "rb") as f:
                payload = base64.b64encode(f.read()).decode("ascii")
        except OSError:
            continue
        faces.append(
            "@font-face{font-family:'Libertinus Serif';font-style:%s;"
            "font-weight:%d;font-display:swap;"
            "src:url(data:font/woff2;base64,%s) format('woff2');}"
            % (style, weight, payload)
        )
    return "\n".join(faces)


def stylesheet():
    """The whole visual identity, as one <style> block."""
    return f"""
<style>
{_font_faces()}

html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"],
button, input, textarea, select {{
    font-family: {FONT_STACK} !important;
}}

[data-testid="stAppViewContainer"] {{ background: {PAGE}; }}
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stMainBlockContainer"] {{
    max-width: 1180px;
    padding: 2.4rem 2rem 4rem;
}}

/* ---- masthead ---- */
.masthead {{
    border-bottom: 1px solid {RULE};
    padding-bottom: 1.1rem;
    margin-bottom: 1.9rem;
}}
.masthead h1 {{
    font-size: 2.35rem;
    font-weight: 600;
    letter-spacing: -0.012em;
    color: {INK};
    margin: 0 0 .35rem;
    line-height: 1.15;
}}
.masthead p {{
    font-size: 1.02rem;
    color: {MUTED};
    margin: 0;
    max-width: 62ch;
    line-height: 1.5;
}}

/* ---- section headings ---- */
.section-title {{
    font-size: 1.28rem;
    font-weight: 600;
    color: {INK};
    margin: 2.1rem 0 .3rem;
    letter-spacing: -0.006em;
}}
.section-note {{
    font-size: .94rem;
    color: {MUTED};
    margin: 0 0 1.15rem;
    max-width: 68ch;
    line-height: 1.5;
}}

/* ---- statistic row ---- */
.stat-row {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 0;
    border: 1px solid {RULE};
    border-radius: 6px;
    overflow: hidden;
    background: {PANEL};
    margin-bottom: 1.6rem;
}}
.stat {{
    padding: 1.05rem 1.25rem;
    border-right: 1px solid {RULE};
}}
.stat:last-child {{ border-right: none; }}
.stat .label {{
    display: block;
    font-size: .78rem;
    letter-spacing: .07em;
    text-transform: uppercase;
    color: {MUTED};
    margin-bottom: .34rem;
}}
.stat .value {{
    display: block;
    font-size: 1.95rem;
    font-weight: 600;
    color: {INK};
    font-variant-numeric: tabular-nums;
    line-height: 1.1;
}}

/* ---- tables ---- */
.tbl-wrap {{
    border: 1px solid {RULE};
    border-radius: 6px;
    overflow-x: auto;
    margin-bottom: .6rem;
}}
table.tbl {{
    width: 100%;
    border-collapse: collapse;
    font-size: .93rem;
}}
table.tbl thead th {{
    text-align: left;
    font-weight: 600;
    font-size: .78rem;
    letter-spacing: .06em;
    text-transform: uppercase;
    color: {MUTED};
    background: {PANEL};
    padding: .68rem .9rem;
    border-bottom: 1px solid {RULE};
    white-space: nowrap;
}}
table.tbl tbody td {{
    padding: .62rem .9rem;
    border-bottom: 1px solid #f1f2f4;
    color: {INK};
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
}}
table.tbl tbody tr:last-child td {{ border-bottom: none; }}
table.tbl tbody tr:hover td {{ background: #fafbfc; }}
table.tbl td.num {{ text-align: right; }}
table.tbl td.mono {{
    font-family: 'SF Mono', 'Cascadia Mono', Consolas, monospace;
    font-size: .86rem;
}}
.tbl-note {{
    font-size: .85rem;
    color: {MUTED};
    margin: 0 0 1.7rem;
}}

/* ---- pills ---- */
.pill {{
    display: inline-block;
    padding: .12rem .55rem;
    border-radius: 999px;
    font-size: .78rem;
    font-weight: 600;
    letter-spacing: .02em;
    border: 1px solid currentColor;
}}
.pill-success {{ color: {GREEN}; }}
.pill-warning {{ color: {AMBER}; }}
.pill-failed  {{ color: {RED}; }}

/* ---- alerts ---- */
.alert {{
    border: 1px solid {RULE};
    border-left: 3px solid {MUTED};
    border-radius: 5px;
    padding: .85rem 1.05rem;
    margin-bottom: .7rem;
    background: {PANEL};
}}
.alert.critical {{ border-left-color: {RED}; }}
.alert.warning  {{ border-left-color: {AMBER}; }}
.alert .meta {{
    font-size: .78rem;
    letter-spacing: .05em;
    text-transform: uppercase;
    color: {MUTED};
    margin-bottom: .3rem;
}}
.alert .body {{ color: {INK}; font-size: .95rem; line-height: 1.5; }}

/* ---- empty state ---- */
.empty {{
    border: 1px dashed {RULE};
    border-radius: 6px;
    padding: 2.1rem 1.5rem;
    text-align: center;
    color: {MUTED};
    font-size: .96rem;
    background: {PANEL};
}}

/* ---- tabs ---- */
.stTabs [data-baseweb="tab-list"] {{
    gap: 1.9rem;
    border-bottom: 1px solid {RULE};
}}
.stTabs [data-baseweb="tab"] {{
    background: transparent;
    padding: .55rem 0;
    font-size: 1rem;
    color: {MUTED};
}}
.stTabs [aria-selected="true"] {{ color: {INK} !important; font-weight: 600; }}
.stTabs [data-baseweb="tab-highlight"] {{ background: {INK}; }}
.stTabs [data-baseweb="tab-border"] {{ display: none; }}

/* ---- sidebar ---- */
[data-testid="stSidebar"] {{
    background: {PANEL};
    border-right: 1px solid {RULE};
    min-width: 300px;
    width: 300px !important;
}}
[data-testid="stSidebarContent"] {{
    padding: 1.5rem 1rem;
}}
[data-testid="stSidebar"] .sb-title {{
    font-size: .8rem;
    letter-spacing: .09em;
    text-transform: uppercase;
    color: {MUTED};
    margin: .2rem 0 1rem;
}}
.sb-item {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    padding: .5rem 0;
    border-bottom: 1px solid {RULE};
}}
.sb-item:last-child {{ border-bottom: none; }}
.sb-item .k {{ font-size: .92rem; color: {MUTED}; }}
.sb-item .v {{
    font-size: 1.02rem;
    font-weight: 600;
    color: {INK};
    font-variant-numeric: tabular-nums;
}}
.sb-status {{
    display: block;
    padding: .6rem .75rem;
    border-radius: 5px;
    font-weight: 600;
    font-size: .95rem;
    text-align: center;
    margin-bottom: 1.1rem;
    border: 1px solid currentColor;
}}
.sb-up   {{ color: {GREEN}; }}
.sb-down {{ color: {RED}; }}

/* ---- Streamlit chrome ----
   The status widget is a running-man animation that fires on every rerun. With
   a 3s auto-refresh it is on screen almost permanently, which reads as "the
   page is stuck loading" rather than "the data is live". Hidden, along with the
   rest of the framework furniture, so the page looks like a site and not like a
   Streamlit app. */
[data-testid="stStatusWidget"],
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stToolbarActions"],
.stDeployButton,
#MainMenu,
footer {{
    display: none !important;
    visibility: hidden !important;
}}

/* ---- config action cards ---- */
.config-actions {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
    margin: 1rem 0 1.5rem;
}}
</style>
"""


# --------------------------------------------------------------------------
# components
# --------------------------------------------------------------------------
def masthead(title, subtitle):
    return f'<div class="masthead"><h1>{html.escape(title)}</h1>' \
           f'<p>{html.escape(subtitle)}</p></div>'


def section(title, note=None):
    out = f'<div class="section-title">{html.escape(title)}</div>'
    if note:
        out += f'<p class="section-note">{html.escape(note)}</p>'
    return out


def stat_row(pairs):
    """pairs: [(label, value), ...]"""
    cells = "".join(
        f'<div class="stat"><span class="label">{html.escape(str(label))}</span>'
        f'<span class="value">{html.escape(str(value))}</span></div>'
        for label, value in pairs
    )
    return f'<div class="stat-row">{cells}</div>'


def pill(status):
    status = str(status or "").lower()
    cls = f"pill-{status}" if status in STATUS_COLORS else ""
    return f'<span class="pill {cls}">{html.escape(status.upper() or "-")}</span>'


def table(rows, columns, aligns=None):
    """rows: list of dicts. columns: [(key, header), ...].
    aligns: optional {key: 'num'|'mono'} for cell classes."""
    aligns = aligns or {}
    head = "".join(f"<th>{html.escape(h)}</th>" for _, h in columns)
    body = []
    for row in rows:
        cells = []
        for key, _ in columns:
            value = row.get(key, "")
            cls = aligns.get(key, "")
            cells.append(f'<td class="{cls}">{value}</td>')
        body.append("<tr>" + "".join(cells) + "</tr>")
    return (
        f'<div class="tbl-wrap"><table class="tbl">'
        f"<thead><tr>{head}</tr></thead>"
        f'<tbody>{"".join(body)}</tbody></table></div>'
    )


def table_note(shown, total, unit="rows"):
    if total <= shown:
        return f'<p class="tbl-note">{total} {unit}.</p>'
    return f'<p class="tbl-note">Showing the {shown} most recent of {total} {unit}.</p>'


def alert(timestamp, source, severity, message):
    sev = str(severity or "warning").lower()
    cls = "critical" if sev == "critical" else "warning"
    return (
        f'<div class="alert {cls}">'
        f'<div class="meta">{html.escape(str(timestamp))} &middot; '
        f'{html.escape(str(source))} &middot; {html.escape(sev)}</div>'
        f'<div class="body">{html.escape(str(message))}</div></div>'
    )


def empty(message):
    return f'<div class="empty">{html.escape(message)}</div>'


def sidebar_status(is_up):
    label = "Application up" if is_up else "Application down"
    cls = "sb-up" if is_up else "sb-down"
    return f'<span class="sb-status {cls}">{label}</span>'


def sidebar_item(key, value):
    return (f'<div class="sb-item"><span class="k">{html.escape(key)}</span>'
            f'<span class="v">{html.escape(str(value))}</span></div>')
