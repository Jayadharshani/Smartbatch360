# SmartBatch 360 – Order-to-Audit & Manufacturing Management System
Internship project (Centre for Digital Infrastructure, NIT Tiruchirappalli) for a small South Indian snacks manufacturer.
It connects **Sales** (order -> approval -> GST invoice -> dispatch -> payment) with **Production** (purchase -> BOM issue -> production run -> output -> variance -> costing) through one stock ledger.

## Stack
Python 3.11+, Flask (application factory + blueprints), Flask-SQLAlchemy, Flask-Login, Flask-WTF (CSRF), Flask-Migrate, SQLite (default) or MySQL (PyMySQL), Bootstrap 5, Chart.js, ReportLab (PDF), OpenPyXL (Excel), qrcode, Pytest.

## Quick start (Windows/Linux/Mac)
```bash
python -m venv venv
venv\Scripts\activate          # Linux/Mac: source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env         # Linux/Mac: cp .env.example .env
flask --app run demo           # full sample data (benchmark transactions done)
# or: flask --app run seed     # only users + opening stock (empty dashboard)
python run.py                  # open http://127.0.0.1:5000
```
Run the full benchmark (18 steps, computed through the real services): `flask --app run benchmark`
Run tests: `python -m pytest -q`

### MySQL
```sql
CREATE DATABASE smartbatch360 CHARACTER SET utf8mb4;
CREATE USER 'smartbatch'@'localhost' IDENTIFIED BY 'yourpassword';
GRANT ALL ON smartbatch360.* TO 'smartbatch'@'localhost';
```
In `.env`: `DATABASE_URL=mysql+pymysql://smartbatch:yourpassword@localhost:3306/smartbatch360` then `flask --app run seed`.
Docker: `docker compose up --build` (provided, not tested by the author).

## Demo logins
| Role | Username | Password |
|---|---|---|
| Factory Admin | admin | admin123 |
| Salesman A / B | salesman_a / salesman_b | salesman_a123 / salesman_b123 |
| Production Supervisor | production | production123 |
| Accountant / Auditor | auditor | auditor123 |
| Owner | owner | owner123 |
Change these passwords before any real use.

## Benchmark results (actual output of `flask --app run benchmark`)
Flour 120 kg, oil 19.5 L, pouches 306, finished stock 238 -> 88 after dispatch, yield variance -6 %, oil variance +5 %,
taxable 7500, CGST 187.50, SGST 187.50, invoice 7875, outstanding 3875, Distributor B shortage 32.
Costing (weighted average): flour Rs 43.125/kg, total run cost Rs 5855, **Rs 31.14 per good packet**. (FIFO alternative: Rs 30.90 - see docs/DESIGN_NOTE.md.)

## What is implemented
Login/roles/RBAC (403 on forbidden URLs), master data (add + list; BOM versioning), purchases with weighted-average cost, stock ledger + adjustments + low-stock alerts,
BOM production runs with variance + costing + overhead entry, orders (edit with audit, approve/reject), GST invoices (CGST+SGST / IGST, FY numbering, PDF), partial dispatch,
payments + allocation + outstanding + ageing, 14 reports with date filter and CSV/Excel/PDF export, owner dashboard (Chart.js),
intelligence page (production recommendation, rule-based anomalies, loss impact, QR batch link, database-backed assistant).

## Assumptions & honest limitations
* Master data screens support **add and list only** (no edit/delete); users can be created but not edited.
* Roles are a column on `users` (no separate `roles` table). Tables not built: `units`, `unit_conversions`, `price_lists`, `inventory_lots` (no batch/expiry), `alerts`, `offline_sync_records`. Units/conversions are handled in code (`app/utils.py`); alerts are computed live.
* **Offline order capture is not implemented.** The PWA only provides an installable manifest + minimal service worker.
* Anomaly detection is **rule-based**, not machine learning (too little history to train a meaningful model). The assistant is keyword matching over database queries, not an LLM.
* QR code opens the batch page (login required) showing materials, output, wastage and cost.
* Credit notes are not implemented: invoices can be cancelled only if nothing was dispatched or paid.
* Overheads are entered per production run. Migrations: Flask-Migrate is configured, but setup uses `flask seed` / `flask init-db` (`create_all`).
* Docker files were not run in the build environment. Automated tests (17) pass on SQLite; MySQL was not tested here.

## Suggested commits
`init flask factory` > `models + auth` > `master data + BOM` > `purchase + stock ledger` > `production engine` > `orders + GST + dispatch` > `payments + costing` > `reports + exports` > `dashboard` > `intelligence` > `tests + docs`
