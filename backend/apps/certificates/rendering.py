"""Drawing the certificate PDF and its QR code.

reportlab draws the page directly rather than going through HTML. A certificate
is a fixed layout, and rendering it with a browser engine would add a large
native dependency and a full HTML parser to the attack surface of a document
built from user-editable text — for the sake of letting somebody centre a
heading.

Nothing here touches the database or decides anything. It takes values and
returns bytes, which is what makes it testable without a certificate.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any

#: A4 landscape, in points.
PAGE_WIDTH = 841.89
PAGE_HEIGHT = 595.28


def verification_url(code: str) -> str:
    """Where a QR code points. Absolute, because it is scanned off paper."""
    from django.conf import settings

    base = str(getattr(settings, "FRONTEND_BASE_URL", "")).rstrip("/")
    return f"{base}/verify/{code}"


def qr_png(payload: str, *, box_size: int = 4) -> bytes:
    """A QR code as PNG bytes."""
    import qrcode

    code = qrcode.QRCode(box_size=box_size, border=1)
    code.add_data(payload)
    code.make(fit=True)
    image = code.make_image(fill_color="black", back_color="white")

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _fill(template_body: str, values: dict[str, Any]) -> str:
    """Substitute placeholders, leaving unknown ones visible rather than raising.

    A template is validated when it is saved, so an unknown placeholder here
    means the allowlist changed under an existing template. Printing
    ``{whatever}`` on the certificate is wrong but obvious; raising would mean a
    student cannot download a certificate that has already been issued.
    """
    out = template_body
    for key, value in values.items():
        out = out.replace("{" + key + "}", str(value))
    return out


def render_certificate_pdf(*, certificate, template) -> bytes:
    """Draw one certificate. Returns the PDF bytes."""
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    values = {
        "student_name": certificate.student_name,
        "course_title": certificate.course_title,
        "completion_date": certificate.completion_date.strftime("%d %B %Y"),
        "certificate_number": certificate.number,
        "batch_code": certificate.batch_code,
        "institution_name": template.institution_name,
    }

    buffer = BytesIO()
    page = canvas.Canvas(buffer, pagesize=(PAGE_WIDTH, PAGE_HEIGHT))
    page.setTitle(f"{template.title} — {certificate.number}")
    page.setAuthor(template.institution_name)

    # Border
    page.setLineWidth(3)
    page.rect(28, 28, PAGE_WIDTH - 56, PAGE_HEIGHT - 56)
    page.setLineWidth(0.75)
    page.rect(38, 38, PAGE_WIDTH - 76, PAGE_HEIGHT - 76)

    centre = PAGE_WIDTH / 2

    page.setFont("Helvetica-Bold", 20)
    page.drawCentredString(centre, PAGE_HEIGHT - 100, template.institution_name)

    page.setFont("Helvetica-Bold", 30)
    page.drawCentredString(centre, PAGE_HEIGHT - 155, template.title)

    page.setFont("Helvetica", 14)
    text_top = PAGE_HEIGHT - 230
    for index, line in enumerate(_wrap(_fill(template.body, values), 78)):
        page.drawCentredString(centre, text_top - index * 22, line)

    page.setFont("Helvetica-Bold", 24)
    page.drawCentredString(centre, PAGE_HEIGHT - 200, certificate.student_name)

    # Signature block
    page.setFont("Helvetica", 11)
    if template.signatory_name:
        page.line(110, 130, 320, 130)
        page.drawCentredString(215, 114, template.signatory_name)
        if template.signatory_title:
            page.setFont("Helvetica-Oblique", 9)
            page.drawCentredString(215, 101, template.signatory_title)

    # Identifiers
    page.setFont("Helvetica", 10)
    page.drawString(60, 62, f"Certificate number: {certificate.number}")
    page.drawString(60, 48, f"Issued: {certificate.issued_at.strftime('%d %B %Y')}")

    # The QR, bottom right, with the code printed under it so a certificate is
    # still checkable when the scan fails or the page is photocopied.
    url = verification_url(certificate.verification_code)
    image = ImageReader(BytesIO(qr_png(url)))
    page.drawImage(image, PAGE_WIDTH - 170, 60, width=104, height=104, mask="auto")
    page.setFont("Helvetica", 7)
    page.drawCentredString(PAGE_WIDTH - 118, 50, certificate.verification_code)

    if template.footer:
        page.setFont("Helvetica-Oblique", 9)
        page.drawCentredString(centre, 175, template.footer)

    if certificate.status != "issued":
        # A superseded or revoked copy must not read as a valid claim.
        page.saveState()
        page.setFont("Helvetica-Bold", 72)
        page.setFillGray(0.85)
        page.translate(centre, PAGE_HEIGHT / 2)
        page.rotate(30)
        page.drawCentredString(0, 0, certificate.get_status_display().upper())
        page.restoreState()

    page.showPage()
    page.save()
    return buffer.getvalue()


def _wrap(text: str, width: int) -> list[str]:
    """Greedy wrap. reportlab has no layout engine on a bare canvas."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines
