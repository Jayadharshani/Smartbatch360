"""CSV / Excel / PDF export of any (title, headers, rows) table."""
import csv
import io
from flask import Response
from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer


def _s(v):
    return "" if v is None else str(v)


def export(title, headers, rows, fmt):
    slug = title.lower().replace(" ", "_")
    if fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(headers)
        w.writerows([[_s(c) for c in r] for r in rows])
        return Response(buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": f"attachment; filename={slug}.csv"})
    if fmt == "xlsx":
        wb = Workbook()
        ws = wb.active
        ws.title = title[:30]
        ws.append(headers)
        for r in rows:
            ws.append([float(c) if hasattr(c, "quantize") else c for c in r])
        buf = io.BytesIO()
        wb.save(buf)
        return Response(buf.getvalue(), mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f"attachment; filename={slug}.xlsx"})
    if fmt == "pdf":
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24)
        st = getSampleStyleSheet()
        data = [headers] + [[_s(c) for c in r] for r in rows]
        t = Table(data, repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3a5f")),
                               ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 7),
                               ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f5fa")])]))
        doc.build([Paragraph(title, st["Title"]), Spacer(1, 8), t])
        return Response(buf.getvalue(), mimetype="application/pdf",
                        headers={"Content-Disposition": f"attachment; filename={slug}.pdf"})
    raise ValueError("Unknown format")
