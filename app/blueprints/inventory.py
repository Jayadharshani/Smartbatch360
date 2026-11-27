from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user
from ..auth_utils import roles_required
from ..models import Item, Supplier, Purchase
from ..services import inventory as inv, reports
from ..services.inventory import InsufficientStock

bp = Blueprint("inventory", __name__)


@bp.route("/stock")
@roles_required("admin", "production", "owner", "auditor")
def stock():
    title, headers, rows = reports.stock_summary()
    return render_template("table.html", title=title, headers=headers, rows=rows,
                           actions=[("Stock Ledger", url_for("reports.view", key="stock-ledger")),
                                    ("Adjust Stock", url_for("inventory.adjust"))] if current_user.role in ("admin", "production") else [])


@bp.route("/stock/adjust", methods=["GET", "POST"])
@roles_required("admin", "production")
def adjust():
    if request.method == "POST":
        try:
            inv.adjust(request.form["item_id"], request.form["delta"], request.form["reason"], current_user.id)
            flash("Adjustment posted to stock ledger", "success")
            return redirect(url_for("inventory.stock"))
        except (ValueError, InsufficientStock) as e:
            flash(str(e), "danger")
    return render_template("adjust.html", items=Item.query.order_by(Item.name).all())


@bp.route("/purchases", methods=["GET", "POST"])
@roles_required("admin", "production", "auditor", "owner")
def purchases():
    if request.method == "POST":
        if current_user.role not in ("admin", "production"):
            return render_template("error.html", code=403, msg="Read-only role"), 403
        lines = []
        f = request.form
        for n in range(1, 6):
            if f.get(f"item_{n}") and f.get(f"qty_{n}"):
                lines.append((f[f"item_{n}"], f[f"qty_{n}"], f.get(f"rate_{n}") or 0))
        try:
            inv.receive_purchase(int(f["supplier_id"]), lines, current_user.id)
            flash("Purchase received and stock updated", "success")
        except Exception as e:
            flash(str(e), "danger")
        return redirect(url_for("inventory.purchases"))
    return render_template("purchases.html", purchases=Purchase.query.order_by(Purchase.id.desc()).all(),
                           suppliers=Supplier.query.all(), items=Item.query.filter(Item.kind != "FG").all(),
                           can_edit=current_user.role in ("admin", "production"))
