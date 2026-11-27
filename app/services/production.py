"""BOM based production engine: material issue, output, variance and costing."""
from datetime import date
from flask import current_app
from ..extensions import db
from ..models import (Product, Bom, BomItem, Item, ProductionRun, ProductionMaterial, Expense, audit)
from ..utils import D, q3, q4, money, convert, POUCH_CODE
from . import inventory


def planned_lines(bom, batches):
    """Expected consumption per BOM line, converted to the inventory item's unit."""
    return [(bi, q3(convert(D(bi.qty) * D(batches), bi.unit, bi.item.unit))) for bi in bom.items]


def create_bom_version(product_id, expected_output, lines, user_id):
    """lines = [(item_id, qty, unit)]. Old versions are kept (inactive) so old runs keep their BOM."""
    product = db.session.get(Product, product_id)
    try:
        for b in product.boms:
            b.is_active = False
        version = (max([b.version for b in product.boms]) + 1) if product.boms else 1
        bom = Bom(product_id=product_id, version=version, expected_output=D(expected_output), is_active=True)
        db.session.add(bom)
        db.session.flush()
        for item_id, qty, unit in lines:
            db.session.add(BomItem(bom_id=bom.id, item_id=item_id, qty=D(qty), unit=unit))
        audit(user_id, "BOM_VERSION", f"{product.code} v{version}")
        db.session.commit()
        return bom
    except Exception:
        db.session.rollback()
        raise


def run_production(product_id, bom_id, batches, actuals, good_output, damaged_pouches, user_id, when=None):
    """
    actuals = {item_id: actual qty (in item unit)}; missing items default to planned.
    Pouch consumption is always good output + damaged pouches (every packet used one pouch).
    Everything happens in one DB transaction: if any stock is short, nothing is saved.
    """
    product, bom = db.session.get(Product, product_id), db.session.get(Bom, bom_id)
    if not product or not bom or bom.product_id != product.id:
        raise ValueError("BOM does not belong to the selected product")
    batches, good, damaged = D(batches), D(good_output), D(damaged_pouches)
    if batches <= 0 or good < 0 or damaged < 0:
        raise ValueError("Invalid quantities")
    when = when or date.today()
    try:
        run = ProductionRun(product_id=product.id, bom_id=bom.id, batches=batches,
                            expected_output=D(bom.expected_output) * batches, actual_output=good,
                            damaged_pouches=damaged, run_date=when, user_id=user_id)
        db.session.add(run)
        db.session.flush()
        run.batch_no = f"B{when:%Y%m%d}-{run.id:04d}"
        for bi, planned in planned_lines(bom, batches):
            item = bi.item
            actual = good + damaged if item.code == POUCH_CODE else D(actuals.get(bi.item_id, planned))
            cost = D(item.avg_cost)
            inventory.post(item, "PRODUCTION_ISSUE", qty_out=actual, doc_type="production_run",
                           doc_id=run.id, user_id=user_id, unit_cost=cost, when=None)
            db.session.add(ProductionMaterial(run_id=run.id, item_id=item.id, planned_qty=planned,
                                              actual_qty=q3(actual), unit_cost=cost))
        db.session.flush()
        if good > 0:
            inventory.post(product.item, "PRODUCTION_OUTPUT", qty_in=good, doc_type="production_run",
                           doc_id=run.id, user_id=user_id)
        db.session.flush()
        recompute_cost(run)
        audit(user_id, "PRODUCTION", f"{run.batch_no} output {good}")
        db.session.commit()
        return run
    except Exception:
        db.session.rollback()
        raise


def recompute_cost(run):
    """Cost = materials at weighted-average cost at time of issue + overheads recorded for the run."""
    db.session.refresh(run)
    rm = pk = D(0)
    for m in run.materials:
        c = D(m.actual_qty) * D(m.unit_cost)
        if m.item.kind == "RAW":
            rm += c
        else:
            pk += c
    exp = {"LABOUR": D(0), "POWER": D(0), "OTHER": D(0)}
    for e in Expense.query.filter_by(run_id=run.id).all():
        exp[e.kind] += D(e.amount)
    run.rm_cost, run.pack_cost = money(rm), money(pk)
    run.labour_cost, run.power_cost, run.other_cost = money(exp["LABOUR"]), money(exp["POWER"]), money(exp["OTHER"])
    run.total_cost = run.rm_cost + run.pack_cost + run.labour_cost + run.power_cost + run.other_cost
    run.cost_per_packet = q4(D(run.total_cost) / D(run.actual_output)) if D(run.actual_output) > 0 else D(0)


def add_expense(run_id, kind, amount, user_id):
    kind = kind.upper()
    if kind not in ("LABOUR", "POWER", "OTHER"):
        raise ValueError("Unknown expense type")
    amount = D(amount)
    if amount <= 0:
        raise ValueError("Amount must be positive")
    try:
        db.session.add(Expense(run_id=run_id, kind=kind, amount=amount, user_id=user_id))
        db.session.flush()
        run = db.session.get(ProductionRun, run_id)
        recompute_cost(run)
        audit(user_id, "EXPENSE", f"run {run_id} {kind} {amount}")
        db.session.commit()
        return run
    except Exception:
        db.session.rollback()
        raise


def tolerance():
    return D(current_app.config["VARIANCE_TOLERANCE"])


def variance_rows(run):
    tol = tolerance()
    rows = []
    for m in run.materials:
        rows.append(dict(item=m.item.name, unit=m.item.unit, planned=D(m.planned_qty), actual=D(m.actual_qty),
                         diff=m.diff, pct=m.var_pct, flag=abs(m.var_pct) > tol))
    return rows


def yield_flag(run):
    return abs(run.yield_variance_pct) > tolerance()
