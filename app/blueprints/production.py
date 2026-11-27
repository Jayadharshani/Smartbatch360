import io
import qrcode
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, send_file
from flask_login import current_user
from ..auth_utils import roles_required
from ..extensions import db
from ..models import Product, ProductionRun, Bom
from ..utils import D
from ..services import production as svc
from ..services.inventory import InsufficientStock

bp = Blueprint("production", __name__, url_prefix="/production")


@bp.route("/")
@roles_required("admin", "production", "owner", "auditor")
def runs():
    return render_template("runs.html", runs=ProductionRun.query.order_by(ProductionRun.id.desc()).all())


@bp.route("/new", methods=["GET", "POST"])
@roles_required("production")
def new_run():
    products = Product.query.filter_by(active=True).all()
    product = db.session.get(Product, int(request.values.get("product_id", 0) or 0)) or (products[0] if products else None)
    if product is None:
        flash("Create a product first", "warning")
        return redirect(url_for("main.dashboard"))
    bom = db.session.get(Bom, int(request.values.get("bom_id", 0) or 0)) if request.values.get("bom_id") else product.active_bom
    if bom is None or bom.product_id != product.id:
        bom = product.active_bom
    batches = D(request.values.get("batches") or 1)
    if request.method == "POST" and request.form.get("save") == "1":
        try:
            actuals = {bi.item_id: D(request.form.get(f"actual_{bi.item_id}") or 0) for bi in bom.items}
            run = svc.run_production(product.id, bom.id, batches, actuals, request.form["good_output"],
                                     request.form.get("damaged") or 0, current_user.id)
            flash(f"Production run {run.batch_no} saved. Stock updated.", "success")
            return redirect(url_for("production.detail", run_id=run.id))
        except (ValueError, InsufficientStock) as e:
            flash(str(e), "danger")
    lines = [dict(bi=bi, planned=p, stock=bi.item.stock) for bi, p in svc.planned_lines(bom, batches)] if bom else []
    return render_template("run_new.html", products=products, product=product, bom=bom, batches=batches, lines=lines)


@bp.route("/<int:run_id>", methods=["GET", "POST"])
@roles_required("admin", "production", "owner", "auditor")
def detail(run_id):
    run = db.session.get(ProductionRun, run_id) or abort(404)
    if request.method == "POST":
        if current_user.role not in ("admin", "production"):
            abort(403)
        try:
            svc.add_expense(run.id, request.form["kind"], request.form["amount"], current_user.id)
            flash("Cost added and cost per packet recalculated", "success")
        except ValueError as e:
            flash(str(e), "danger")
        return redirect(url_for("production.detail", run_id=run.id))
    return render_template("run_detail.html", run=run, rows=svc.variance_rows(run), yflag=svc.yield_flag(run),
                           can_edit=current_user.role in ("admin", "production"))


@bp.route("/<int:run_id>/qr.png")
@roles_required("admin", "production", "owner", "auditor")
def qr(run_id):
    img = qrcode.make(url_for("production.detail", run_id=run_id, _external=True))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")
