"""PDF report generation for completed inspections."""

from io import BytesIO
from html import escape
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from rules import RULE_ENGINE_VERSION, load_rules


def _paragraph(text: Any, style: ParagraphStyle) -> Paragraph:
    safe_text = escape(str(text).replace("₹", "INR ")).replace("\n", "<br/>")
    return Paragraph(safe_text, style)


def build_pdf(record: dict[str, Any], evidence_path: Path | None = None) -> bytes:
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
        title=f"LabelGuard inspection {record['id']}",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("LabelGuardTitle", parent=styles["Title"], alignment=TA_CENTER)
    small = ParagraphStyle("LabelGuardSmall", parent=styles["BodyText"], fontSize=8, leading=10)
    table_header = ParagraphStyle(
        "LabelGuardTableHeader",
        parent=small,
        fontName="Helvetica-Bold",
        textColor=colors.white,
    )
    story: list[Any] = [
        Paragraph("LabelGuard Inspection Report", title_style),
        Spacer(1, 8),
        Paragraph("Automated Deterministic Screening Result", styles["Heading2"]),
        _paragraph(
            "Decision-support compliance screening report. "
            "LabelGuard provides automated screening based on configured deterministic statutory rules under the "
            "Legal Metrology (Packaged Commodities) Rules, 2011. This report does not constitute official legal certification.",
            styles["BodyText"],
        ),
        Spacer(1, 10),
    ]

    metadata = [
        ["Inspection ID", str(record["id"])],
        ["Original file", record.get("original_filename", "unnamed")],
        ["Created", record.get("created_at", "")],
        [
            "Overall automated result",
            (
                "NO ISSUE FLAGGED (engine status: compliant)"
                if record.get("overall_status") == "compliant"
                else record.get("overall_status", "").replace("_", " ").upper()
            ),
        ],
        ["OCR engine", record.get("ocr_engine", "unknown")],
        ["Rule engine", record.get("rule_engine_version") or RULE_ENGINE_VERSION],
        ["Package scope", record.get("context", {}).get("package_scope", "unknown")],
        ["OCR orientation correction", f"{int(record.get('orientation_degrees', 0))}°"],
    ]
    metadata_table = Table(
        [[_paragraph(label, small), _paragraph(value, small)] for label, value in metadata],
        colWidths=[1.7 * inch, 5.35 * inch],
    )
    metadata_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#E8EEF4")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#B8C4D0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.extend([metadata_table, Spacer(1, 14), Paragraph("Image quality", styles["Heading2"])])

    quality = record.get("quality", {})
    quality_rows = [["Status", quality.get("status", "unknown")]]
    for label, key in [
        ("Dimensions", "dimensions"),
        ("Blur score", "blur_score"),
        ("Glare ratio", "glare_ratio"),
        ("Warnings", "warnings"),
    ]:
        value = quality.get(key)
        if key == "dimensions" and not value:
            value = f"{quality.get('width', '?')} × {quality.get('height', '?')}"
        if isinstance(value, list):
            value = "; ".join(value) or "None"
        quality_rows.append([label, value if value is not None else "unknown"])
    quality_table = Table(quality_rows, colWidths=[1.35 * inch, 5.7 * inch])
    quality_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F3F5F7")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#C8D0D8")),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.extend([quality_table, Spacer(1, 14), Paragraph("Extracted fields", styles["Heading2"])])

    verification_fields = record.get("verification", {}).get("fields", {})
    field_rows = [["Field", "Value", "Verification"]]
    for field, value in record.get("extracted_fields", {}).items():
        text = value.get("text") if isinstance(value, dict) else value
        provenance = verification_fields.get(field, {})
        verification_label = provenance.get("verification_source") or provenance.get(
            "verification_state", "Not recorded"
        )
        field_rows.append(
            [
                field.replace("_", " ").title(),
                str(text or "Not detected").replace("₹", "INR "),
                str(verification_label).replace("_", " ").title(),
            ]
        )
    field_table = Table(
        field_rows, colWidths=[2.05 * inch, 3.2 * inch, 1.8 * inch], repeatRows=1
    )
    field_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1C344D")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#C8D0D8")),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.extend([field_table, Spacer(1, 14), Paragraph("Rule findings", styles["Heading2"])])

    finding_rows = [["Rule", "Field", "Status", "Confidence", "Reason and source"]]
    rule_descriptions = {rule["rule_id"]: rule.get("description", "") for rule in load_rules()}
    for finding in record.get("findings", []):
        finding_rows.append(
            [
                finding.get("rule_id", ""),
                finding.get("field", ""),
                finding.get("status", ""),
                f"{float(finding.get('confidence', 0)):.0%}",
                (
                    (finding.get("description") or rule_descriptions.get(finding.get("rule_id"), ""))
                    + (f" Source: {finding.get('source_citation')}" if finding.get("source_citation") else "")
                ),
            ]
        )
    if len(finding_rows) == 1:
        finding_rows.append(["None", "", "", "", "No rule findings were produced."])
    findings_table = Table(
        [[_paragraph(cell, table_header if index == 0 else small) for cell in row] for index, row in enumerate(finding_rows)],
        colWidths=[1.1 * inch, 1.3 * inch, 0.7 * inch, 0.75 * inch, 3.2 * inch],
        repeatRows=1,
    )
    findings_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1C344D")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#C8D0D8")),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(findings_table)

    gemini = record.get("gemini_status", {})
    verification = record.get("verification", {})
    story.extend(
        [
            Spacer(1, 14),
            Paragraph("Gemini Extraction and Validation", styles["Heading2"]),
        ]
    )
    verification_rows = [
        ["Gemini extraction", str(gemini.get("status", "not recorded")).replace("_", " ")],
        ["Model", gemini.get("model", "not configured")],
        ["Route reason", gemini.get("route_reason") or "not recorded"],
        ["Image readability", gemini.get("image_readability") or "not assessed"],
        ["Candidate fields", gemini.get("candidate_count", 0)],
        ["Deterministic validation", "Applied" if gemini.get("deterministic_validation") else "Not recorded"],
        ["Manual review requested", "Yes" if verification.get("review_required") else "No"],
        ["Explanation source", str(gemini.get("explanation_status", "deterministic fallback")).replace("_", " ")],
    ]
    verification_table = Table(
        [[_paragraph(label, small), _paragraph(value, small)] for label, value in verification_rows],
        colWidths=[1.8 * inch, 5.25 * inch],
    )
    verification_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#E8F7F3")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#B8C4D0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ]
        )
    )
    story.extend(
        [
            verification_table,
            Spacer(1, 12),
            Paragraph("AI-Assisted Plain-Language Explanation", styles["Heading2"]),
            _paragraph(
                record.get("ai_summary")
                or "A deterministic explanation was not stored for this historical inspection.",
                styles["BodyText"],
            ),
            Spacer(1, 10),
            Paragraph("Recommended Next Step", styles["Heading2"]),
        ]
    )
    recommendations = record.get("recommendation", [])
    if not recommendations:
        recommendations = [
            "Review the accepted evidence and deterministic findings.",
            "Capture a clearer image for any unreadable declaration.",
            "Record the inspector's independent decision.",
        ]
    for index, recommendation in enumerate(recommendations[:4], start=1):
        story.append(_paragraph(f"{index}. {recommendation}", styles["BodyText"]))

    story.extend(
        [
            Spacer(1, 10),
            _paragraph(
                "The compliance screening result is generated by LabelGuard's configured "
                "deterministic rule engine. AI-assisted visual verification and explanations "
                "are advisory and do not independently determine legal compliance.",
                small,
            ),
        ]
    )

    # Human review & corrections section
    from database import get_audit_events, get_field_corrections, get_latest_review

    insp_id_str = str(record["id"])
    review = get_latest_review(insp_id_str)
    corrections = get_field_corrections(insp_id_str)
    audit_events = get_audit_events(insp_id_str)

    if review and review.get("review_status") != "NOT_REVIEWED":
        story.extend([Spacer(1, 14), Paragraph("Inspector Review Disposition", styles["Heading2"])])
        review_rows = [
            ["Review Status", review.get("review_status", "").replace("_", " ")],
            ["Reviewed By", review.get("reviewed_by", "Inspector")],
            ["Review Date", review.get("reviewed_at", "")],
            ["Notes", review.get("review_notes") or "None"],
        ]
        review_table = Table(review_rows, colWidths=[1.5 * inch, 5.55 * inch])
        review_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EBF5FB")),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#AED6F1")),
                    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(review_table)

    if corrections:
        story.extend([Spacer(1, 14), Paragraph("Field Corrections History", styles["Heading2"])])
        corr_rows = [["Field", "Original OCR", "Corrected Value", "Reason / Actor"]]
        for c in corrections:
            corr_rows.append([
                c.get("field", "").replace("_", " ").title(),
                c.get("original_text", ""),
                c.get("corrected_text", ""),
                f"{c.get('reason', '')} (by {c.get('actor', 'Inspector')})",
            ])
        corr_table = Table(
            [[_paragraph(cell, table_header if index == 0 else small) for cell in row] for index, row in enumerate(corr_rows)],
            colWidths=[1.4 * inch, 1.8 * inch, 1.8 * inch, 2.05 * inch],
            repeatRows=1,
        )
        corr_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2C3E50")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#BDC3C7")),
                    ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(corr_table)

    if audit_events:
        story.extend([Spacer(1, 14), Paragraph("Audit Trail", styles["Heading2"])])
        audit_rows = [["Timestamp", "Event", "Actor", "Description"]]
        for a in audit_events:
            audit_rows.append([
                a.get("created_at", "")[:19].replace("T", " "),
                a.get("event_type", ""),
                a.get("actor", ""),
                a.get("description", ""),
            ])
        audit_table = Table(
            [[_paragraph(cell, table_header if index == 0 else small) for cell in row] for index, row in enumerate(audit_rows)],
            colWidths=[1.35 * inch, 1.4 * inch, 1.1 * inch, 3.2 * inch],
            repeatRows=1,
        )
        audit_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#34495E")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#BDC3C7")),
                    ("FONTSIZE", (0, 0), (-1, -1), 7.0),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(audit_table)

    ocr_text = record.get("ocr_text", "").strip()
    if ocr_text:
        story.extend(
            [
                Spacer(1, 14),
                Paragraph("OCR text", styles["Heading2"]),
                _paragraph(ocr_text, small),
            ]
        )

    if evidence_path and evidence_path.exists():
        story.append(
            KeepTogether(
                [
                    Spacer(1, 14),
                    Paragraph("Evidence image", styles["Heading2"]),
                    Image(str(evidence_path), width=6.8 * inch, height=4.8 * inch, kind="proportional"),
                ]
            )
        )

    story.extend(
        [
            Spacer(1, 14),
            _paragraph(
                "Notice: Final statutory determination of legal compliance requires verification "
                "by an authorized Legal Metrology officer. Automated screenings are advisory decision aids.",
                small,
            ),
        ]
    )

    document.build(story)
    return buffer.getvalue()
