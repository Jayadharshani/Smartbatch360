"""Recommendations, anomaly detection (rule based), loss impact and the audit assistant."""
import math
import re
from collections import Counter
from ..models import Product, Order, ProductionRun, Item, Customer
from ..utils import D, money, q3
from .production import variance_rows, tolerance, planned_lines
from . import reports
from .sales import customer_outstanding

OPEN_STATUSES = ("SUBMITTED", "APPROVED", "INVOICED", "PARTIALLY_DISPATCHED")


def recommend_production():
    out = []
    for p in Product.query.filter_by(active=True).all():
        bom = p.active_bom
        if not bom:
            continue
        pending = D(0)
        for o in Order.query.filter(Order.status.in_(OPEN_STATUSES)).all():
            for it in o.items:
                if it.product_id == p.id:
                    pending += D(it.qty) - D(it.dispatched_qty)
        stock = p.item.stock
        shortfall = max(D(0), pending - stock)
        batches = math.ceil(shortfall / D(bom.expected_output)) if shortfall > 0 else 0
        mats = []
        for bi, planned in planned_lines(bom, batches):
            need = planned
            mats.append(dict(item=bi.item.name, unit=bi.item.unit, need=need, have=bi.item.stock, ok=bi.item.stock >= need))
        out.append(dict(product=p.name, pending=pending, stock=stock, shortfall=shortfall, batches=batches,
                        materials=mats, can_produce=all(m["ok"] for m in mats)))
    return out


def anomalies():
    """Rule based: any run whose material or yield variance exceeds the tolerance; plus repeat offenders."""
    tol, found, repeats = tolerance(), [], Counter()
    for r in ProductionRun.query.order_by(ProductionRun.id).all():
        for v in variance_rows(r):
            if v["pct"] > tol:  # over-consumption
                found.append(dict(batch=r.batch_no, kind="High consumption", detail=f"{v['item']} {v['pct']:.1f}% above plan"))
                repeats[v["item"]] += 1
        if r.yield_variance_pct < -tol:
            found.append(dict(batch=r.batch_no, kind="Low yield", detail=f"Yield {r.yield_variance_pct:.1f}% vs expected"))
            repeats["YIELD"] += 1
        if D(r.damaged_pouches) > 0 and D(r.actual_output) > 0 and D(r.damaged_pouches) / D(r.actual_output) * 100 > tol:
            found.append(dict(batch=r.batch_no, kind="High packaging wastage", detail=f"{r.damaged_pouches} damaged pouches"))
    rep = [dict(item=k, count=c) for k, c in repeats.items() if c >= 2]
    return found, rep


def loss_impact():
    rows, total = [], D(0)
    for r in ProductionRun.query.order_by(ProductionRun.id).all():
        excess = [(m.item.name, m.diff, m.diff * D(m.unit_cost)) for m in r.materials if m.diff > 0]
        cost = money(sum((x[2] for x in excess), D(0)))
        short = max(D(0), D(r.expected_output) - D(r.actual_output))
        rows.append(dict(batch=r.batch_no, excess=excess, excess_cost=cost, yield_short=short,
                         yield_loss=money(short * D(r.cost_per_packet))))
        total += cost
    return rows, money(total)


def answer(question):
    """Keyword based assistant. Every number comes from a database query, nothing is generated."""
    q = question.lower()
    items = Item.query.all()
    for it in items:
        if it.name.lower() in q or it.code.lower() in q or it.name.lower().split()[0] in q:
            if "stock" in q or "how much" in q:
                return f"Current stock of {it.name}: {it.stock} {it.unit} (from stock ledger)."
    if "wastage" in q and "highest" in q:
        best = None
        for p in Product.query.all():
            runs = ProductionRun.query.filter_by(product_id=p.id).all()
            w = sum((D(r.damaged_pouches) for r in runs), D(0))
            if runs and (best is None or w > best[1]):
                best = (p.name, w)
        return f"{best[0]} has the highest recorded damaged-pouch wastage: {best[1]} pouches." if best else "No production runs yet."
    if "cost" in q:
        for p in Product.query.all():
            if p.name.lower().split()[0] in q:
                r = ProductionRun.query.filter_by(product_id=p.id).order_by(ProductionRun.id.desc()).first()
                if r:
                    return f"Latest cost per {p.name} packet: Rs. {D(r.cost_per_packet):.2f} (batch {r.batch_no}, total cost Rs. {r.total_cost})."
        return "No production run found for that product."
    if "pending" in q or "outstanding" in q or "owe" in q:
        lst = [(c.name, customer_outstanding(c.id)) for c in Customer.query.all()]
        lst = [x for x in lst if x[1] > 0]
        return "Pending payments: " + "; ".join(f"{n}: Rs. {a}" for n, a in lst) if lst else "No pending payments."
    if "produce" in q or "how many packets" in q:
        recs = recommend_production()
        return " | ".join(f"{r['product']}: produce {r['shortfall']} packets ({r['batches']} batch(es))" for r in recs) or "No products."
    return "I can answer: current stock of an item, highest wastage, cost per product packet, pending customer payments, and how many packets to produce."
