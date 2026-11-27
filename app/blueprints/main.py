import json
from datetime import date, datetime
from collections import defaultdict
from flask import Blueprint, render_template, redirect, url_for
from flask_login import current_user, login_required
from ..auth_utils import roles_required
from ..models import Invoice, Order, ProductionRun, Item, Product, Customer
from ..utils import D, money
from ..services import inventory
from ..services.intelligence import anomalies
from ..services.sales import customer_outstanding

bp = Blueprint("main", __name__)


@bp.route("/")
@login_required
def home():
    return redirect(url_for("sales.new_order") if current_user.role == "salesman" else url_for("main.dashboard"))


@bp.route("/dashboard")
@roles_required("admin", "production", "auditor", "owner")
def dashboard():
    invs = Invoice.query.filter_by(status="POSTED").all()
    sales_by_day = defaultdict(lambda: D(0))
    for i in invs:
        sales_by_day[i.invoice_date.isoformat()] += D(i.total)
    runs = ProductionRun.query.order_by(ProductionRun.id).all()
    items = Item.query.order_by(Item.name).all()
    found, _ = anomalies()
    latest = {}
    for r in runs:
        latest[r.product.name] = D(r.cost_per_packet)
    kpi = dict(
        total_sales=money(sum((D(i.total) for i in invs), D(0))),
        today_orders=Order.query.filter(Order.created_at >= datetime.combine(date.today(), datetime.min.time())).count(),
        pending=Order.query.filter(Order.status.in_(["SUBMITTED", "APPROVED"])).count(),
        total_production=sum((D(r.actual_output) for r in runs), D(0)),
        outstanding=money(sum((customer_outstanding(c.id) for c in Customer.query.all()), D(0))),
    )
    margins = []
    for p in Product.query.all():
        if p.name in latest and D(p.price) > 0:
            cpp = latest[p.name]
            margins.append((p.name, cpp, D(p.price) - cpp, (D(p.price) - cpp) / D(p.price) * 100))
    charts = dict(
        sales=dict(labels=sorted(sales_by_day), data=[float(sales_by_day[k]) for k in sorted(sales_by_day)]),
        stock=dict(labels=[i.name for i in items], data=[float(i.stock) for i in items]),
        prod=dict(labels=[r.batch_no for r in runs], expected=[float(r.expected_output) for r in runs],
                  actual=[float(r.actual_output) for r in runs]),
    )
    return render_template("dashboard.html", kpi=kpi, low=inventory.low_stock_items(), alerts=found, margins=margins,
                           items=items, charts=json.dumps(charts))
