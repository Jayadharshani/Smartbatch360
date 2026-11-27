from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, Response
from flask_login import current_user
from ..auth_utils import roles_required
from ..extensions import db
from ..models import Invoice, Customer, Payment
from ..utils import D
from ..services import sales as svc, reports
from ..services.invoice_pdf import invoice_pdf
from ..services.inventory import InsufficientStock

bp = Blueprint("billing", __name__, url_prefix="/billing")


@bp.route("/invoices")
@roles_required("admin", "auditor", "owner")
def invoices():
    return render_template("invoices.html", invoices=Invoice.query.order_by(Invoice.id.desc()).all())


@bp.route("/invoice/<int:iid>", methods=["GET", "POST"])
@roles_required("admin", "auditor", "owner")
def invoice(iid):
    inv = db.session.get(Invoice, iid) or abort(404)
    if request.method == "POST":
        if current_user.role != "admin":
            abort(403)
        try:
            if request.form["action"] == "dispatch":
                svc.dispatch(inv.id, {i.product_id: D(request.form.get(f"qty_{i.product_id}") or 0) for i in inv.items}, current_user.id)
                flash("Dispatch recorded and finished goods stock reduced", "success")
            elif request.form["action"] == "cancel":
                svc.cancel_invoice(inv.id, request.form.get("reason", ""), current_user.id)
                flash("Invoice cancelled (kept for audit)", "warning")
        except (ValueError, InsufficientStock) as e:
            flash(str(e), "danger")
        return redirect(url_for("billing.invoice", iid=inv.id))
    return render_template("invoice_detail.html", inv=inv)


@bp.route("/invoice/<int:iid>/pdf")
@roles_required("admin", "auditor", "owner")
def pdf(iid):
    inv = db.session.get(Invoice, iid) or abort(404)
    return Response(invoice_pdf(inv), mimetype="application/pdf",
                    headers={"Content-Disposition": f"inline; filename={inv.invoice_no.replace('/', '-')}.pdf"})


@bp.route("/payments", methods=["GET", "POST"])
@roles_required("admin", "auditor", "owner")
def payments():
    if request.method == "POST":
        if current_user.role != "admin":
            abort(403)
        try:
            svc.record_payment(int(request.form["customer_id"]), request.form["amount"], request.form["mode"],
                               current_user.id, invoice_id=request.form.get("invoice_id") or None)
            flash("Payment recorded", "success")
        except ValueError as e:
            flash(str(e), "danger")
        return redirect(url_for("billing.payments"))
    open_inv = [i for i in Invoice.query.filter_by(status="POSTED").all() if i.balance > 0]
    return render_template("payments.html", payments=Payment.query.order_by(Payment.id.desc()).all(),
                           customers=Customer.query.all(), open_inv=open_inv, can_edit=current_user.role == "admin")
