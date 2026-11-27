from app.seed import reset_db, seed_base


def login(client, u):
    return client.post("/login", data={"username": u, "password": f"{u}123"}, follow_redirects=True)


def test_login_and_bad_login(app, client):
    seed_base()
    assert b"Invalid" in client.post("/login", data={"username": "admin", "password": "x"}).data
    assert login(client, "admin").status_code == 200


def test_requires_login(app, client):
    seed_base()
    assert client.get("/dashboard").status_code == 302


def test_role_restrictions(app, client):
    seed_base()
    login(client, "salesman_a")
    for url in ("/dashboard", "/billing/invoices", "/reports/", "/production/new", "/users"):
        assert client.get(url).status_code == 403, url
    assert client.get("/sales/new").status_code == 200


def test_auditor_read_only(app, client):
    seed_base()
    login(client, "auditor")
    assert client.get("/reports/sales-register").status_code == 200
    assert client.get("/reports/stock-summary?format=xlsx").status_code == 200
    assert client.get("/reports/stock-summary?format=csv").status_code == 200
    assert client.get("/reports/stock-summary?format=pdf").status_code == 200
    assert client.post("/billing/payments", data={"customer_id": 1, "amount": 10, "mode": "Cash"}).status_code == 403
    assert client.post("/stock/adjust", data={}).status_code == 403


def test_all_pages_render_for_admin(app, client):
    from app.seed import run_benchmark
    run_benchmark()
    login(client, "admin")
    for url in ("/dashboard", "/sales/orders", "/sales/order/1", "/billing/invoices", "/billing/invoice/1", "/billing/invoice/1/pdf",
                "/billing/payments", "/master/products", "/master/customers", "/master/suppliers", "/master/items", "/master/bom/1",
                "/purchases", "/stock", "/stock/adjust", "/production/", "/production/1", "/production/1/qr.png",
                "/reports/", "/intelligence/", "/users"):
        r = client.get(url)
        assert r.status_code == 200, (url, r.status_code)
    r = client.post("/intelligence/", data={"q": "What is the current flour stock?"})
    assert b"120" in r.data
