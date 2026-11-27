"""Orders, GST invoices, dispatch, payments."""
from datetime import date, datetime
from flask import current_app
from ..extensions import db
from ..models import (Order, OrderItem, Product, Customer, Invoice, InvoiceItem, Dispatch, DispatchItem,
                      Payment, PaymentAllocation, audit)
from ..utils import D, q3, money, financial_year
from . import inventory
from .inventory import InsufficientStock


def create_order(salesman_id, customer_id, lines):
    """lines = [(product_id, qty)]; price is taken from the product master."""
    lines = [(int(p), D(q)) for p, q in lines if D(q) > 0]
    if not lines:
        raise ValueError("Enter a quantity for at least one product")
    try:
        order = Order(customer_id=customer_id, salesman_id=salesman_id)
        db.session.add(order)
        db.session.flush()
        order.order_no = f"ORD-{order.id:05d}"
        for pid, qty in lines:
            p = db.session.get(Product, pid)
            db.session.add(OrderItem(order_id=order.id, product_id=pid, qty=qty, price=p.price))
        audit(salesman_id, "ORDER_CREATE", order.order_no)
        db.session.commit()
        return order
    except Exception:
        db.session.rollback()
        raise


def _order(order_id):
    return db.session.get(Order, order_id)


def edit_order(order_id, changes, user_id):
    """changes = {order_item_id: (qty, price)}. Allowed only before invoicing; logged in audit_logs."""
    order = _order(order_id)
    if order.status not in ("SUBMITTED", "APPROVED"):
        raise ValueError("Order can no longer be edited")
    try:
        for it in order.items:
            if it.id in changes:
                qty, price = D(changes[it.id][0]), D(changes[it.id][1])
                if qty < 0 or price < 0:
                    raise ValueError("Negative values not allowed")
                audit(user_id, "ORDER_EDIT", f"{order.order_no} {it.product.code}: qty {it.qty}->{qty}, price {it.price}->{price}")
                it.qty, it.price = qty, price
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def set_status(order_id, new_status, user_id):
    order = _order(order_id)
    if new_status == "APPROVED" and order.status != "SUBMITTED":
        raise ValueError("Only submitted orders can be approved")
    if new_status == "REJECTED" and order.status not in ("SUBMITTED", "APPROVED"):
        raise ValueError("This order cannot be rejected")
    order.status = new_status
    audit(user_id, f"ORDER_{new_status}", order.order_no)
    db.session.commit()
    return order


def stock_check(order):
    """Per product: remaining qty to dispatch, available finished stock, shortage."""
    out = []
    for it in order.items:
        remaining = D(it.qty) - D(it.dispatched_qty)
        avail = it.product.item.stock
        out.append(dict(product=it.product.name, remaining=remaining, available=avail,
                        shortage=max(D(0), remaining - avail)))
    return out


def next_invoice_no(d):
    fy = financial_year(d)
    n = Invoice.query.filter(Invoice.invoice_no.like(f"SB/{fy}/%")).count() + 1
    return f"SB/{fy}/{n:04d}"


def generate_invoice(order_id, user_id, when=None):
    """GST invoice. Intra-state -> CGST+SGST, inter-state -> IGST. Does NOT touch stock."""
    order = _order(order_id)
    if order.status != "APPROVED" or order.invoice:
        raise ValueError("Only approved orders without an invoice can be invoiced")
    when = when or date.today()
    intra = order.customer.state.strip().lower() == current_app.config["COMPANY_STATE"].strip().lower()
    try:
        inv = Invoice(invoice_no=next_invoice_no(when), order_id=order.id, customer_id=order.customer_id,
                      invoice_date=when)
        db.session.add(inv)
        db.session.flush()
        tot = dict(taxable=D(0), cgst=D(0), sgst=D(0), igst=D(0))
        for it in order.items:
            if D(it.qty) <= 0:
                continue
            taxable = money(D(it.qty) * D(it.price))
            tax = money(taxable * D(it.product.gst_rate) / 100)
            cgst = sgst = igst = D(0)
            if intra:
                cgst = money(tax / 2)
                sgst = tax - cgst
            else:
                igst = tax
            db.session.add(InvoiceItem(invoice_id=inv.id, product_id=it.product_id, qty=it.qty, price=it.price,
                                       gst_rate=it.product.gst_rate, hsn=it.product.hsn, taxable=taxable,
                                       cgst=cgst, sgst=sgst, igst=igst))
            for k, v in (("taxable", taxable), ("cgst", cgst), ("sgst", sgst), ("igst", igst)):
                tot[k] += v
        inv.taxable, inv.cgst, inv.sgst, inv.igst = tot["taxable"], tot["cgst"], tot["sgst"], tot["igst"]
        inv.total = tot["taxable"] + tot["cgst"] + tot["sgst"] + tot["igst"]
        order.status = "INVOICED"
        audit(user_id, "INVOICE", inv.invoice_no)
        db.session.commit()
        return inv
    except Exception:
        db.session.rollback()
        raise


def cancel_invoice(invoice_id, reason, user_id):
    inv = db.session.get(Invoice, invoice_id)
    if inv.status == "CANCELLED":
        raise ValueError("Already cancelled")
    if inv.paid > 0 or any(D(i.dispatched_qty) > 0 for i in inv.items):
        raise ValueError("Cannot cancel: payments or dispatches exist (issue a credit note instead)")
    if not reason.strip():
        raise ValueError("Reason required")
    inv.status = "CANCELLED"
    inv.order.status = "APPROVED"  # order can be re-invoiced after correction
    audit(user_id, "INVOICE_CANCEL", f"{inv.invoice_no}: {reason}")
    db.session.commit()


def dispatch(invoice_id, qtys, user_id):
    """qtys = {product_id: qty}. Supports partial dispatch. Reduces finished goods stock."""
    inv = db.session.get(Invoice, invoice_id)
    if inv.status != "POSTED":
        raise ValueError("Invoice is cancelled")
    try:
        d = Dispatch(invoice_id=inv.id, user_id=user_id)
        db.session.add(d)
        db.session.flush()
        any_qty = False
        for line in inv.items:
            qty = D(qtys.get(line.product_id, 0))
            if qty <= 0:
                continue
            if qty > D(line.qty) - D(line.dispatched_qty):
                raise ValueError(f"{line.product.name}: cannot dispatch more than the remaining invoice quantity")
            inventory.post(line.product.item, "DISPATCH", qty_out=qty, doc_type="dispatch", doc_id=d.id,
                           user_id=user_id)  # raises InsufficientStock if short
            line.dispatched_qty = D(line.dispatched_qty) + qty
            db.session.add(DispatchItem(dispatch_id=d.id, product_id=line.product_id, qty=qty))
            for oi in inv.order.items:
                if oi.product_id == line.product_id:
                    oi.dispatched_qty = D(oi.dispatched_qty) + qty
            any_qty = True
        if not any_qty:
            raise ValueError("Enter a dispatch quantity")
        full = all(D(i.dispatched_qty) >= D(i.qty) for i in inv.items)
        inv.order.status = "DISPATCHED" if full else "PARTIALLY_DISPATCHED"
        audit(user_id, "DISPATCH", inv.invoice_no)
        db.session.commit()
        return d
    except Exception:
        db.session.rollback()
        raise


# ---------------- payments ----------------
def allocate(payment_id, invoice_id, amount):
    pay, inv, amount = db.session.get(Payment, payment_id), db.session.get(Invoice, invoice_id), D(amount)
    if amount <= 0:
        raise ValueError("Amount must be positive")
    if inv.status != "POSTED" or inv.customer_id != pay.customer_id:
        raise ValueError("Invoice does not belong to this customer or is cancelled")
    if amount > pay.unallocated:
        raise ValueError("Allocation exceeds unallocated payment amount")
    if amount > inv.balance:
        raise ValueError("Allocation exceeds invoice balance")
    db.session.add(PaymentAllocation(payment_id=pay.id, invoice_id=inv.id, amount=amount))
    db.session.flush()


def record_payment(customer_id, amount, mode, user_id, invoice_id=None, when=None):
    amount = money(amount)
    if amount <= 0:
        raise ValueError("Payment must be positive")
    try:
        pay = Payment(customer_id=customer_id, amount=amount, mode=mode, user_id=user_id,
                      pay_date=when or date.today())
        db.session.add(pay)
        db.session.flush()
        if invoice_id:
            allocate(pay.id, int(invoice_id), amount)
        audit(user_id, "PAYMENT", f"{amount} from customer {customer_id}")
        db.session.commit()
        return pay
    except Exception:
        db.session.rollback()
        raise


def customer_outstanding(customer_id):
    invs = Invoice.query.filter_by(customer_id=customer_id, status="POSTED").all()
    return sum((i.balance for i in invs), D(0))
