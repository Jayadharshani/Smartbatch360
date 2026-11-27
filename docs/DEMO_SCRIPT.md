# 8-minute demo script
Setup: `flask --app run seed` then `python run.py` (open http://127.0.0.1:5000). To see the final benchmark state instead run `flask --app run benchmark`.
1. (0:00) Login as **production**: Stock page (flour 100 kg...), Products > BOM view.
2. (0:45) Purchases: receive 60 kg flour at Rs 45 -> stock 160, avg cost 43.125.
3. (1:30) New Production Run: Murukku, 1 batch. Flour 40, oil 10.5, spice 1.2, cartons 9, good output 188, damaged 6. Save -> variance page: oil +5 %, yield -6 % flagged, QR code.
4. (3:00) Add labour 1200 and power 600 -> cost per packet Rs 31.14.
5. (3:45) Login as **salesman_a** on a phone-size window: New Order, Retailer A, 150 packets.
6. (4:30) Login as **admin**: open order, stock check, Approve, Generate GST invoice (CGST 187.50 + SGST 187.50), open PDF, Record dispatch 150 -> FG stock 88.
7. (5:30) **salesman_b**: order 120 for Distributor B. Admin order page shows shortage 32.
8. (6:00) Admin: Payments, Rs 4000 from Retailer A on the invoice -> outstanding 3875.
9. (6:30) **auditor**: Reports > GST summary, Stock ledger, export Excel/PDF; try to open /billing/payments POST -> read-only.
10. (7:15) **owner**: dashboard charts, low-stock/variance alerts, Intelligence page + ask "What is the current flour stock?".
