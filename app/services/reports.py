"""14 reports. Each returns (title, headers, rows) so one exporter handles CSV / Excel / PDF."""
from collections import defaultdict
from datetime import date
from ..models import (Invoice, Purchase, Item, StockLedger, ProductionRun, Payment, Customer)
from ..utils import D, money, q3
from .production import variance_rows, tolerance


def _in(d, start, end):
    if hasattr(d, "date"):  # datetime -> date
        d = d.date()
    return (not start or d >= start) and (not end or d <= end)


def _invoices(start, end):
    return [i for i in Invoice.query.filter_by(status="POSTED").order_by(Invoice.invoice_date).all()
            if _in(i.invoice_date, start, end)]


def sales_register(s, e):
    rows = [(i.invoice_no, i.invoice_date, i.customer.name, i.taxable, i.cgst, i.sgst, i.igst, i.total) for i in _invoices(s, e)]
    return "Sales Register", ["Invoice", "Date", "Customer", "Taxable", "CGST", "SGST", "IGST", "Total"], rows


def customer_sales(s, e):
    agg = defaultdict(lambda: [D(0), D(0)])
    for i in _invoices(s, e):
        agg[i.customer.name][0] += D(i.taxable)
        agg[i.customer.name][1] += D(i.total)
    return "Customer-wise Sales", ["Customer", "Taxable", "Total"], [(k, *v) for k, v in agg.items()]


def product_sales(s, e):
    agg = defaultdict(lambda: [D(0), D(0)])
    for i in _invoices(s, e):
        for it in i.items:
            agg[it.product.name][0] += D(it.qty)
            agg[it.product.name][1] += D(it.taxable)
    return "Product-wise Sales", ["Product", "Qty", "Taxable"], [(k, *v) for k, v in agg.items()]


def gst_summary(s, e):
    agg = defaultdict(lambda: [D(0)] * 4)
    for i in _invoices(s, e):
        for it in i.items:
            a = agg[str(it.gst_rate)]
            agg[str(it.gst_rate)] = [a[0] + D(it.taxable), a[1] + D(it.cgst), a[2] + D(it.sgst), a[3] + D(it.igst)]
    rows = [(k + "%", v[0], v[1], v[2], v[3], v[0] + v[1] + v[2] + v[3]) for k, v in agg.items()]
    return "GST Outward Supply Summary", ["GST Rate", "Taxable", "CGST", "SGST", "IGST", "Total"], rows


def purchase_register(s, e):
    rows = []
    for p in Purchase.query.order_by(Purchase.date).all():
        if _in(p.date, s, e):
            for it in p.items:
                rows.append((p.id, p.date, p.supplier.name, it.item.name, it.qty, it.item.unit, it.rate, money(D(it.qty) * D(it.rate))))
    return "Purchase Register", ["Purchase", "Date", "Supplier", "Item", "Qty", "Unit", "Rate", "Amount"], rows


def stock_summary(s=None, e=None):
    rows = [(i.code, i.name, i.kind, i.stock, i.unit, i.avg_cost, money(i.stock * D(i.avg_cost)), "LOW" if i.low else "")
            for i in Item.query.order_by(Item.kind, Item.name).all()]
    return "Stock Summary", ["Code", "Item", "Type", "Stock", "Unit", "Avg Cost", "Value", "Alert"], rows


def stock_ledger(s, e):
    rows = []
    for l in StockLedger.query.order_by(StockLedger.id).all():
        if _in(l.txn_date, s, e):
            rows.append((l.id, l.txn_date.strftime("%Y-%m-%d %H:%M"), l.item.name, l.txn_type, l.qty_in, l.qty_out,
                         l.doc_type or "", l.doc_id or "", l.user.username if l.user else "", l.note or ""))
    return "Stock Ledger", ["ID", "Date", "Item", "Type", "In", "Out", "Doc", "Doc ID", "User", "Note"], rows


def _runs(s, e):
    return [r for r in ProductionRun.query.order_by(ProductionRun.id).all() if _in(r.run_date, s, e)]


def production_report(s, e):
    rows = [(r.batch_no, r.run_date, r.product.name, r.bom.version, r.expected_output, r.actual_output,
             f"{r.yield_variance_pct:.2f}%", r.damaged_pouches) for r in _runs(s, e)]
    return "Production Report", ["Batch", "Date", "Product", "BOM v", "Expected", "Actual", "Yield Var", "Damaged Pouches"], rows


def variance_report(s, e):
    rows = []
    for r in _runs(s, e):
        for v in variance_rows(r):
            rows.append((r.batch_no, v["item"], v["unit"], v["planned"], v["actual"], v["diff"], f"{v['pct']:.2f}%", "FLAG" if v["flag"] else "OK"))
    return "Planned vs Actual Variance", ["Batch", "Material", "Unit", "Planned", "Actual", "Diff", "Var %", "Status"], rows


def wastage_report(s, e):
    rows = []
    for r in _runs(s, e):
        excess = sum((m.diff * D(m.unit_cost) for m in r.materials if m.diff > 0), D(0))
        rows.append((r.batch_no, r.product.name, r.damaged_pouches, D(r.expected_output) - D(r.actual_output), money(excess)))
    return "Wastage Report", ["Batch", "Product", "Damaged Pouches", "Packets Short of Plan", "Excess Material Cost"], rows


def cost_report(s, e):
    rows = [(r.batch_no, r.product.name, r.rm_cost, r.pack_cost, r.labour_cost, r.power_cost, r.other_cost, r.total_cost,
             r.actual_output, f"{D(r.cost_per_packet):.2f}", r.product.price, f"{D(r.product.price) - D(r.cost_per_packet):.2f}")
            for r in _runs(s, e)]
    return "Cost per Packet", ["Batch", "Product", "RM", "Packaging", "Labour", "Power", "Other", "Total", "Good Pkts", "Cost/Pkt", "Price", "Margin/Pkt"], rows


def collections(s, e):
    rows = [(p.id, p.pay_date, p.customer.name, p.mode, p.amount, p.unallocated) for p in Payment.query.order_by(Payment.pay_date).all() if _in(p.pay_date, s, e)]
    return "Payment and Collection", ["Payment", "Date", "Customer", "Mode", "Amount", "Unallocated"], rows


def outstanding(s=None, e=None):
    agg = defaultdict(lambda: [D(0), D(0)])
    for i in Invoice.query.filter_by(status="POSTED").all():
        agg[i.customer.name][0] += D(i.total)
        agg[i.customer.name][1] += i.balance
    rows = [(k, v[0], v[0] - v[1], v[1]) for k, v in agg.items()]
    return "Customer Outstanding", ["Customer", "Invoiced", "Paid", "Outstanding"], rows


def ageing(s=None, e=None):
    today = date.today()
    agg = defaultdict(lambda: [D(0)] * 4)
    for i in Invoice.query.filter_by(status="POSTED").all():
        if i.balance <= 0:
            continue
        age = (today - i.invoice_date).days
        b = 0 if age <= 30 else 1 if age <= 60 else 2 if age <= 90 else 3
        a = list(agg[i.customer.name])
        a[b] += i.balance
        agg[i.customer.name] = a
    rows = [(k, *v, sum(v, D(0))) for k, v in agg.items()]
    return "Outstanding Ageing", ["Customer", "0-30 days", "31-60", "61-90", "90+", "Total"], rows


REPORTS = {
    "sales-register": sales_register, "customer-sales": customer_sales, "product-sales": product_sales,
    "gst-summary": gst_summary, "purchase-register": purchase_register, "stock-summary": stock_summary,
    "stock-ledger": stock_ledger, "production": production_report, "variance": variance_report,
    "wastage": wastage_report, "cost-per-packet": cost_report, "collections": collections,
    "outstanding": outstanding, "ageing": ageing,
}
