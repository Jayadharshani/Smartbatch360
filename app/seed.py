"""Seed data + the mandatory benchmark scenario (executed through the real services)."""
from decimal import Decimal
from .extensions import db
from .models import User, Customer, Supplier, Item, Product, StockLedger, ROLES
from .utils import D
from .services import inventory, production, sales, reports
from .services.intelligence import recommend_production

DEMO_USERS = [("salesman_a", "Salesman A", "salesman"), ("salesman_b", "Salesman B", "salesman"),
              ("admin", "Factory Admin", "admin"), ("production", "Production Supervisor", "production"),
              ("auditor", "Accountant", "auditor"), ("owner", "Owner", "owner")]


def reset_db():
    db.drop_all()
    db.create_all()


def seed_base():
    """Master data + opening stock exactly as in the benchmark."""
    users = {}
    for uname, name, role in DEMO_USERS:
        u = User(username=uname, full_name=name, role=role)
        u.set_password(f"{uname}123")
        db.session.add(u)
        users[uname] = u
    db.session.flush()
    mk = lambda code, name, kind, unit, rl, cost: Item(code=code, name=name, kind=kind, unit=unit, reorder_level=rl, avg_cost=cost)
    flour, oil, spice = mk("FLOUR", "Flour", "RAW", "kg", 30, 42), mk("OIL", "Cooking Oil", "RAW", "l", 10, 140), mk("SPICE", "Salt and Spice Mix", "RAW", "kg", 2, 200)
    pouch, carton = mk("POUCH", "200 g Pouch", "PACK", "piece", 100, "2.5"), mk("CARTON", "Carton", "PACK", "piece", 10, 15)
    fg = mk("FG-MUR200", "Murukku 200 g (finished)", "FG", "packet", 20, 0)
    db.session.add_all([flour, oil, spice, pouch, carton, fg])
    db.session.flush()
    prod = Product(code="MUR200", name="Murukku 200 g", category="Murukku", pack_size="200 g", price=D(50),
                   gst_rate=D(5), hsn="2106", packets_per_carton=20, item_id=fg.id)
    db.session.add(prod)
    db.session.add_all([Supplier(name="Trichy Flour Mills", state="Tamil Nadu", phone="9000000001"),
                        Customer(name="Retailer A", state="Tamil Nadu", gstin="33AAAAA0000A1Z5", address="Trichy",
                                 salesman_id=users["salesman_a"].id),
                        Customer(name="Distributor B", state="Karnataka", gstin="29BBBBB1111B1Z5", address="Bengaluru",
                                 salesman_id=users["salesman_b"].id)])
    db.session.flush()
    admin_id = users["admin"].id
    for item, qty in ((flour, 100), (oil, 30), (spice, 5), (pouch, 500), (carton, 30), (fg, 50)):
        inventory.post(item, "OPENING", qty_in=qty, doc_type="opening", user_id=admin_id, unit_cost=item.avg_cost)
    db.session.commit()
    production.create_bom_version(prod.id, 200, [(flour.id, 40, "kg"), (oil.id, 10, "l"), (spice.id, "1.2", "kg"),
                                                 (pouch.id, 200, "piece"), (carton.id, 10, "piece")], admin_id)


def run_benchmark():
    """Runs the 18 benchmark steps. Returns computed results (nothing is hard coded)."""
    reset_db()
    seed_base()
    U = lambda n: User.query.filter_by(username=n).one()
    I = lambda c: Item.query.filter_by(code=c).one()
    prod = Product.query.filter_by(code="MUR200").one()
    admin, sup = U("admin"), Supplier.query.first()
    ret_a, dist_b = Customer.query.filter_by(name="Retailer A").one(), Customer.query.filter_by(name="Distributor B").one()
    R = {}
    inventory.receive_purchase(sup.id, [(I("FLOUR").id, 60, 45)], admin.id)                        # 1
    R["flour_avg_cost"] = I("FLOUR").avg_cost
    run = production.run_production(prod.id, prod.active_bom.id, 1,                                  # 2-8
                                    {I("FLOUR").id: 40, I("OIL").id: "10.5", I("SPICE").id: "1.2", I("CARTON").id: 9},
                                    188, 6, U("production").id)
    R["run_id"] = run.id
    R["fg_after_production"] = I("FG-MUR200").stock
    o1 = sales.create_order(U("salesman_a").id, ret_a.id, [(prod.id, 150)])                          # 9
    sales.set_status(o1.id, "APPROVED", admin.id)                                                    # 10
    inv = sales.generate_invoice(o1.id, admin.id)                                                    # 11
    sales.dispatch(inv.id, {prod.id: 150}, admin.id)                                                 # 12
    R["fg_after_dispatch"] = I("FG-MUR200").stock
    o2 = sales.create_order(U("salesman_b").id, dist_b.id, [(prod.id, 120)])                         # 13
    R["distributor_b_shortage"] = sales.stock_check(o2)[0]["shortage"]                               # 14
    sales.record_payment(ret_a.id, 4000, "UPI", admin.id, invoice_id=inv.id)                         # 15
    production.add_expense(run.id, "LABOUR", 1200, admin.id)                                         # 16
    production.add_expense(run.id, "POWER", 600, admin.id)                                           # 17
    db.session.refresh(run)
    R.update(flour_stock=I("FLOUR").stock, oil_stock=I("OIL").stock, pouch_stock=I("POUCH").stock,
             yield_variance=run.yield_variance_pct,
             oil_variance=[v["pct"] for v in production.variance_rows(run) if v["item"] == "Cooking Oil"][0],
             taxable=inv.taxable, cgst=inv.cgst, sgst=inv.sgst, igst=inv.igst, invoice_total=inv.total,
             outstanding=sales.customer_outstanding(ret_a.id), invoice_no=inv.invoice_no,
             rm_cost=run.rm_cost, pack_cost=run.pack_cost, total_cost=run.total_cost, cost_per_packet=run.cost_per_packet)
    R["reports_generated"] = {k: len(f(None, None)[2]) for k, f in reports.REPORTS.items()}           # 18
    return R
