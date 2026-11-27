from flask import Blueprint, render_template, request
from ..auth_utils import roles_required
from ..services import intelligence as ai

bp = Blueprint("intelligence", __name__, url_prefix="/intelligence")


@bp.route("/", methods=["GET", "POST"])
@roles_required("admin", "production", "auditor", "owner")
def index():
    q = request.form.get("q", "").strip()
    found, repeats = ai.anomalies()
    loss_rows, loss_total = ai.loss_impact()
    return render_template("intel.html", recs=ai.recommend_production(), found=found, repeats=repeats,
                           loss=loss_rows, loss_total=loss_total, q=q, ans=ai.answer(q) if q else None)
