from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import current_user
from ..auth_utils import roles_required
from ..extensions import db
from ..models import Product, Customer, Supplier, Item, User, Bom, audit
from ..utils import D
from ..services import production as prod_svc

bp = Blueprint("master", __name__, url_prefix="/master")

UNITS = ["kg", "g", "l", "ml", "piece", "packet", "carton"]
STATES = ["Tamil Nadu", "Karnataka", "Kerala", "Andhra Pradesh", "Telangana", "Maharashtra", "Delhi"]

ENT = {
    "products": dict(title="Products", model=Product, roles=("admin",), cols=["code", "name", "category", "pack_size", "price", "gst_rate", "hsn", "packets_per_carton"]),
    "customers": dict(title="Customers", model=Customer, roles=("admin",), cols=["name", "gstin", "state", "address"]),
    "suppliers": dict(title="Suppliers", model=Supplier, roles=("admin",), cols=["name", "gstin", "phone", "state"]),
    "items": dict(title="Raw / Packaging Items", model=Item, roles=("admin", "production"), cols=["code", "name", "kind", "unit", "reorder_level", "avg_cost"]),
}


def fields_for(name):
    if name == "products":
        return [dict(n="code", l="Product code"), dict(n="name", l="Product name"), dict(n="category", l="Category"),
                dict(n="pack_size", l="Pack size"), dict(n="price", l="Selling price (Rs)", t="number"),
                dict(n="gst_rate", l="GST rate %", t="number", v="5"), dict(n="hsn", l="HSN code"),
                dict(n="packets_per_carton", l="Packets per carton", t="number", v="20")]
    if name == "customers":
        sm = [(u.id, u.full_name) for u in User.query.filter_by(role="salesman")]
        return [dict(n="name", l="Name"), dict(n="gstin", l="GSTIN", req=False), dict(n="state", l="State", opts=[(s, s) for s in STATES]),
                dict(n="address", l="Address", req=False), dict(n="salesman_id", l="Salesman", opts=sm)]
    if name == "suppliers":
        return [dict(n="name", l="Name"), dict(n="gstin", l="GSTIN", req=False), dict(n="phone", l="Phone", req=False),
                dict(n="state", l="State", opts=[(s, s) for s in STATES])]
    return [dict(n="code", l="Code"), dict(n="name", l="Name"), dict(n="kind", l="Type", opts=[("RAW", "Raw material"), ("PACK", "Packaging")]),
            dict(n="unit", l="Unit", opts=[(u, u) for u in UNITS]), dict(n="reorder_level", l="Low-stock level", t="number", v="0")]


@bp.route("/<name>", methods=["GET", "POST"])
@roles_required("admin", "production", "owner", "auditor")
def entity_list(name):
    cfg = ENT.get(name) or abort(404)
    can_edit = current_user.role in cfg["roles"]
    if request.method == "POST":
        if not can_edit:
            abort(403)
        f = request.form
        try:
            data = {}
            for fld in fields_for(name):
                val = f.get(fld["n"], "").strip()
                if fld.get("req", True) and val == "":
                    raise ValueError(f"{fld['l']} is required")
                data[fld["n"]] = D(val) if fld.get("t") == "number" and val != "" else (val or None)
            if name == "products":
                if Product.query.filter_by(code=data["code"]).first():
                    raise ValueError("Product code already exists")
                data["packets_per_carton"] = int(data["packets_per_carton"])
                fg = Item(code="FG-" + data["code"], name=data["name"] + " (finished)", kind="FG", unit="packet", reorder_level=0)
                db.session.add(fg)
                db.session.flush()
                db.session.add(Product(item_id=fg.id, **data))
            elif name == "customers":
                db.session.add(Customer(**data))
            elif name == "suppliers":
                db.session.add(Supplier(**data))
            else:
                if Item.query.filter_by(code=data["code"]).first():
                    raise ValueError("Item code already exists")
                db.session.add(Item(**data))
            audit(current_user.id, "MASTER_ADD", f"{name}: {data.get('name')}")
            db.session.commit()
            flash("Saved", "success")
        except Exception as e:
            db.session.rollback()
            flash(str(e), "danger")
        return redirect(url_for("master.entity_list", name=name))
    rows = cfg["model"].query.all()
    return render_template("master.html", name=name, title=cfg["title"], cols=cfg["cols"], rows=rows,
                           fields=fields_for(name) if can_edit else None)


@bp.route("/bom/<int:product_id>", methods=["GET", "POST"])
@roles_required("admin", "production", "owner", "auditor")
def bom(product_id):
    p = db.session.get(Product, product_id) or abort(404)
    if request.method == "POST":
        if current_user.role not in ("admin", "production"):
            abort(403)
        f = request.form
        try:
            lines = []
            for it in Item.query.filter(Item.kind != "FG").all():
                q = f.get(f"qty_{it.id}", "").strip()
                if q and D(q) > 0:
                    lines.append((it.id, D(q), f.get(f"unit_{it.id}", it.unit)))
            if not lines or D(f["expected_output"]) <= 0:
                raise ValueError("Enter expected output and at least one material")
            prod_svc.create_bom_version(p.id, f["expected_output"], lines, current_user.id)
            flash("New BOM version saved (old versions are preserved)", "success")
        except Exception as e:
            db.session.rollback()
            flash(str(e), "danger")
        return redirect(url_for("master.bom", product_id=p.id))
    return render_template("bom.html", p=p, items=Item.query.filter(Item.kind != "FG").all(), units=UNITS,
                           can_edit=current_user.role in ("admin", "production"))
