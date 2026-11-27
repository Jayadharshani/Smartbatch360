from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import current_user
from ..auth_utils import roles_required
from ..extensions import db
from ..models import Order, Customer, Product
from ..services import sales as svc
from ..services.inventory import InsufficientStock

bp = Blueprint("sales", __name__, url_prefix="/sales")


@bp.route("/new", methods=["GET", "POST"])
@roles_required("salesman")
def new_order():
    custs = Customer.query.filter_by(salesman_id=current_user.id).all() or Customer.query.all()
    products = Product.query.filter_by(active=True).all()
    if request.method == "POST":
        try:
            cid = int(request.form["customer_id"])
            if cid not in [c.id for c in custs]:
                abort(403)
            o = svc.create_order(current_user.id, cid, [(p.id, request.form.get(f"qty_{p.id}") or 0) for p in products])
            flash(f"Order {o.order_no} submitted", "success")
            return redirect(url_for("sales.orders"))
        except ValueError as e:
            flash(str(e), "danger")
    return render_template("order_new.html", customers=custs, products=products)


@bp.route("/orders")
@roles_required("salesman", "admin", "owner", "auditor")
def orders():
    q = Order.query.order_by(Order.id.desc())
    if current_user.role == "salesman":
        q = q.filter_by(salesman_id=current_user.id)
    return render_template("orders.html", orders=q.all())


@bp.route("/order/<int:oid>", methods=["GET", "POST"])
@roles_required("salesman", "admin", "owner", "auditor")
def order(oid):
    o = db.session.get(Order, oid) or abort(404)
    if current_user.role == "salesman" and o.salesman_id != current_user.id:
        abort(403)
    if request.method == "POST":
        if current_user.role != "admin":
            abort(403)
        act = request.form["action"]
        try:
            if act == "approve":
                svc.set_status(o.id, "APPROVED", current_user.id)
            elif act == "reject":
                svc.set_status(o.id, "REJECTED", current_user.id)
            elif act == "edit":
                svc.edit_order(o.id, {i.id: (request.form[f"qty_{i.id}"], request.form[f"price_{i.id}"]) for i in o.items}, current_user.id)
            elif act == "invoice":
                inv = svc.generate_invoice(o.id, current_user.id)
                flash(f"Invoice {inv.invoice_no} generated", "success")
                return redirect(url_for("billing.invoice", iid=inv.id))
            flash("Done", "success")
        except (ValueError, InsufficientStock) as e:
            flash(str(e), "danger")
        return redirect(url_for("sales.order", oid=o.id))
    return render_template("order_detail.html", o=o, check=svc.stock_check(o))
