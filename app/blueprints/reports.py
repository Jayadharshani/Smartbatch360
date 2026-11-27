from flask import Blueprint, render_template, request, abort
from ..auth_utils import roles_required
from ..exports import export
from ..services.reports import REPORTS
from ..utils import parse_date

bp = Blueprint("reports", __name__, url_prefix="/reports")


@bp.route("/")
@roles_required("admin", "auditor", "owner")
def index():
    return render_template("reports.html", reports=[(k, f(None, None)[0]) for k, f in REPORTS.items()])


@bp.route("/<key>")
@roles_required("admin", "auditor", "owner")
def view(key):
    fn = REPORTS.get(key) or abort(404)
    try:
        s, e = parse_date(request.args.get("start")), parse_date(request.args.get("end"))
    except ValueError:
        abort(400)
    title, headers, rows = fn(s, e)
    fmt = request.args.get("format")
    if fmt in ("csv", "xlsx", "pdf"):
        return export(title, headers, rows, fmt)
    return render_template("report_view.html", key=key, title=title, headers=headers, rows=rows,
                           start=request.args.get("start", ""), end=request.args.get("end", ""))
