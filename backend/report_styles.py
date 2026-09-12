"""
backend/report_styles.py

Professional ReportLab Styling Architecture for NiriKsha Statutory Reports.
Follows Government of India / Department of Consumer Affairs (DoCA) visual guidelines.
Implements dynamic two-pass NumberedCanvas for exact 'Page X of Y' total page calculation,
running headers, running footers, and institutional navy theme tokens.
"""

import os
from pathlib import Path
from typing import Optional
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.lib.styles import getSampleStyleSheet, StyleSheet1, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping

# ─────────────────────────────────────────────────────────────────────────────
# UNICODE / INDIC FONT REGISTRATION (PCR STATUTORY STANDARDS & DEVANAGARI SUPPORT)
# ─────────────────────────────────────────────────────────────────────────────
REPORT_FONT_REGULAR = "Helvetica"
REPORT_FONT_BOLD = "Helvetica-Bold"
REPORT_FONT_OBLIQUE = "Helvetica-Oblique"

def _init_reportlab_unicode_fonts():
    global REPORT_FONT_REGULAR, REPORT_FONT_BOLD, REPORT_FONT_OBLIQUE
    candidate_ttc_paths = [
        Path("backend/assets/fonts/Nirmala.ttc"),
        Path("../backend/assets/fonts/Nirmala.ttc"),
        Path("C:/Windows/Fonts/Nirmala.ttc"),
    ]
    for cp in candidate_ttc_paths:
        if cp.exists():
            try:
                pdfmetrics.registerFont(TTFont("NirmalaUI", str(cp), subfontIndex=0))
                pdfmetrics.registerFont(TTFont("NirmalaUI-Bold", str(cp), subfontIndex=1))
                addMapping("NirmalaUI", 0, 0, "NirmalaUI")
                addMapping("NirmalaUI", 1, 0, "NirmalaUI-Bold")
                REPORT_FONT_REGULAR = "NirmalaUI"
                REPORT_FONT_BOLD = "NirmalaUI-Bold"
                REPORT_FONT_OBLIQUE = "NirmalaUI"
                return
            except Exception:
                pass

_init_reportlab_unicode_fonts()

# ─────────────────────────────────────────────────────────────────────────────
# PAGE GEOMETRY & LAYOUT CONSTANTS (A4 PORTRAIT)
# ─────────────────────────────────────────────────────────────────────────────
PAGE_WIDTH, PAGE_HEIGHT = A4  # 595.27 pt x 841.89 pt
MARGIN_LEFT = 36.0           # 0.5 inch
MARGIN_RIGHT = 36.0          # 0.5 inch
MARGIN_TOP = 40.0            # Printable content starts below header
MARGIN_BOTTOM = 46.0         # Printable content ends above footer
PRINTABLE_WIDTH = PAGE_WIDTH - MARGIN_LEFT - MARGIN_RIGHT  # 523.27 pt

# ─────────────────────────────────────────────────────────────────────────────
# CURATED NIRIKSHA PALETTE (NAVY / SLATE INSTITUTIONAL THEME)
# ─────────────────────────────────────────────────────────────────────────────
COLOR_PRIMARY_NAVY = colors.HexColor("#0A192F")       # Deep authoritative navy
COLOR_SECONDARY_BLUE = colors.HexColor("#1E3A8A")     # Royal institutional blue
COLOR_ACCENT_BLUE = colors.HexColor("#0284C7")        # Cyan-blue highlight
COLOR_TEXT_DARK = colors.HexColor("#0F172A")          # Near-black slate for readability
COLOR_TEXT_MUTED = colors.HexColor("#475569")         # Muted description slate
COLOR_BG_LIGHT = colors.HexColor("#F8FAFC")           # Very light card fill
COLOR_BG_CARD = colors.HexColor("#F1F5F9")            # Subtle table/card fill
COLOR_BORDER = colors.HexColor("#CBD5E1")             # Light crisp divider
COLOR_BORDER_DARK = colors.HexColor("#94A3B8")        # Stronger accent border

# Compliance Status Badges / Highlights
COLOR_PASS_GREEN = colors.HexColor("#15803D")         # Forest green (Compliant)
COLOR_PASS_BG = colors.HexColor("#DCFCE7")            # Soft green tint
COLOR_FAIL_RED = colors.HexColor("#B91C1C")           # Crimson red (Potential Non-Compliance)
COLOR_FAIL_BG = colors.HexColor("#FEE2E2")            # Soft red tint
COLOR_WARN_AMBER = colors.HexColor("#B45309")         # Deep amber (Manual Verification / Warning)
COLOR_WARN_BG = colors.HexColor("#FEF3C7")            # Soft amber tint
COLOR_NEUTRAL_SLATE = colors.HexColor("#64748B")      # Neutral grey
COLOR_NEUTRAL_BG = colors.HexColor("#F1F5F9")

# ─────────────────────────────────────────────────────────────────────────────
# DYNAMIC TWO-PASS NUMBERED CANVAS (PAGE X OF Y)
# ─────────────────────────────────────────────────────────────────────────────
class NumberedCanvas(canvas.Canvas):
    """
    Two-pass ReportLab Canvas that stores page states and stamps exact
    'Page X of Y' total page numbers and running headers/footers upon save().
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []
        # Dynamic metadata attached per report build
        self.inspection_number: str = "LM-INSPECTION"
        self.report_version: int = 1
        self.report_id: str = ""
        self.generated_date_str: str = ""

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, total_pages: int):
        self.saveState()

        # ── 1. Running Header (Displayed on Page 2 and subsequent pages) ───────
        if self._pageNumber > 1:
            self.setFont(REPORT_FONT_BOLD, 7.5)
            self.setFillColor(COLOR_PRIMARY_NAVY)
            self.drawString(MARGIN_LEFT, PAGE_HEIGHT - 24, "NIRIKSHA \u2014 LEGAL METROLOGY INSPECTION REPORT")

            self.setFont(REPORT_FONT_REGULAR, 7.5)
            self.setFillColor(COLOR_TEXT_MUTED)
            self.drawRightString(
                PAGE_WIDTH - MARGIN_RIGHT,
                PAGE_HEIGHT - 24,
                f"Inspection No: {self.inspection_number} \u2022 Version v{self.report_version}"
            )

            # Header thin rule
            self.setStrokeColor(COLOR_BORDER)
            self.setLineWidth(0.6)
            self.line(MARGIN_LEFT, PAGE_HEIGHT - 28, PAGE_WIDTH - MARGIN_RIGHT, PAGE_HEIGHT - 28)

        # ── 2. Running Footer (Displayed on ALL pages) ─────────────────────────
        footer_line_y = MARGIN_BOTTOM - 8
        self.setStrokeColor(COLOR_BORDER)
        self.setLineWidth(0.6)
        self.line(MARGIN_LEFT, footer_line_y, PAGE_WIDTH - MARGIN_RIGHT, footer_line_y)

        self.setFont(REPORT_FONT_REGULAR, 7.0)
        self.setFillColor(COLOR_TEXT_MUTED)
        footer_left = f"NiriKsha | Inspection Report | {self.inspection_number} | Official Statutory Record"
        self.drawString(MARGIN_LEFT, footer_line_y - 10, footer_left)

        page_str = f"Page {self._pageNumber} of {total_pages}"
        self.drawRightString(PAGE_WIDTH - MARGIN_RIGHT, footer_line_y - 10, page_str)

        self.restoreState()


# ─────────────────────────────────────────────────────────────────────────────
# TYPOGRAPHY & PARAGRAPH STYLES
# ─────────────────────────────────────────────────────────────────────────────
def get_report_stylesheet() -> StyleSheet1:
    """Returns a unified typography stylesheet for NiriKsha PDF reports."""
    styles = getSampleStyleSheet()

    # Document / Cover Titles
    styles.add(ParagraphStyle(
        name="ReportDocTitle",
        fontName=REPORT_FONT_BOLD,
        fontSize=13,
        leading=16,
        alignment=1,  # Center
        textColor=COLOR_PRIMARY_NAVY,
        spaceAfter=3,
        spaceBefore=0
    ))
    styles.add(ParagraphStyle(
        name="ReportDocSubtitle",
        fontName=REPORT_FONT_REGULAR,
        fontSize=8.5,
        leading=11,
        alignment=1,  # Center
        textColor=COLOR_TEXT_MUTED,
        spaceAfter=6
    ))
    styles.add(ParagraphStyle(
        name="GovtAgencyHeader",
        fontName=REPORT_FONT_BOLD,
        fontSize=9.5,
        leading=12,
        alignment=0,  # Left
        textColor=COLOR_PRIMARY_NAVY
    ))
    styles.add(ParagraphStyle(
        name="GovtAgencySub",
        fontName=REPORT_FONT_REGULAR,
        fontSize=7.5,
        leading=10,
        alignment=0,  # Left
        textColor=COLOR_TEXT_MUTED
    ))

    # Section Headers
    styles.add(ParagraphStyle(
        name="SectionHeaderTitle",
        fontName=REPORT_FONT_BOLD,
        fontSize=9.0,
        leading=11,
        textColor=colors.white,
        spaceBefore=0,
        spaceAfter=0
    ))
    styles.add(ParagraphStyle(
        name="SectionHeaderSubtitle",
        fontName=REPORT_FONT_OBLIQUE,
        fontSize=7.0,
        leading=9,
        textColor=COLOR_TEXT_MUTED,
        spaceBefore=2,
        spaceAfter=4
    ))

    # Body Text
    styles.add(ParagraphStyle(
        name="ReportBody",
        fontName=REPORT_FONT_REGULAR,
        fontSize=7.5,
        leading=9.5,
        textColor=COLOR_TEXT_DARK
    ))
    styles.add(ParagraphStyle(
        name="ReportBodyBold",
        fontName=REPORT_FONT_BOLD,
        fontSize=7.5,
        leading=9.5,
        textColor=COLOR_TEXT_DARK
    ))
    styles.add(ParagraphStyle(
        name="ReportBodyMuted",
        fontName=REPORT_FONT_REGULAR,
        fontSize=7.0,
        leading=9.0,
        textColor=COLOR_TEXT_MUTED
    ))

    # Table Typography
    styles.add(ParagraphStyle(
        name="TableHeaderDark",
        fontName=REPORT_FONT_BOLD,
        fontSize=7.0,
        leading=9.0,
        alignment=0,
        textColor=COLOR_PRIMARY_NAVY
    ))
    styles.add(ParagraphStyle(
        name="TableHeaderCenter",
        fontName=REPORT_FONT_BOLD,
        fontSize=7.0,
        leading=9.0,
        alignment=1,
        textColor=COLOR_PRIMARY_NAVY
    ))
    styles.add(ParagraphStyle(
        name="TableCellText",
        fontName=REPORT_FONT_REGULAR,
        fontSize=7.0,
        leading=9.0,
        textColor=COLOR_TEXT_DARK
    ))
    styles.add(ParagraphStyle(
        name="TableCellBold",
        fontName=REPORT_FONT_BOLD,
        fontSize=7.0,
        leading=9.0,
        textColor=COLOR_TEXT_DARK
    ))
    styles.add(ParagraphStyle(
        name="TableCellCenter",
        fontName=REPORT_FONT_REGULAR,
        fontSize=7.0,
        leading=9.0,
        alignment=1,
        textColor=COLOR_TEXT_DARK
    ))
    styles.add(ParagraphStyle(
        name="TableCellCenterBold",
        fontName=REPORT_FONT_BOLD,
        fontSize=7.0,
        leading=9.0,
        alignment=1,
        textColor=COLOR_TEXT_DARK
    ))
    styles.add(ParagraphStyle(
        name="TableCellMono",
        fontName="Courier",
        fontSize=6.5,
        leading=8.5,
        textColor=COLOR_TEXT_DARK
    ))
    styles.add(ParagraphStyle(
        name="TableCellSmall",
        fontName=REPORT_FONT_REGULAR,
        fontSize=6.5,
        leading=8.5,
        textColor=COLOR_TEXT_DARK
    ))

    # KPI / Summary Cards
    styles.add(ParagraphStyle(
        name="KPICardValue",
        fontName=REPORT_FONT_BOLD,
        fontSize=15.0,
        leading=17.0,
        alignment=1,
        textColor=COLOR_PRIMARY_NAVY
    ))
    styles.add(ParagraphStyle(
        name="KPICardLabel",
        fontName=REPORT_FONT_BOLD,
        fontSize=6.5,
        leading=8.0,
        alignment=1,
        textColor=COLOR_TEXT_MUTED
    ))

    # Disclaimers & Safety Statements
    styles.add(ParagraphStyle(
        name="LegalNoticeText",
        fontName=REPORT_FONT_REGULAR,
        fontSize=6.5,
        leading=8.5,
        textColor=COLOR_TEXT_MUTED
    ))
    styles.add(ParagraphStyle(
        name="LegalNoticeTextBold",
        fontName=REPORT_FONT_BOLD,
        fontSize=6.5,
        leading=8.5,
        textColor=COLOR_TEXT_DARK
    ))

    return styles
