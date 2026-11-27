"""Runs the benchmark through the real services, then checks results against the spec."""
from decimal import Decimal as D
import pytest
from app.extensions import db
from app.models import Item, Product, Customer, User, StockLedger
from app.seed import run_benchmark
from app.services import sales, inventory
from app.services.inventory import InsufficientStock
from app.utils import convert, cartons_needed


@pytest.fixture()
def R(app):
    return run_benchmark()


def test_stock_results(R):
    assert R["flour_stock"] == D("120"); assert R["oil_stock"] == D("19.5"); assert R["pouch_stock"] == D("306")
    assert R["fg_after_production"] == D("238"); assert R["fg_after_dispatch"] == D("88")


def test_variances(R):
    assert R["yield_variance"] == D("-6"); assert R["oil_variance"] == D("5")


def test_gst_and_outstanding(R):
    assert (R["taxable"], R["cgst"], R["sgst"], R["igst"], R["invoice_total"]) == (D("7500"), D("187.50"), D("187.50"), D("0"), D("7875"))
    assert R["outstanding"] == D("3875"); assert R["invoice_no"].startswith("SB/")


def test_shortage(R):
    assert R["distributor_b_shortage"] == D("32")


def test_weighted_average_costing(R):
    assert R["flour_avg_cost"] == D("43.125")           # (100*42 + 60*45) / 160
    assert R["rm_cost"] == D("3435.00")                 # 40*43.125 + 10.5*140 + 1.2*200
    assert R["pack_cost"] == D("620.00")                # 194 pouches*2.5 + 9 cartons*15
    assert R["total_cost"] == D("5855.00")             # 3435 + 620 + 1200 labour + 600 power
    assert round(R["cost_per_packet"], 2) == D("31.14")


def test_reports_run(R):
    assert all(v >= 0 for v in R["reports_generated"].values()) and len(R["reports_generated"]) == 14


def test_igst_for_other_state(R, app):
    prod = Product.query.first(); b = Customer.query.filter_by(name="Distributor B").one()
    o = sales.create_order(User.query.filter_by(username="salesman_b").one().id, b.id, [(prod.id, 10)])
    sales.set_status(o.id, "APPROVED", 1)
    inv = sales.generate_invoice(o.id, 1)
    assert inv.igst == D("25.00") and inv.cgst == 0 and inv.sgst == 0


def test_dispatch_blocked_when_stock_short(R, app):
    prod = Product.query.first(); b = Customer.query.filter_by(name="Distributor B").one()
    o = sales.create_order(1, b.id, [(prod.id, 120)]); sales.set_status(o.id, "APPROVED", 1)
    inv = sales.generate_invoice(o.id, 1)
    before = prod.item.stock
    with pytest.raises(InsufficientStock):
        sales.dispatch(inv.id, {prod.id: 120}, 1)
    assert prod.item.stock == before                      # nothing changed
    sales.dispatch(inv.id, {prod.id: 88}, 1)              # partial dispatch works
    assert prod.item.stock == 0 and o.status == "PARTIALLY_DISPATCHED"


def test_payment_allocation_limits(R, app):
    inv = db_inv()
    with pytest.raises(ValueError):
        sales.record_payment(inv.customer_id, 5000, "Cash", 1, invoice_id=inv.id)   # more than balance 3875
    assert sales.customer_outstanding(inv.customer_id) == D("3875")


def db_inv():
    from app.models import Invoice
    return Invoice.query.first()


def test_no_negative_stock(R, app):
    with pytest.raises(InsufficientStock):
        inventory.adjust(Item.query.filter_by(code="OIL").one().id, -1000, "test", 1)


def test_ledger_never_negative_and_traceable(R, app):
    for it in Item.query.all():
        assert it.stock >= 0
    assert all(l.doc_type for l in StockLedger.query.filter(StockLedger.txn_type != "ADJUSTMENT").all())


def test_unit_conversion():
    assert convert(500, "g", "kg") == D("0.5") and convert(2, "kg", "g") == D("2000") and convert(1500, "ml", "l") == D("1.5")
    assert cartons_needed(188, 20) == 10 and cartons_needed(188, 25) == 8   # carton size is product specific
    with pytest.raises(ValueError):
        convert(1, "kg", "l")
