import click
from flask import Flask, render_template
from flask_login import current_user
from .config import Config
from .extensions import db, migrate, login_manager, csrf

MENU = {
    "salesman": [("New Order", "sales.new_order", "bi-cart-plus"), ("My Orders", "sales.orders", "bi-list-check")],
    "admin": [("Dashboard", "main.dashboard", "bi-speedometer2"), ("Orders", "sales.orders", "bi-list-check"),
              ("Invoices", "billing.invoices", "bi-receipt"), ("Payments", "billing.payments", "bi-cash-coin"),
              ("Products", "master.entity_list|products", "bi-box"), ("Customers", "master.entity_list|customers", "bi-people"),
              ("Suppliers", "master.entity_list|suppliers", "bi-truck"), ("Items", "master.entity_list|items", "bi-boxes"),
              ("Purchases", "inventory.purchases", "bi-bag"), ("Stock", "inventory.stock", "bi-archive"),
              ("Production", "production.runs", "bi-gear"), ("Reports", "reports.index", "bi-file-earmark-bar-graph"),
              ("Intelligence", "intelligence.index", "bi-lightbulb"), ("Users", "auth.users", "bi-person-gear")],
    "production": [("Dashboard", "main.dashboard", "bi-speedometer2"), ("New Production Run", "production.new_run", "bi-plus-circle"),
                   ("Production History", "production.runs", "bi-gear"), ("Stock", "inventory.stock", "bi-archive"),
                   ("Purchases", "inventory.purchases", "bi-bag"), ("Items", "master.entity_list|items", "bi-boxes"),
                   ("Products & BOM", "master.entity_list|products", "bi-box"), ("Intelligence", "intelligence.index", "bi-lightbulb")],
    "auditor": [("Dashboard", "main.dashboard", "bi-speedometer2"), ("Reports", "reports.index", "bi-file-earmark-bar-graph"),
                ("Invoices", "billing.invoices", "bi-receipt"), ("Production History", "production.runs", "bi-gear"),
                ("Intelligence", "intelligence.index", "bi-lightbulb")],
    "owner": [("Dashboard", "main.dashboard", "bi-speedometer2"), ("Orders", "sales.orders", "bi-list-check"),
              ("Stock", "inventory.stock", "bi-archive"), ("Production", "production.runs", "bi-gear"),
              ("Reports", "reports.index", "bi-file-earmark-bar-graph"), ("Intelligence", "intelligence.index", "bi-lightbulb")],
}


def create_app(config=None):
    app = Flask(__name__)
    app.config.from_object(config or Config)
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    from .blueprints import auth, main, master, inventory, production, sales, billing, reports, intelligence
    for m in (auth, main, master, inventory, production, sales, billing, reports, intelligence):
        app.register_blueprint(m.bp)

    @app.context_processor
    def inject():
        menu = MENU.get(current_user.role, []) if current_user.is_authenticated else []
        return dict(menu=menu, company=app.config["COMPANY_NAME"])

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("error.html", code=403, msg="You do not have permission to open this page."), 403

    @app.errorhandler(404)
    def notfound(e):
        return render_template("error.html", code=404, msg="Page not found."), 404

    @app.cli.command("init-db")
    def init_db():
        """Create all tables (and demo data with: flask seed)."""
        db.create_all()
        click.echo("Tables created.")

    @app.cli.command("seed")
    def seed():
        """Reset database and load demo users + benchmark opening data."""
        from .seed import reset_db, seed_base
        reset_db()
        seed_base()
        click.echo("Seeded. Logins: admin/admin123, salesman_a/salesman_a123, production/production123, auditor/auditor123, owner/owner123")

    @app.cli.command("benchmark")
    def benchmark():
        """Reset DB and run the 18 benchmark transactions, printing computed results."""
        from .seed import run_benchmark
        for k, v in run_benchmark().items():
            click.echo(f"{k:28} {v}")

    @app.cli.command("demo")
    def demo():
        """Reset DB and load full sample data (benchmark transactions already done)."""
        from .seed import run_benchmark
        run_benchmark()
        click.echo("Sample data loaded. Start the app with: python run.py")

    return app
