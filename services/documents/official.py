"""
Official Kapuletu document builder (ReportLab).

Every official document gets the same frame:
  - the organisation letterhead on every page (logo + details from the organisation profile)
  - a title block with reference number, issue date (EAT), "Prepared by" and classification
  - "Page X of Y" footers
  - optional signature block, and an audit-log entry recording that the document was issued

Usage:
    doc = OfficialDocument(db, title="Staff Attendance Report", department="HR", doc_type="ATT", prepared_by="Jane Doe")
    doc.section("Summary")
    doc.key_figures([("Attendance", "94%", "128 of 136 days")])
    doc.table(["Name", "Days"], rows, numeric_cols={1})
    doc.signature_block()
    pdf_bytes = doc.build(actor_id=user_id)
"""
import datetime
import io
import os
import secrets
from typing import Any, Iterable, Optional, Sequence
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from common.utils import nairobi_now
from services.documents.organization import OrganizationProfile, get_organization_profile

BRAND = colors.HexColor("#097255")
BRAND_TINT = colors.HexColor("#E8F3EF")
INK = colors.HexColor("#1F2937")
MUTED = colors.HexColor("#6B7280")
RULE = colors.HexColor("#D1D5DB")
ZEBRA = colors.HexColor("#F7F9F8")

LOGO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "assets", "logos", "primary logo.png"
)

MARGIN_X = 16 * mm
HEADER_HEIGHT = 30 * mm
FOOTER_HEIGHT = 14 * mm

DEFAULT_CLASSIFICATION = "Confidential — internal use only"


def esc(value: Any) -> str:
    """Escapes text for ReportLab paragraph markup."""
    return "" if value is None else escape(str(value))


def make_reference(department: str, doc_type: str, issued_at: datetime.datetime, suffix: Optional[str] = None) -> str:
    """KPL/<DEPT>/<TYPE>/<YYYYMM>/<SUFFIX>; the suffix is random unless the document has a natural one."""
    return f"KPL/{department}/{doc_type}/{issued_at:%Y%m}/{suffix or secrets.token_hex(3).upper()}"


def _styles() -> dict[str, ParagraphStyle]:
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=9, leading=12, textColor=INK)
    return {
        "body": base,
        "cell": ParagraphStyle("cell", parent=base, fontSize=8, leading=10),
        "cell_head": ParagraphStyle("cell_head", parent=base, fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=colors.white),
        "cell_num": ParagraphStyle("cell_num", parent=base, fontSize=8, leading=10, alignment=TA_RIGHT),
        "cell_head_num": ParagraphStyle("cell_head_num", parent=base, fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=colors.white, alignment=TA_RIGHT),
        "figure_value": ParagraphStyle("figure_value", parent=base, fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=BRAND),
        "figure_label": ParagraphStyle("figure_label", parent=base, fontName="Helvetica-Bold", fontSize=8, leading=10),
        "figure_hint": ParagraphStyle("figure_hint", parent=base, fontSize=7, leading=9, textColor=MUTED),
        "meta_label": ParagraphStyle("meta_label", parent=base, fontSize=7, leading=9, textColor=MUTED),
        "meta_value": ParagraphStyle("meta_value", parent=base, fontName="Helvetica-Bold", fontSize=8.5, leading=11),
        "muted": ParagraphStyle("muted", parent=base, textColor=MUTED, fontSize=8, leading=11),
        "section": ParagraphStyle("section", parent=base, fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=BRAND, spaceBefore=10, spaceAfter=6, keepWithNext=1),
        "subtitle": ParagraphStyle("subtitle", parent=base, fontSize=10, leading=13, textColor=MUTED),
        "title": ParagraphStyle("title", parent=base, fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=INK, spaceAfter=2),
    }


class _NumberedCanvas(rl_canvas.Canvas):
    """Defers page output so every page can be decorated knowing the total page count."""

    def __init__(self, *args, decorate, **kwargs):
        super().__init__(*args, **kwargs)
        self._decorate = decorate
        self._saved_pages: list[dict] = []

    def showPage(self):  # noqa: N802 (ReportLab API)
        self._saved_pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_pages)
        for state in self._saved_pages:
            self.__dict__.update(state)
            self._decorate(self, self._pageNumber, total)
            super().showPage()
        super().save()


class OfficialDocument:
    def __init__(
        self,
        db: Session,
        *,
        title: str,
        department: str,
        doc_type: str,
        subtitle: Optional[str] = None,
        prepared_by: Optional[str] = None,
        reference: Optional[str] = None,
        classification: Optional[str] = DEFAULT_CLASSIFICATION,
        orientation: str = "portrait",
        issued_at: Optional[datetime.datetime] = None,
    ):
        self._db = db
        self.profile: OrganizationProfile = get_organization_profile(db)
        self.title = title
        self.subtitle = subtitle
        self.prepared_by = prepared_by
        self.classification = classification
        self.issued_at = issued_at or nairobi_now()
        self.reference = reference or make_reference(department, doc_type, self.issued_at)
        self.pagesize = landscape(A4) if orientation == "landscape" else A4
        self.width = self.pagesize[0] - 2 * MARGIN_X
        self.styles = _styles()
        self._story: list = []
        self._title_block()

    # --- Content helpers ---------------------------------------------------

    def section(self, heading: str) -> None:
        self._story.append(Paragraph(esc(heading), self.styles["section"]))

    def paragraph(self, text: str, muted: bool = False) -> None:
        self._story.append(Paragraph(esc(text), self.styles["muted" if muted else "body"]))

    def spacer(self, height_mm: float = 4) -> None:
        self._story.append(Spacer(1, height_mm * mm))

    def key_figures(self, figures: Sequence[tuple[str, str, Optional[str]]], columns: int = 4) -> None:
        """Tiles of (label, value, optional hint), laid out in rows of `columns`."""
        cells = [
            [Paragraph(esc(value), self.styles["figure_value"]),
             Paragraph(esc(label), self.styles["figure_label"]),
             Paragraph(esc(hint or ""), self.styles["figure_hint"])]
            for label, value, hint in figures
        ]
        rows = [cells[i:i + columns] for i in range(0, len(cells), columns)]
        rows[-1] += [""] * (columns - len(rows[-1]))
        gap = 3 * mm
        tile_width = (self.width - gap * (columns - 1)) / columns
        table = Table(
            [[self._tile(cell, tile_width) if cell else "" for cell in row] for row in rows],
            colWidths=[tile_width + (gap if i < columns - 1 else 0) for i in range(columns)],
            hAlign="LEFT",
        )
        table.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), gap),
                                   ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), gap),
                                   ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        self._story.append(table)

    def table(
        self,
        header: Sequence[str],
        rows: Iterable[Sequence[Any]],
        col_widths: Optional[Sequence[float]] = None,
        numeric_cols: Iterable[int] = (),
        empty_message: str = "No records for this period.",
    ) -> None:
        """A branded data table; widths are fractions of the printable width (default: equal)."""
        numeric = set(numeric_cols)
        rows = list(rows)
        if not rows:
            self.paragraph(empty_message, muted=True)
            return

        def cell(value, col, head=False):
            key = ("cell_head" if head else "cell") + ("_num" if col in numeric else "")
            return Paragraph(esc(value), self.styles[key])

        data = [[cell(h, i, head=True) for i, h in enumerate(header)]]
        data += [[cell(v, i) for i, v in enumerate(row)] for row in rows]
        fractions = col_widths or [1 / len(header)] * len(header)
        table = Table(data, colWidths=[self.width * f for f in fractions], repeatRows=1, hAlign="LEFT")
        style = [
            ("BACKGROUND", (0, 0), (-1, 0), BRAND),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, RULE),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ]
        style += [("BACKGROUND", (0, r), (-1, r), ZEBRA) for r in range(2, len(data), 2)]
        table.setStyle(TableStyle(style))
        self._story.append(table)

    def bullet_list(self, items: Iterable[str]) -> None:
        for item in items:
            self._story.append(Paragraph(f"•&nbsp;&nbsp;{esc(item)}", self.styles["body"]))

    def signature_block(self, roles: Sequence[str] = ("Prepared by", "Approved by"), note: Optional[str] = None) -> None:
        """Sign-off lines; an optional note (e.g. methodology) is kept on the same page as the signatures."""
        def column(role):
            name = self.prepared_by if role == "Prepared by" and self.prepared_by else ""
            return [
                Paragraph(esc(role), self.styles["figure_label"]),
                Spacer(1, 10 * mm),
                Paragraph(f"Name: {esc(name) or '_' * 32}", self.styles["body"]),
                Spacer(1, 4 * mm),
                Paragraph("Signature: " + "_" * 28, self.styles["body"]),
                Spacer(1, 4 * mm),
                Paragraph("Date: " + "_" * 32, self.styles["body"]),
            ]

        table = Table([[column(role) for role in roles]], colWidths=[self.width / len(roles)] * len(roles), hAlign="LEFT")
        table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        lead = [Spacer(1, 3 * mm), Paragraph(esc(note), self.styles["muted"])] if note else []
        self._story.append(KeepTogether([*lead, Spacer(1, 8 * mm), table]))

    # --- Output ------------------------------------------------------------

    def build(self, *, actor_id: Optional[str] = None, audit: bool = True, audit_details: Optional[dict] = None) -> bytes:
        stream = io.BytesIO()
        doc = SimpleDocTemplate(
            stream,
            pagesize=self.pagesize,
            leftMargin=MARGIN_X,
            rightMargin=MARGIN_X,
            topMargin=HEADER_HEIGHT + 6 * mm,
            bottomMargin=FOOTER_HEIGHT + 4 * mm,
            title=self.title,
            author=self.profile.name,
            subject=self.reference,
        )
        doc.build(self._story, canvasmaker=lambda *a, **kw: _NumberedCanvas(*a, decorate=self._decorate_page, **kw))

        if audit:
            from services.audit.service import AuditService
            AuditService(self._db).log_action(
                actor_id=actor_id,
                action="DOCUMENT_ISSUED",
                entity_type="DOCUMENT",
                entity_id=self.reference,
                details={"message": f"Official document issued: {self.title}", "title": self.title,
                         "subtitle": self.subtitle, **(audit_details or {})},
            )
        return stream.getvalue()

    @property
    def filename_stem(self) -> str:
        return self.reference.replace("/", "-")

    # --- Internals ---------------------------------------------------------

    def _tile(self, cell, width):
        tile = Table([[c] for c in cell], colWidths=[width])
        tile.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), BRAND_TINT),
            ("LINEBEFORE", (0, 0), (0, -1), 2, BRAND),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, 0), 6),
            ("TOPPADDING", (0, 1), (-1, -1), 0),
            ("BOTTOMPADDING", (0, -1), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -2), 1),
        ]))
        return tile

    def _title_block(self) -> None:
        self._story.append(Paragraph(esc(self.title), self.styles["title"]))
        if self.subtitle:
            self._story.append(Paragraph(esc(self.subtitle), self.styles["subtitle"]))
        self._story.append(Spacer(1, 4 * mm))

        meta = [
            ("Reference", self.reference),
            ("Date issued", f"{self.issued_at:%d %B %Y, %H:%M} EAT"),
            ("Prepared by", self.prepared_by or self.profile.name),
            ("Classification", self.classification or "Official"),
        ]
        cells = [[Paragraph(esc(label), self.styles["meta_label"]), Paragraph(esc(value), self.styles["meta_value"])] for label, value in meta]
        # Weighted so the reference code never wraps, even on portrait pages.
        table = Table([cells], colWidths=[self.width * f for f in (0.31, 0.25, 0.2, 0.24)], hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, RULE),
            ("LINEAFTER", (0, 0), (-2, -1), 0.5, RULE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        self._story.append(table)
        self._story.append(Spacer(1, 4 * mm))

    def _decorate_page(self, canvas: rl_canvas.Canvas, page: int, total: int) -> None:
        width, height = self.pagesize
        p = self.profile
        top = height - 10 * mm

        # Letterhead: logo on the left, organisation details on the right.
        if os.path.exists(LOGO_PATH):
            logo = ImageReader(LOGO_PATH)
            img_w, img_h = logo.getSize()
            logo_h = 13 * mm
            canvas.drawImage(logo, MARGIN_X, top - logo_h, width=logo_h * img_w / img_h, height=logo_h, mask="auto")
        else:
            canvas.setFont("Helvetica-Bold", 16)
            canvas.setFillColor(BRAND)
            canvas.drawString(MARGIN_X, top - 9 * mm, p.name)

        right = width - MARGIN_X
        canvas.setFillColor(INK)
        canvas.setFont("Helvetica-Bold", 10.5)
        canvas.drawRightString(right, top - 3.5 * mm, p.name)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        detail_lines = [
            " · ".join(filter(None, [p.address, p.phone])),
            " · ".join(filter(None, [p.email, p.website])),
            " · ".join(filter(None, [
                f"Reg. No. {p.registration_number}" if p.registration_number else None,
                f"KRA PIN {p.tax_pin}" if p.tax_pin else None,
            ])),
        ]
        y = top - 8 * mm
        for line in filter(None, detail_lines):
            canvas.drawRightString(right, y, line)
            y -= 3.6 * mm

        rule_y = height - HEADER_HEIGHT
        canvas.setStrokeColor(BRAND)
        canvas.setLineWidth(1.4)
        canvas.line(MARGIN_X, rule_y, right, rule_y)

        # Footer: reference, classification, page numbering.
        footer_y = FOOTER_HEIGHT - 4 * mm
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN_X, footer_y + 4 * mm, right, footer_y + 4 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(MARGIN_X, footer_y, f"{p.name} · Ref {self.reference}")
        if self.classification:
            canvas.drawCentredString(width / 2, footer_y, self.classification)
        canvas.drawRightString(right, footer_y, f"Page {page} of {total}")
