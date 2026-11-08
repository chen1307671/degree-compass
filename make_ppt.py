"""Degree Compass - deck builder (editorial layout, not a generic template)

Build/verify script for the Degree Compass deliverable. See README for usage."""
from __future__ import annotations
import pathlib
from PIL import Image
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn

from src.slides_data import SLIDES

HERE = pathlib.Path(__file__).resolve().parent
CHARTS = HERE / "assets" / "charts"
OUT = HERE / "slides" / "学位罗盘_答辩演示.pptx"

# -- editorial palette (consistent with the charts) --
INK = RGBColor(0x13, 0x29, 0x4B)
INK2 = RGBColor(0x27, 0x49, 0x6E)
TERRA = RGBColor(0xC2, 0x54, 0x2F)
TEAL = RGBColor(0x0E, 0x7C, 0x6B)
GOLD = RGBColor(0xB0, 0x8D, 0x3C)
SLATE = RGBColor(0x4A, 0x55, 0x68)
MUTE = RGBColor(0x9A, 0xA3, 0xB2)
HAIR = RGBColor(0xC7, 0xBC, 0xA9)
HDIV = RGBColor(0xB9, 0xAC, 0x95)   # 暖灰发丝线（浅底上更清晰）
PAPER = RGBColor(0xFB, 0xF9, 0xF4)
PANEL = RGBColor(0xEF, 0xEA, 0xDD)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
LIGHTINK = RGBColor(0xCF, 0xD8, 0xE4)   # 深底上的浅字
FONT = "Microsoft YaHei"
LATIN = "Times New Roman"
EMU_W, EMU_H = Inches(13.333), Inches(7.5)
ML, MR = Inches(0.6), Inches(0.6)
CW = EMU_W - ML - MR                     # 内容宽
AUTHOR = "学位罗盘 Compass"

# Main chart per page (None if absent); narrow vs full-width chosen by aspect ratio
CHART_FOR = {}
_UNUSED = {
    4: ("target_distribution.png", None),
    5: ("pipeline_flow.png", None),
    # page 6 = knowledge-base page (cards + text, no chart)
    7: ("mindmap.png", None),
    8: ("auc_ci.png", None),
    9: ("ablation.png", None),
    10: ("cf_example.png", None),
    11: ("policy_labels.png", None),
    12: ("cohort_example.png", None),
    13: ("agent_loop.png", None),
    14: ("agent_baselines.png", None),
    15: ("prompts_cf.png", None),
    16: ("ui_real.png", None),
}


# ---------- primitives ----------
def _bg(slide, color):
    slide.background.fill.solid(); slide.background.fill.fore_color.rgb = color


def _txt(slide, l, t, w, h, anchor=MSO_ANCHOR.TOP, align=PP_ALIGN.LEFT):
    tb = slide.shapes.add_textbox(l, t, w, h)
    tf = tb.text_frame; tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    return tb, tf


def _para(tf, text, size, color, bold=False, first=False, space_after=6,
          align=PP_ALIGN.LEFT, font=FONT, italic=False, tracking=None):
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    p.alignment = align; p.space_after = Pt(space_after); p.space_before = Pt(0)
    if tracking:
        p.line_spacing = None
    r = p.add_run(); r.text = text
    r.font.size = Pt(size); r.font.bold = bold; r.font.italic = italic
    r.font.color.rgb = color; r.font.name = LATIN
    rpr = r._r.get_or_add_rPr(); rpr.append(rpr.makeelement(qn('a:ea'), {'typeface': font}))
    return p


def _rect(slide, l, t, w, h, fill, line=None, line_w=None, rounded=False):
    shp = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE, l, t, w, h)
    shp.shadow.inherit = False
    if fill is None: shp.fill.background()
    else: shp.fill.solid(); shp.fill.fore_color.rgb = fill
    if line is None: shp.line.fill.background()
    else: shp.line.color.rgb = line; shp.line.width = Pt(line_w or 1)
    return shp


def _hairline(slide, y, color=HAIR, x=ML, w=CW, thick=0.75):
    _rect(slide, x, y, w, Pt(thick), color)


def _bg_color(s, dark):
    return PAPER if not dark else INK


def _kicker(slide, s, dark):
    c = GOLD if dark else TERRA
    y = Inches(0.46)
    # thin rule plus letter-spaced plain-text kicker (no pill)
    _rect(slide, ML, y, Inches(0.05), Inches(0.26), c)
    tb, tf = _txt(slide, ML + Inches(0.14), y - Inches(0.02), Inches(9), Inches(0.32),
                  anchor=MSO_ANCHOR.MIDDLE)
    _para(tf, s["kicker"].upper(), 11, c, bold=True, first=True,
          space_after=0, font=FONT)
    # apply letter spacing
    p = tf.paragraphs[0]
    pPr = p._pPr if p._pPr is not None else p.get_or_add_pPr()
    pPr.set('algn', 'l')


def _title(slide, s, dark):
    tcol = WHITE if dark else INK
    scol = LIGHTINK if dark else SLATE
    tb, tf = _txt(slide, ML, Inches(0.84), CW, Inches(0.8), anchor=MSO_ANCHOR.MIDDLE)
    _para(tf, s["title"], 27, tcol, bold=True, first=True, space_after=0)
    if s.get("subtitle"):
        tb, tf = _txt(slide, ML, Inches(1.62), CW, Inches(0.5))
        _para(tf, s["subtitle"], 13.5, scol, first=True, space_after=0)


def _watermark(slide, s, dark=False):
    """Very light oversized page number in the lower-left corner."""
    col = RGBColor(0xE7, 0xDF, 0xD0) if not dark else RGBColor(0x1E, 0x38, 0x56)
    tb = slide.shapes.add_textbox(ML, Inches(4.7), Inches(3.4), Inches(2.4))
    tf = tb.text_frame; tf.word_wrap = False
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.LEFT
    r = p.add_run(); r.text = f"{s['no']:02d}"
    r.font.size = Pt(120); r.font.bold = True; r.font.color.rgb = col; r.font.name = LATIN
    rpr = r._r.get_or_add_rPr(); rpr.append(rpr.makeelement(qn('a:ea'), {'typeface': FONT}))


def _footer(slide, s, dark):
    _hairline(slide, Inches(7.02), HAIR if not dark else RGBColor(0x33,0x4B,0x6B))
    tb, tf = _txt(slide, ML, Inches(7.06), Inches(8), Inches(0.3), anchor=MSO_ANCHOR.MIDDLE)
    _para(tf, AUTHOR, 9, MUTE if not dark else RGBColor(0x7E,0x90,0xA8),
          first=True, space_after=0)
    tb, tf = _txt(slide, EMU_W - MR - Inches(1.2), Inches(7.06), Inches(1.2), Inches(0.3),
                  anchor=MSO_ANCHOR.MIDDLE, align=PP_ALIGN.RIGHT)
    _para(tf, f"{s['no']:02d} / 20", 9, MUTE if not dark else RGBColor(0x7E,0x90,0xA8),
          first=True, align=PP_ALIGN.RIGHT, space_after=0)


def _bullets(slide, l, t, w, h, items, size=13.5, gap=11, color=None, dark=False):
    col = (LIGHTINK if dark else SLATE) if color is None else color
    tb, tf = _txt(slide, l, t, w, h)
    for i, b in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT; p.space_after = Pt(gap)
        rb = p.add_run(); rb.text = "—  " + b
        rb.font.size = Pt(size); rb.font.color.rgb = col; rb.font.name = LATIN
        rbpr = rb._r.get_or_add_rPr(); rbpr.append(rbpr.makeelement(qn('a:ea'), {'typeface': FONT}))
    return tb


def _hero(slide, l, t, w, h, value, label, dark=False, size=34, align=PP_ALIGN.LEFT):
    """Large numeric anchor: thin rule above, big number, label."""
    if align == PP_ALIGN.LEFT:
        _rect(slide, l, t, Inches(0.5), Pt(2.2), TERRA)
    tb, tf = _txt(slide, l, t + Inches(0.12), w, h - Inches(0.5), anchor=MSO_ANCHOR.MIDDLE, align=align)
    _para(tf, str(value), size, (WHITE if dark else TERRA), bold=True, first=True,
          space_after=4, align=align)
    _para(tf, label, 11.5, (LIGHTINK if dark else SLATE), first=False, align=align, space_after=0)


def _cards(slide, l, t, w, h, cards, cols=2, dark=False):
    n = len(cards); gap = Inches(0.18)
    cw = (w - gap * (cols - 1)) / cols
    ch = (h - gap * (max(1, (n + cols - 1) // cols) - 1)) / max(1, (n + cols - 1) // cols)
    for i, card in enumerate(cards):
        r, c = divmod(i, cols)
        x = l + c * (cw + gap); y = t + r * (ch + gap)
        fill = (INK2 if dark else PANEL)
        _rect(slide, x, y, cw, ch, fill, rounded=True)
        tb, tf = _txt(slide, x + Inches(0.14), y + Inches(0.1), cw - Inches(0.28), ch - Inches(0.2),
                      anchor=MSO_ANCHOR.MIDDLE)
        _para(tf, str(card[0]), 15, (WHITE if dark else TERRA), bold=True, first=True, space_after=3)
        _para(tf, str(card[1]), 10.5, (LIGHTINK if dark else SLATE), first=False)


def _table(slide, l, t, w, headers, rows, col_w=None, dark=False):
    nrows = len(rows) + 1
    th = Inches(0.4 * nrows) + Inches(0.1)
    gt = slide.shapes.add_table(nrows, len(headers), l, t, w, th)
    tbl = gt.table; tbl.first_row = False; tbl.horz_banding = False
    if col_w:
        total = sum(col_w)
        for j, cw in enumerate(col_w):
            tbl.columns[j].width = Emu(int(w * cw / total))
    for j, htext in enumerate(headers):
        c = tbl.cell(0, j); c.fill.solid(); c.fill.fore_color.rgb = (INK if not dark else INK2)
        c.margin_left = Inches(0.1); c.margin_right = Inches(0.08)
        c.margin_top = Inches(0.04); c.margin_bottom = Inches(0.04)
        c.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = c.text_frame.paragraphs[0]; p.alignment = PP_ALIGN.LEFT
        r = p.add_run(); r.text = str(htext); r.font.size = Pt(10.5)
        r.font.bold = True; r.font.color.rgb = WHITE; r.font.name = LATIN
        rpr = r._r.get_or_add_rPr(); rpr.append(rpr.makeelement(qn('a:ea'), {'typeface': FONT}))
    for i, row in enumerate(rows, start=1):
        for j, val in enumerate(row):
            c = tbl.cell(i, j); c.fill.solid()
            c.fill.fore_color.rgb = (WHITE if not dark else RGBColor(0x1C,0x35,0x54))
            c.margin_left = Inches(0.1); c.margin_right = Inches(0.08)
            c.margin_top = Inches(0.03); c.margin_bottom = Inches(0.03)
            c.vertical_anchor = MSO_ANCHOR.MIDDLE
            p = c.text_frame.paragraphs[0]; p.alignment = PP_ALIGN.LEFT
            r = p.add_run(); r.text = str(val); r.font.size = Pt(10)
            r.font.color.rgb = (INK if not dark else LIGHTINK); r.font.name = LATIN
            rpr = r._r.get_or_add_rPr(); rpr.append(rpr.makeelement(qn('a:ea'), {'typeface': FONT}))
    for i in range(nrows):
        for j in range(len(headers)):
            _set_cell_border(tbl.cell(i, j), HAIR if not dark else RGBColor(0x33,0x4B,0x6B))
    return gt, th


def _set_cell_border(cell, line_rgb):
    lh = "%02X%02X%02X" % (line_rgb[0], line_rgb[1], line_rgb[2])
    tc = cell._tc
    tcPr = tc.find(qn('a:tcPr'))
    if tcPr is None:
        tcPr = tc.makeelement(qn('a:tcPr'), {}); tc.insert(0, tcPr)
    for edge in ('lnL', 'lnR', 'lnT', 'lnB'):
        el = tcPr.makeelement(qn('a:' + edge), {'w': '6350', 'cap': 'flat'})
        fill = el.makeelement(qn('a:solidFill'), {})
        clr = fill.makeelement(qn('a:srgbClr'), {'val': lh}); fill.append(clr)
        el.append(fill); tcPr.append(el)


def _aspect(name):
    p = CHARTS / name
    if not p.exists():
        return 1.0
    w, h = Image.open(p).size
    return w / h


def _fit_picture(slide, name, box):
    p = CHARTS / name
    if not p.exists():
        return
    img = Image.open(p); iw, ih = img.size
    x, y, bw, bh = box
    scale = min(bw / iw, bh / ih)
    w = int(iw * scale); h = int(ih * scale)
    left = x + (bw - w) // 2; top = y + (bh - h) // 2
    slide.shapes.add_picture(str(p), left, top, width=w, height=h)


# ---------- layout: cover / dark statement ----------
def _cover(slide, s, dark):
    _bg(slide, INK)
    # kicker
    tb, tf = _txt(slide, ML, Inches(0.72), CW, Inches(0.4), anchor=MSO_ANCHOR.MIDDLE)
    _para(tf, "第二届全国人工智能应用创新大赛 · 教育领域", 12.5, GOLD, bold=True, first=True, space_after=0)
    # title
    tb, tf = _txt(slide, ML, Inches(1.35), Inches(11.8), Inches(1.3), anchor=MSO_ANCHOR.MIDDLE)
    _para(tf, s["title"], 44, WHITE, bold=True, first=True, space_after=6)
    tb, tf = _txt(slide, ML, Inches(2.72), Inches(11.8), Inches(0.6))
    _para(tf, s.get("subtitle", ""), 17, LIGHTINK, first=True, space_after=0)
    # one-line claim
    tb, tf = _txt(slide, ML, Inches(3.5), Inches(11.6), Inches(0.9))
    _para(tf, (s.get("bullets") or [""])[0], 13, LIGHTINK, first=True, space_after=0)
    # divider (thin ochre rule as the anchor)
    _hairline(slide, Inches(4.55), TERRA, x=ML, w=Inches(3.2), thick=2.0)
    # three large numeric anchors at the bottom
    stats = s.get("cards") or ([s["hero"]] if s.get("hero") else [])
    if stats:
        base_y = Inches(5.05); seg = CW / len(stats)
        for i, card in enumerate(stats):
            x = ML + seg * i
            if i > 0:
                _rect(slide, x, base_y, Pt(0.9), Inches(1.1), RGBColor(0x33,0x4B,0x6B))
            tb, tf = _txt(slide, x + (Inches(0.28) if i > 0 else 0), base_y, seg - Inches(0.4), Inches(1.1),
                          anchor=MSO_ANCHOR.MIDDLE)
            _para(tf, str(card[0]), 32, TERRA, bold=True, first=True, space_after=3, align=PP_ALIGN.LEFT)
            _para(tf, card[1], 11, LIGHTINK, first=False, align=PP_ALIGN.LEFT, space_after=0)
    _footer(slide, s, dark=True)


def _dark_statement(slide, s):
    _bg(slide, INK)
    _kicker(slide, s, dark=True)
    _title(slide, s, dark=True)
    _hairline(slide, Inches(1.78), RGBColor(0x33,0x4B,0x6B))
    # two panels: in scope / out of scope
    cards = s.get("cards", [])
    if cards:
        lx = ML; rx = ML + CW / 2 + Inches(0.2)
        pw = CW / 2 - Inches(0.1)
        y = Inches(2.05); ph = Inches(3.15)
        for x, card, accent in ((lx, cards[0], TEAL), (rx, cards[1], TERRA)):
            _rect(slide, x, y, pw, ph, RGBColor(0x2B,0x4E,0x78), line=accent, line_w=1.25, rounded=True)
            _rect(slide, x, y, Inches(0.1), ph, accent)
            tb, tf = _txt(slide, x + Inches(0.32), y + Inches(0.28), pw - Inches(0.55), Inches(0.5),
                          anchor=MSO_ANCHOR.MIDDLE)
            _para(tf, card[0], 17, accent, bold=True, first=True, space_after=7)
            tb, tf = _txt(slide, x + Inches(0.32), y + Inches(1.05), pw - Inches(0.55), ph - Inches(1.2))
            for i, it in enumerate(card[1].split(" · ")):
                p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
                p.space_after = Pt(9)
                r = p.add_run(); r.text = "· " + it
                r.font.size = Pt(13); r.font.color.rgb = LIGHTINK; r.font.name = LATIN
                rpr = r._r.get_or_add_rPr(); rpr.append(rpr.makeelement(qn('a:ea'), {'typeface': FONT}))
    if s.get("bullets"):
        _bullets(slide, ML, Inches(5.45), CW, Inches(1.2), s["bullets"], size=12.5, gap=8, dark=True)
    if s.get("footnote"):
        tb, tf = _txt(slide, ML, Inches(6.78), CW, Inches(0.3))
        _para(tf, s["footnote"], 10, RGBColor(0x9F,0xB0,0xC6), italic=True, first=True, space_after=0)
    _footer(slide, s, dark=True)


# ---------- layout: full-width chart ----------
def _wide(slide, s, chart):
    dark = False
    _bg(slide, PAPER)
    _kicker(slide, s, dark)
    _title(slide, s, dark)
    _hairline(slide, Inches(1.78), HDIV)
    y0 = Inches(1.98)
    # interface page: chart is the hero, one line on top, chart fills the lower half
    if s.get("ui_seq"):
        if s.get("bullets"):
            _bullets(slide, ML, y0, Inches(9.5), Inches(1.2), s["bullets"], size=13, gap=8)
        _fit_picture(slide, chart, (ML, Inches(3.35), CW, Inches(6.34) - Inches(3.35)))
        if s.get("footnote"):
            tb, tf = _txt(slide, ML, Inches(6.5), CW, Inches(0.4))
            _para(tf, s["footnote"], 9.5, MUTE, italic=True, first=True, space_after=0)
        _footer(slide, s, dark)
        return
    # top: table or text
    if s.get("table"):
        _, th = _table(slide, ML, y0, CW, s["table"]["headers"], s["table"]["rows"])
        yc = y0 + th + Inches(0.22)
    else:
        if s.get("hero") and s.get("bullets"):
            _hero(slide, ML, y0, Inches(4.2), Inches(1.5), s["hero"][0], s["hero"][1])
            _bullets(slide, ML + Inches(4.6), y0, CW - Inches(4.6), Inches(1.6),
                     s["bullets"], size=12.5, gap=8)
        elif s.get("bullets"):
            _bullets(slide, ML, y0, CW * 0.62, Inches(1.5), s["bullets"], size=13, gap=9)
        yc = y0 + Inches(1.85)
    _fit_picture(slide, chart, (ML, yc, CW, (Inches(6.34) if s.get("footnote") else Inches(6.85)) - yc))
    if s.get("footnote"):
        tb, tf = _txt(slide, ML, Inches(6.5), CW, Inches(0.4))
        _para(tf, s["footnote"], 9.5, MUTE, italic=True, first=True, space_after=0)
    _footer(slide, s, dark)


# ---------- layout: two columns (narrow chart) ----------
def _column(slide, s, chart, chart2):
    dark = False
    _bg(slide, PAPER)
    _kicker(slide, s, dark)
    _title(slide, s, dark)
    _hairline(slide, Inches(1.78), HDIV)
    y0 = Inches(1.98)
    lx, lw = ML, Inches(6.35)
    rx = ML + lw + Inches(0.45)
    rw = EMU_W - MR - rx
    has_chart = chart is not None
    # table only: full-width table, vertically centred
    if s.get("table") and not has_chart and not s.get("bullets"):
        _, th = _table(slide, ML, Inches(2.5), CW, s["table"]["headers"], s["table"]["rows"], col_w=[1, 1.7])
        if s.get("footnote"):
            tb, tf = _txt(slide, ML, Inches(2.5) + th + Inches(0.2), CW, Inches(0.4))
            _para(tf, s["footnote"], 10, MUTE, italic=True, first=True, space_after=0)
        _footer(slide, s, dark)
        return
    # left column
    if s.get("table"):
        _, th = _table(slide, lx, y0, lw, s["table"]["headers"], s["table"]["rows"],
                       col_w=s["table"].get("col_w"))
        if s.get("bullets"):
            _bullets(slide, lx, y0 + th + Inches(0.22), lw, Inches(2.4),
                     s["bullets"], size=11.5, gap=7)
    elif s.get("cards"):
        # metric / limitation cards (earlier layouts never rendered them)
        if has_chart:
            _cards(slide, lx, y0, lw, Inches(1.9), s["cards"], cols=2)
            if s.get("bullets"):
                _bullets(slide, lx, y0 + Inches(2.06), lw, Inches(2.4),
                         s["bullets"], size=11.5, gap=6)
        else:
            _cards(slide, ML, y0, CW, Inches(1.5), s["cards"], cols=len(s["cards"]))
            if s.get("bullets"):
                _bullets(slide, ML, y0 + Inches(1.72), CW, Inches(2.6),
                         s["bullets"], size=13.5, gap=10)
    elif s.get("hero") and has_chart:
        _hero(slide, lx, y0, Inches(3.2), Inches(1.6), s["hero"][0], s["hero"][1])
        if s.get("bullets"):
            _bullets(slide, lx, y0 + Inches(1.8), lw, Inches(2.6), s["bullets"], size=13, gap=9)
    elif s.get("bullets"):
        _bullets(slide, lx, Inches(2.9), lw, Inches(4.2), s["bullets"], size=15, gap=15)
    # right column: chart or large number
    if has_chart:
        if chart2:
            _fit_picture(slide, chart, (rx, y0, rw, Inches(2.95)))
            _fit_picture(slide, chart2, (rx, y0 + Inches(3.1), rw, Inches(1.75)))
        else:
            _fit_picture(slide, chart, (rx, y0, rw, Inches(4.7)))
    elif s.get("hero"):
        # no-chart page: large number as the visual anchor, centred
        _hero(slide, rx, Inches(2.6), rw, Inches(4.0), s["hero"][0], s["hero"][1], size=42, align=PP_ALIGN.CENTER)
        if not s.get("table"):   # 有表格时左下有内容，水印会与脚注相撞
            _watermark(slide, s)
    if s.get("footnote"):
        tb, tf = _txt(slide, ML, Inches(6.5), CW, Inches(0.4))
        _para(tf, s["footnote"], 9.5, MUTE, italic=True, first=True, space_after=0)
    _footer(slide, s, dark)


def build_slide(slide, s):
    no = s["no"]
    if s.get("cover"):
        _cover(slide, s, True); return
    if s.get("dark"):
        _dark_statement(slide, s); return
    if s.get("layout") == "column":
        chart = CHARTS / f'{s["chart"]}.png' if s.get("chart") else None
        _column(slide, s, chart, None)
        return
    if s.get("chart"):
        # explicit chart on the slide wins over the page-number map
        chart, chart2 = CHARTS / f'{s["chart"]}.png', None
    else:
        # legacy map: page 13 was inserted later, so later pages shift by one
        _k = no if no <= 12 else no - 1
        chart, chart2 = CHART_FOR.get(_k, (None, None))
    if chart and _aspect(chart) >= 1.7:
        _wide(slide, s, chart)
    else:
        _column(slide, s, chart, chart2)


def main():
    prs = Presentation(); prs.slide_width = EMU_W; prs.slide_height = EMU_H
    blank = prs.slide_layouts[6]
    for s in SLIDES:
        build_slide(prs.slides.add_slide(blank), s)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(OUT))
    n_pic = sum(1 for sl in prs.slides for sh in sl.shapes if sh.shape_type == 13)
    print(f"[ppt] saved {OUT}  ({len(SLIDES)} slides, {OUT.stat().st_size:,} bytes, charts={n_pic})")


if __name__ == "__main__":
    main()
