"""
PDF generation for clinical decision support reports.
Uses reportlab to produce a formatted PDF.
"""

import io
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY


def generate_pdf(result: dict) -> bytes:
    """
    Generate a PDF report from a MetaAnalysisResult dict.

    Args:
        result: dict from MetaAnalysisResult.to_dict()

    Returns:
        PDF bytes.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "ClinTitle",
        parent=styles["Heading1"],
        fontSize=16,
        textColor=colors.HexColor("#1a3a5c"),
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "ClinSubtitle",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#555555"),
        spaceAfter=12,
    )
    section_style = ParagraphStyle(
        "ClinSection",
        parent=styles["Heading2"],
        fontSize=11,
        textColor=colors.HexColor("#1a3a5c"),
        spaceBefore=14,
        spaceAfter=4,
        borderPad=2,
    )
    body_style = ParagraphStyle(
        "ClinBody",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        alignment=TA_JUSTIFY,
        spaceAfter=8,
    )
    bottom_line_style = ParagraphStyle(
        "BottomLine",
        parent=styles["Normal"],
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#1a3a5c"),
        backColor=colors.HexColor("#eef4fb"),
        borderColor=colors.HexColor("#1a3a5c"),
        borderWidth=1,
        borderPad=8,
        spaceAfter=12,
    )
    ref_style = ParagraphStyle(
        "ClinRef",
        parent=styles["Normal"],
        fontSize=8,
        leading=12,
        textColor=colors.HexColor("#333333"),
        spaceAfter=4,
    )
    warning_style = ParagraphStyle(
        "Warning",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.HexColor("#888888"),
        alignment=TA_CENTER,
    )

    story = []

    # ── Header ────────────────────────────────────────────────────────────────
    story.append(
        Paragraph("Clinical Decision Support Report", title_style)
    )
    ts = datetime.now().strftime("%B %d, %Y  %H:%M")
    story.append(
        Paragraph(
            f"Generated: {ts} &nbsp;|&nbsp; Evidence-Based Medicine Tool",
            subtitle_style,
        )
    )
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#1a3a5c")))
    story.append(Spacer(1, 8))

    # ── Clinical Question ──────────────────────────────────────────────────────
    story.append(Paragraph("Clinical Question (PICO)", section_style))
    pico = result.get("pico_statement", "")
    story.append(Paragraph(_escape(pico), body_style))

    # ── Bottom Line ────────────────────────────────────────────────────────────
    story.append(Paragraph("Clinical Bottom Line", section_style))
    story.append(
        Paragraph(_escape(result.get("clinical_bottom_line", "")), bottom_line_style)
    )

    # ── Evidence Summary ───────────────────────────────────────────────────────
    story.append(Paragraph("Evidence Summary", section_style))
    story.append(
        Paragraph(
            f"<b>Evidence quality:</b> {_escape(result.get('evidence_quality', ''))}",
            body_style,
        )
    )
    for para in result.get("summary", "").split("\n\n"):
        if para.strip():
            story.append(Paragraph(_escape(para.strip()), body_style))

    # ── Probability Estimates ──────────────────────────────────────────────────
    estimates = result.get("probability_estimates", {})
    if estimates:
        story.append(Paragraph("Probability Estimates", section_style))

        table_data = [["Metric", "Value"]]
        metric_map = [
            ("control_event_rate", "Control Event Rate (CER)", ".1%"),
            ("treatment_event_rate", "Treatment Event Rate (EER)", ".1%"),
            ("arr", "Absolute Risk Reduction (ARR)", ".1%"),
            ("rrr", "Relative Risk Reduction (RRR)", ".1%"),
            ("nnt", "Number Needed to Treat (NNT)", ".1f"),
            ("sensitivity", "Sensitivity", ".1%"),
            ("specificity", "Specificity", ".1%"),
            ("prevalence", "Pre-test Probability (Prevalence)", ".1%"),
            ("ppv", "Positive Predictive Value (PPV)", ".1%"),
            ("npv", "Negative Predictive Value (NPV)", ".1%"),
            ("lr_positive", "Positive Likelihood Ratio (LR+)", ".2f"),
            ("lr_negative", "Negative Likelihood Ratio (LR−)", ".3f"),
            ("post_test_prob_positive", "Post-test Prob (test positive)", ".1%"),
            ("post_test_prob_negative", "Post-test Prob (test negative)", ".1%"),
        ]
        for key, label, fmt in metric_map:
            val = estimates.get(key)
            if val is not None:
                if fmt.endswith("%"):
                    display = f"{val:{fmt}}"
                else:
                    display = f"{val:{fmt}}"
                table_data.append([label, display])

        if len(table_data) > 1:
            col_w = [4.2 * inch, 1.8 * inch]
            tbl = Table(table_data, colWidths=col_w)
            tbl.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a3a5c")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f4f8")]),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
                        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            story.append(tbl)
            story.append(Spacer(1, 4))

        if estimates.get("notes"):
            story.append(
                Paragraph(f"<i>Note: {_escape(estimates['notes'])}</i>", ref_style)
            )

    # ── Limitations ────────────────────────────────────────────────────────────
    limitations = result.get("limitations", "")
    if limitations:
        story.append(Paragraph("Limitations", section_style))
        story.append(Paragraph(_escape(limitations), body_style))

    # ── References ─────────────────────────────────────────────────────────────
    papers = result.get("papers_used", [])
    if papers:
        story.append(Paragraph("References", section_style))
        for i, p in enumerate(papers, 1):
            authors = ", ".join((p.get("authors") or [])[:3])
            if len(p.get("authors") or []) > 3:
                authors += " et al."
            year = p.get("year", "")
            venue = p.get("venue", "")
            title = p.get("title", "")
            urls = p.get("urls") or []
            link_part = ""
            if urls:
                link_part = f' <link href="{urls[0]}" color="blue">[link]</link>'
            line = f"[{i}] {_escape(authors)} ({year}). <i>{_escape(title)}</i>. {_escape(venue)}.{link_part}"
            story.append(Paragraph(line, ref_style))

    # ── Disclaimer ─────────────────────────────────────────────────────────────
    story.append(Spacer(1, 16))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#aaaaaa")))
    story.append(Spacer(1, 4))
    story.append(
        Paragraph(
            "DISCLAIMER: This report is generated by an AI-assisted tool and is intended "
            "to support—not replace—clinical judgement. Always verify findings against "
            "primary sources. Not a substitute for professional medical advice.",
            warning_style,
        )
    )

    doc.build(story)
    return buf.getvalue()


def _escape(text: str) -> str:
    """Escape XML special characters for ReportLab Paragraph."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
