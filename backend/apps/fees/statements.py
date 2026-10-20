"""The fee statement a student is sent: what was agreed and where it stands.

One A4 page (more if the schedule is long), drawn with reportlab's flowables so
a 36-row schedule pages itself. Everything on it comes from the ledger at the
moment it is drawn — the fee, the discount and how it was given, what has been
received, what is left, and each instalment's state.

It is a statement, not a tax invoice, and says so: the institution has no
GSTIN or tax rates configured here, and a document that looks like an invoice
without them would be wrong in a way that matters.
"""

from __future__ import annotations

from io import BytesIO

from django.utils import timezone

from .models import FeePlan, InstallmentStatus, installment_rows

STATE_LABEL = {
    InstallmentStatus.PAID: "Paid",
    InstallmentStatus.PENDING: "Due",
    InstallmentStatus.OVERDUE: "Overdue",
    InstallmentStatus.UPCOMING: "Upcoming",
}


def rupees(value) -> str:
    return f"Rs. {value:,.2f}"


def render_statement_pdf(plan: FeePlan, *, institution_name: str, support_line: str = "") -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    enrollment = plan.enrollment
    student = enrollment.student
    name = student.user.full_name or student.user.email
    styles = getSampleStyleSheet()
    small = styles["BodyText"].clone("small", fontSize=8, leading=10)

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"Fee statement {enrollment.code}",
        author=institution_name,
    )

    grid = TableStyle(
        [
            ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F3F5")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C9CED6")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
    )

    story: list = [
        Paragraph(f"<b>{institution_name}</b>", styles["Title"]),
    ]
    if support_line:
        story.append(Paragraph(support_line, styles["Normal"]))
    story += [
        Spacer(1, 4 * mm),
        Paragraph("<b>FEE STATEMENT</b>", styles["Heading2"]),
        Paragraph(f"As of {timezone.localdate():%d %B %Y}", small),
        Spacer(1, 4 * mm),
    ]

    who = Table(
        [
            ["Student", name, "Student ID", student.student_id],
            ["Course", enrollment.course.title, "Enrolment", enrollment.code],
            [
                "Batch",
                f"{enrollment.batch.name} ({enrollment.batch.code})",
                "Email",
                student.user.email,
            ],
        ],
        colWidths=[24 * mm, 66 * mm, 24 * mm, 60 * mm],
    )
    who.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
                ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9),
                ("FONT", (2, 0), (2, -1), "Helvetica-Bold", 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story += [who, Spacer(1, 5 * mm)]

    if plan.discount_amount > 0:
        how = (
            f"{plan.discount_percent.normalize():f}% of the fee"
            if plan.discount_percent is not None
            else "flat"
        )
        discount_line = (
            f"{rupees(plan.discount_amount)} ({how}; {plan.discount_reason or 'no reason given'})"
        )
    else:
        discount_line = "None"
    figures = Table(
        [
            ["", "Amount"],
            ["Course fee", rupees(plan.agreed_amount)],
            ["Discount", discount_line],
            ["Payable", rupees(plan.payable)],
            ["Received so far", rupees(plan.paid)],
            ["Balance", rupees(plan.balance)],
        ],
        colWidths=[50 * mm, 124 * mm],
    )
    figures_style = TableStyle(grid.getCommands())
    figures_style.add("FONT", (0, 5), (-1, 5), "Helvetica-Bold", 9)
    figures.setStyle(figures_style)
    story += [figures, Spacer(1, 6 * mm)]

    rows = installment_rows(plan)
    if rows:
        story.append(Paragraph("<b>Instalment schedule</b>", styles["Heading4"]))
        schedule = Table(
            [["#", "Due by", "Amount", "Received", "Status"]]
            + [
                [
                    str(row["sequence"]),
                    f"{row['due_on']:%d %b %Y}",
                    rupees(row["amount"]),
                    rupees(row["paid_amount"]),
                    STATE_LABEL.get(row["status"], str(row["status"])),
                ]
                for row in rows
            ],
            colWidths=[10 * mm, 34 * mm, 44 * mm, 44 * mm, 42 * mm],
            repeatRows=1,
        )
        schedule.setStyle(grid)
        story += [schedule, Spacer(1, 6 * mm)]

    payments = list(plan.payments.order_by("paid_on", "created_at"))
    if payments:
        story.append(Paragraph("<b>Payments received</b>", styles["Heading4"]))
        paid_table = Table(
            [["Date", "Receipt", "Method", "Amount"]]
            + [
                [
                    f"{payment.paid_on:%d %b %Y}",
                    payment.receipt_number + (" (void)" if payment.is_voided else ""),
                    payment.get_method_display(),
                    rupees(payment.amount),
                ]
                for payment in payments
            ],
            colWidths=[34 * mm, 54 * mm, 42 * mm, 44 * mm],
            repeatRows=1,
        )
        paid_table.setStyle(grid)
        story += [paid_table, Spacer(1, 6 * mm)]

    story.append(
        Paragraph(
            "This is a statement of the fee agreed and the payments received, not a tax "
            f"invoice. Generated {timezone.localtime():%d %b %Y %H:%M}; computer-generated, "
            "no signature needed.",
            small,
        )
    )
    document.build(story)
    return buffer.getvalue()
