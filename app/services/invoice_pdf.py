import io
from flask import current_app
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer


def invoice_pdf(inv):
    cfg = current_app.config
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=28, rightMargin=28, topMargin=28, bottomMargin=28)
    st = getSampleStyleSheet()
    c = inv.customer
    story = [Paragraph(f"TAX INVOICE{' (CANCELLED)' if inv.status == 'CANCELLED' else ''}", st["Title"]),
             Paragraph(f"<b>{cfg['COMPANY_NAME']}</b><br/>{cfg['COMPANY_ADDRESS']}<br/>GSTIN: {cfg['COMPANY_GSTIN']}", st["Normal"]),
             Spacer(1, 8),
             Paragraph(f"<b>Invoice No:</b> {inv.invoice_no} &nbsp;&nbsp; <b>Date:</b> {inv.invoice_date:%d-%m-%Y}", st["Normal"]),
             Paragraph(f"<b>Bill To:</b> {c.name}, {c.address or ''}<br/>State: {c.state} &nbsp; GSTIN: {c.gstin or 'N/A (unregistered)'}", st["Normal"]),
             Spacer(1, 10)]
    head = ["#", "Description", "HSN", "Qty", "Rate", "Taxable", "GST%", "CGST", "SGST", "IGST"]
    rows = [head]
    for i, it in enumerate(inv.items, 1):
        rows.append([i, it.product.name, it.hsn or "", f"{it.qty:.0f}", f"{it.price:.2f}", f"{it.taxable:.2f}",
                     f"{it.gst_rate:.0f}", f"{it.cgst:.2f}", f"{it.sgst:.2f}", f"{it.igst:.2f}"])
    rows.append(["", "TOTAL", "", "", "", f"{inv.taxable:.2f}", "", f"{inv.cgst:.2f}", f"{inv.sgst:.2f}", f"{inv.igst:.2f}"])
    t = Table(rows, repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3a5f")),
                           ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 8),
                           ("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold")]))
    story += [t, Spacer(1, 10), Paragraph(f"<b>Invoice Total: Rs. {inv.total:.2f}</b>", st["Heading3"]),
              Paragraph("Computer generated invoice. Goods dispatched separately (see dispatch record).", st["Italic"])]
    doc.build(story)
    return buf.getvalue()
