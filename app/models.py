"""All database tables. Money = Numeric(12,2), quantities = Numeric(14,3), costs = Numeric(14,4)."""
from datetime import datetime, date
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from .extensions import db, login_manager
from .utils import D, q3, money

ROLES = ("salesman", "admin", "production", "auditor", "owner")
ROLE_LABELS = {"salesman": "Salesman", "admin": "Factory Admin", "production": "Production Supervisor",
               "auditor": "Accountant / Auditor", "owner": "Owner"}


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, index=True)
    is_active_user = db.Column(db.Boolean, default=True)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

    @property
    def is_active(self):
        return self.is_active_user


@login_manager.user_loader
def load_user(uid):
    return db.session.get(User, int(uid))


class Customer(db.Model):
    __tablename__ = "customers"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    gstin = db.Column(db.String(20))
    state = db.Column(db.String(50), default="Tamil Nadu", nullable=False)
    address = db.Column(db.String(255))
    salesman_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    salesman = db.relationship("User")


class Supplier(db.Model):
    __tablename__ = "suppliers"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    gstin = db.Column(db.String(20))
    phone = db.Column(db.String(20))
    state = db.Column(db.String(50), default="Tamil Nadu")


class Item(db.Model):
    """inventory_items: raw material (RAW), packaging (PACK) or finished good (FG)."""
    __tablename__ = "inventory_items"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(30), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    kind = db.Column(db.String(5), nullable=False, index=True)
    unit = db.Column(db.String(10), nullable=False)
    reorder_level = db.Column(db.Numeric(14, 3), default=0)
    avg_cost = db.Column(db.Numeric(14, 4), default=0)  # weighted average cost

    @property
    def stock(self):
        rows = db.session.query(StockLedger.qty_in, StockLedger.qty_out).filter_by(item_id=self.id).all()
        return q3(sum((D(i) - D(o) for i, o in rows), D(0)))

    @property
    def low(self):
        return D(self.reorder_level) > 0 and self.stock <= D(self.reorder_level)


class Product(db.Model):
    __tablename__ = "products"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(30), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(50))
    pack_size = db.Column(db.String(30))
    price = db.Column(db.Numeric(12, 2), nullable=False)
    gst_rate = db.Column(db.Numeric(5, 2), default=5)
    hsn = db.Column(db.String(10))
    packets_per_carton = db.Column(db.Integer, default=20)
    item_id = db.Column(db.Integer, db.ForeignKey("inventory_items.id"), nullable=False)
    active = db.Column(db.Boolean, default=True)
    item = db.relationship("Item")
    boms = db.relationship("Bom", backref="product", order_by="Bom.version")

    @property
    def active_bom(self):
        act = [b for b in self.boms if b.is_active]
        return act[-1] if act else None


class Bom(db.Model):
    __tablename__ = "bom_headers"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    version = db.Column(db.Integer, nullable=False)
    expected_output = db.Column(db.Numeric(14, 3), nullable=False)  # packets per batch
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship("BomItem", backref="bom", cascade="all, delete-orphan")
    __table_args__ = (db.UniqueConstraint("product_id", "version"),)


class BomItem(db.Model):
    __tablename__ = "bom_items"
    id = db.Column(db.Integer, primary_key=True)
    bom_id = db.Column(db.Integer, db.ForeignKey("bom_headers.id"), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey("inventory_items.id"), nullable=False)
    qty = db.Column(db.Numeric(14, 3), nullable=False)  # per batch
    unit = db.Column(db.String(10), nullable=False)
    item = db.relationship("Item")


class Purchase(db.Model):
    __tablename__ = "purchases"
    id = db.Column(db.Integer, primary_key=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id"), nullable=False)
    date = db.Column(db.Date, default=date.today)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    supplier = db.relationship("Supplier")
    items = db.relationship("PurchaseItem", backref="purchase", cascade="all, delete-orphan")

    @property
    def total(self):
        return money(sum((D(i.qty) * D(i.rate) for i in self.items), D(0)))


class PurchaseItem(db.Model):
    __tablename__ = "purchase_items"
    id = db.Column(db.Integer, primary_key=True)
    purchase_id = db.Column(db.Integer, db.ForeignKey("purchases.id"), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey("inventory_items.id"), nullable=False)
    qty = db.Column(db.Numeric(14, 3), nullable=False)
    rate = db.Column(db.Numeric(12, 4), nullable=False)
    item = db.relationship("Item")


class StockLedger(db.Model):
    """Single source of truth for stock. Rows are never edited or deleted."""
    __tablename__ = "stock_ledger"
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("inventory_items.id"), nullable=False, index=True)
    txn_type = db.Column(db.String(30), nullable=False)
    qty_in = db.Column(db.Numeric(14, 3), default=0, nullable=False)
    qty_out = db.Column(db.Numeric(14, 3), default=0, nullable=False)
    unit_cost = db.Column(db.Numeric(14, 4), default=0)
    txn_date = db.Column(db.DateTime, default=datetime.utcnow)
    doc_type = db.Column(db.String(30))
    doc_id = db.Column(db.Integer)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    note = db.Column(db.String(255))
    item = db.relationship("Item")
    user = db.relationship("User")


class ProductionRun(db.Model):
    __tablename__ = "production_runs"
    id = db.Column(db.Integer, primary_key=True)
    batch_no = db.Column(db.String(30), unique=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    bom_id = db.Column(db.Integer, db.ForeignKey("bom_headers.id"), nullable=False)
    batches = db.Column(db.Numeric(8, 2), nullable=False)
    expected_output = db.Column(db.Numeric(14, 3), nullable=False)
    actual_output = db.Column(db.Numeric(14, 3), nullable=False)
    damaged_pouches = db.Column(db.Numeric(14, 3), default=0)
    run_date = db.Column(db.Date, default=date.today)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    rm_cost = db.Column(db.Numeric(14, 2), default=0)
    pack_cost = db.Column(db.Numeric(14, 2), default=0)
    labour_cost = db.Column(db.Numeric(14, 2), default=0)
    power_cost = db.Column(db.Numeric(14, 2), default=0)
    other_cost = db.Column(db.Numeric(14, 2), default=0)
    total_cost = db.Column(db.Numeric(14, 2), default=0)
    cost_per_packet = db.Column(db.Numeric(14, 4), default=0)
    product = db.relationship("Product")
    bom = db.relationship("Bom")
    materials = db.relationship("ProductionMaterial", backref="run", cascade="all, delete-orphan")

    @property
    def yield_variance_pct(self):
        e = D(self.expected_output)
        return ((D(self.actual_output) - e) / e * 100) if e else D(0)


class ProductionMaterial(db.Model):
    __tablename__ = "production_materials"
    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(db.Integer, db.ForeignKey("production_runs.id"), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey("inventory_items.id"), nullable=False)
    planned_qty = db.Column(db.Numeric(14, 3), nullable=False)
    actual_qty = db.Column(db.Numeric(14, 3), nullable=False)
    unit_cost = db.Column(db.Numeric(14, 4), nullable=False)
    item = db.relationship("Item")

    @property
    def diff(self):
        return D(self.actual_qty) - D(self.planned_qty)

    @property
    def var_pct(self):
        p = D(self.planned_qty)
        return (self.diff / p * 100) if p else D(0)


class Expense(db.Model):
    """Labour / power / other overheads attached to a production run."""
    __tablename__ = "expenses"
    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(db.Integer, db.ForeignKey("production_runs.id"), nullable=False)
    kind = db.Column(db.String(10), nullable=False)  # LABOUR / POWER / OTHER
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    date = db.Column(db.Date, default=date.today)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))


class Order(db.Model):
    __tablename__ = "orders"
    id = db.Column(db.Integer, primary_key=True)
    order_no = db.Column(db.String(20), unique=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False)
    salesman_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    status = db.Column(db.String(25), default="SUBMITTED", index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    customer = db.relationship("Customer")
    salesman = db.relationship("User")
    items = db.relationship("OrderItem", backref="order", cascade="all, delete-orphan")
    invoice = db.relationship("Invoice", uselist=False, backref="order")

    @property
    def total(self):
        return money(sum((D(i.qty) * D(i.price) for i in self.items), D(0)))


class OrderItem(db.Model):
    __tablename__ = "order_items"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    qty = db.Column(db.Numeric(14, 3), nullable=False)
    price = db.Column(db.Numeric(12, 2), nullable=False)
    dispatched_qty = db.Column(db.Numeric(14, 3), default=0)
    product = db.relationship("Product")


class Invoice(db.Model):
    __tablename__ = "invoices"
    id = db.Column(db.Integer, primary_key=True)
    invoice_no = db.Column(db.String(30), unique=True, nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False)
    invoice_date = db.Column(db.Date, default=date.today)
    taxable = db.Column(db.Numeric(12, 2), default=0)
    cgst = db.Column(db.Numeric(12, 2), default=0)
    sgst = db.Column(db.Numeric(12, 2), default=0)
    igst = db.Column(db.Numeric(12, 2), default=0)
    total = db.Column(db.Numeric(12, 2), default=0)
    status = db.Column(db.String(15), default="POSTED")  # POSTED / CANCELLED
    customer = db.relationship("Customer")
    items = db.relationship("InvoiceItem", backref="invoice", cascade="all, delete-orphan")
    allocations = db.relationship("PaymentAllocation", backref="invoice")

    @property
    def paid(self):
        return money(sum((D(a.amount) for a in self.allocations), D(0)))

    @property
    def balance(self):
        return D(self.total) - self.paid if self.status == "POSTED" else D(0)


class InvoiceItem(db.Model):
    __tablename__ = "invoice_items"
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    qty = db.Column(db.Numeric(14, 3), nullable=False)
    price = db.Column(db.Numeric(12, 2), nullable=False)
    gst_rate = db.Column(db.Numeric(5, 2), nullable=False)
    hsn = db.Column(db.String(10))
    taxable = db.Column(db.Numeric(12, 2), nullable=False)
    cgst = db.Column(db.Numeric(12, 2), default=0)
    sgst = db.Column(db.Numeric(12, 2), default=0)
    igst = db.Column(db.Numeric(12, 2), default=0)
    dispatched_qty = db.Column(db.Numeric(14, 3), default=0)
    product = db.relationship("Product")


class Dispatch(db.Model):
    __tablename__ = "dispatches"
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.id"), nullable=False)
    dispatch_date = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    items = db.relationship("DispatchItem", backref="dispatch", cascade="all, delete-orphan")


class DispatchItem(db.Model):
    __tablename__ = "dispatch_items"
    id = db.Column(db.Integer, primary_key=True)
    dispatch_id = db.Column(db.Integer, db.ForeignKey("dispatches.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    qty = db.Column(db.Numeric(14, 3), nullable=False)


class Payment(db.Model):
    __tablename__ = "payments"
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    mode = db.Column(db.String(20), default="Cash")
    pay_date = db.Column(db.Date, default=date.today)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    customer = db.relationship("Customer")
    allocations = db.relationship("PaymentAllocation", backref="payment")

    @property
    def unallocated(self):
        return D(self.amount) - money(sum((D(a.amount) for a in self.allocations), D(0)))


class PaymentAllocation(db.Model):
    __tablename__ = "payment_allocations"
    id = db.Column(db.Integer, primary_key=True)
    payment_id = db.Column(db.Integer, db.ForeignKey("payments.id"), nullable=False)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.id"), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    ts = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    action = db.Column(db.String(50), nullable=False)
    detail = db.Column(db.String(500))
    user = db.relationship("User")


def audit(user_id, action, detail=""):
    db.session.add(AuditLog(user_id=user_id, action=action, detail=detail[:500]))
