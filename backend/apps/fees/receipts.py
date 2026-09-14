"""The receipt a student is handed for a payment, as a PDF.

One page, A5, drawn directly with reportlab like the certificate is. The
institution's name comes from the settings an administrator maintains; the
figures come from the ledger and nowhere else. A voided payment still
renders — stamped VOID across it — because a receipt that was issued was
issued, and the void is part of its history.
"""

from __future__ import annotations

from io import BytesIO

from django.utils import timezone


def render_receipt_pdf(payment, *, institution_name: str, support_line: str = "") -> bytes:
    from reportlab.lib.pagesizes import A5
    from reportlab.pdfgen import canvas

    width, height = A5
    enrollment = payment.plan.enrollment
    student = enrollment.student
    plan = payment.plan

    buffer = BytesIO()
    page = canvas.Canvas(buffer, pagesize=A5)
    page.setTitle(f"Receipt {payment.receipt_number}")
    page.setAuthor(institution_name)

    page.setLineWidth(1)
    page.rect(20, 20, width - 40, height - 40)

    page.setFont("Helvetica-Bold", 16)
    page.drawCentredString(width / 2, height - 55, institution_name)
    page.setFont("Helvetica", 9)
    if support_line:
        page.drawCentredString(width / 2, height - 70, support_line)
    page.setFont("Helvetica-Bold", 12)
    page.drawCentredString(width / 2, height - 95, "FEE RECEIPT")

    left, top = 40, height - 125
    line = 16

    def row(index: int, label: str, value: str) -> None:
        y = top - index * line
        page.setFont("Helvetica", 9)
        page.drawString(left, y, label)
        page.setFont("Helvetica-Bold", 9)
        page.drawString(left + 110, y, value)

    name = student.user.full_name or student.user.email
    row(0, "Receipt number", payment.receipt_number)
    row(1, "Date", payment.paid_on.strftime("%d %B %Y"))
    row(2, "Received from", name)
    row(3, "Student ID", student.student_id)
    row(4, "Course", enrollment.course.title)
    row(5, "Batch", f"{enrollment.batch.name} ({enrollment.batch.code})")
    row(6, "Amount", f"Rs. {payment.amount:,.2f}")
    row(7, "Paid by", payment.get_method_display())
    if payment.reference:
        row(8, "Reference", payment.reference)
    row(9, "Received by", payment.recorded_by.full_name if payment.recorded_by else "")

    page.setLineWidth(0.5)
    page.line(left, top - 10 * line, width - 40, top - 10 * line)
    page.setFont("Helvetica", 9)
    page.drawString(left, top - 11 * line, "Fee agreed")
    page.drawString(left, top - 12 * line, "Paid so far")
    page.drawString(left, top - 13 * line, "Balance")
    page.setFont("Helvetica-Bold", 9)
    page.drawRightString(width - 40, top - 11 * line, f"Rs. {plan.payable:,.2f}")
    page.drawRightString(width - 40, top - 12 * line, f"Rs. {plan.paid:,.2f}")
    page.drawRightString(width - 40, top - 13 * line, f"Rs. {plan.balance:,.2f}")

    if payment.is_voided:
        page.saveState()
        page.setFont("Helvetica-Bold", 48)
        page.setFillGray(0.75)
        page.translate(width / 2, height / 2)
        page.rotate(30)
        page.drawCentredString(0, 0, "VOID")
        page.restoreState()
        page.setFont("Helvetica", 8)
        page.drawString(left, 50, f"Voided: {payment.void_reason}")

    page.setFont("Helvetica-Oblique", 7)
    page.drawString(
        left,
        34,
        f"Generated {timezone.localtime():%d %b %Y %H:%M}. Computer-generated; no signature.",
    )
    page.showPage()
    page.save()
    return buffer.getvalue()
