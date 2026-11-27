"""Helpers: Decimal money maths, unit conversion, financial year."""
import math
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

POUCH_CODE = "POUCH"


def D(v):
    """Convert anything to Decimal safely (never via float arithmetic)."""
    if isinstance(v, Decimal):
        return v
    if v is None or v == "":
        return Decimal("0")
    return Decimal(str(v))


def money(v):
    return D(v).quantize(Decimal("0.01"), ROUND_HALF_UP)


def q3(v):
    return D(v).quantize(Decimal("0.001"), ROUND_HALF_UP)


def q4(v):
    return D(v).quantize(Decimal("0.0001"), ROUND_HALF_UP)


_FACTORS = {
    ("g", "kg"): Decimal("0.001"), ("kg", "g"): Decimal("1000"),
    ("ml", "l"): Decimal("0.001"), ("l", "ml"): Decimal("1000"),
}


def convert(qty, from_unit, to_unit):
    qty = D(qty)
    if from_unit == to_unit:
        return qty
    if (from_unit, to_unit) in _FACTORS:
        return qty * _FACTORS[(from_unit, to_unit)]
    if {from_unit, to_unit} <= {"piece", "packet"}:
        return qty  # 1 pouch = 1 packet
    raise ValueError(f"Cannot convert {from_unit} to {to_unit}")


def cartons_needed(packets, packets_per_carton):
    """Carton size is product specific, so it is passed in (never assumed)."""
    return Decimal(math.ceil(D(packets) / D(packets_per_carton)))


def financial_year(d):
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{str(start + 1)[2:]}"


def parse_date(s):
    if not s:
        return None
    if isinstance(s, (date, datetime)):
        return s
    return datetime.strptime(s, "%Y-%m-%d").date()
