"""Stock ledger service. All stock changes go through post()."""
from datetime import date, datetime
from ..extensions import db
from ..models import Item, StockLedger, Purchase, PurchaseItem, audit
from ..utils import D, q3, q4


class InsufficientStock(Exception):
    def __init__(self, item, needed, available):
        self.item, self.needed, self.available = item, needed, available
        super().__init__(f"Insufficient stock for {item.name}: need {needed} {item.unit}, available {available}")


def post(item, txn_type, qty_in=0, qty_out=0, doc_type=None, doc_id=None, user_id=None,
         unit_cost=None, note="", when=None):
    """Add one ledger row. Refuses to let stock go negative."""
    qty_in, qty_out = q3(qty_in), q3(qty_out)
    if qty_in < 0 or qty_out < 0:
        raise ValueError("Quantities must be positive")
    if qty_out > 0:
        avail = item.stock
        if avail < qty_out:
            raise InsufficientStock(item, qty_out, avail)
    row = StockLedger(item_id=item.id, txn_type=txn_type, qty_in=qty_in, qty_out=qty_out,
                      unit_cost=q4(item.avg_cost if unit_cost is None else unit_cost),
                      doc_type=doc_type, doc_id=doc_id, user_id=user_id, note=note,
                      txn_date=when or datetime.utcnow())
    db.session.add(row)
    db.session.flush()
    return row


def receive_purchase(supplier_id, lines, user_id, when=None):
    """lines = [(item_id, qty, rate)]. Updates weighted-average cost and writes ledger rows."""
    if not lines:
        raise ValueError("Add at least one purchase line")
    try:
        pur = Purchase(supplier_id=supplier_id, user_id=user_id, date=when or date.today())
        db.session.add(pur)
        db.session.flush()
        for item_id, qty, rate in lines:
            item, qty, rate = db.session.get(Item, int(item_id)), D(qty), D(rate)
            if qty <= 0 or rate < 0:
                raise ValueError("Quantity must be > 0 and rate >= 0")
            old_qty = item.stock
            # Weighted average = (old value + new value) / (old qty + new qty)
            item.avg_cost = q4((old_qty * D(item.avg_cost) + qty * rate) / (old_qty + qty))
            db.session.add(PurchaseItem(purchase_id=pur.id, item_id=item.id, qty=qty, rate=rate))
            post(item, "PURCHASE", qty_in=qty, doc_type="purchase", doc_id=pur.id, user_id=user_id,
                 unit_cost=rate)
        audit(user_id, "PURCHASE", f"Purchase #{pur.id}")
        db.session.commit()
        return pur
    except Exception:
        db.session.rollback()
        raise


def adjust(item_id, delta, reason, user_id):
    """Traceable manual correction (+/-). Reason is mandatory."""
    if not reason or not reason.strip():
        raise ValueError("Reason is required for stock adjustment")
    item, delta = db.session.get(Item, int(item_id)), D(delta)
    try:
        if delta > 0:
            post(item, "ADJUSTMENT", qty_in=delta, doc_type="adjustment", user_id=user_id, note=reason)
        elif delta < 0:
            post(item, "ADJUSTMENT", qty_out=-delta, doc_type="adjustment", user_id=user_id, note=reason)
        else:
            raise ValueError("Adjustment cannot be zero")
        audit(user_id, "ADJUSTMENT", f"{item.code} {delta}: {reason}")
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def low_stock_items():
    return [i for i in Item.query.order_by(Item.name).all() if i.low]
