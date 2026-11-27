from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, current_user
from ..auth_utils import roles_required
from ..extensions import db
from ..models import User, ROLES, audit

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = User.query.filter_by(username=request.form.get("username", "").strip()).first()
        if u and u.is_active and u.check_password(request.form.get("password", "")):
            login_user(u)
            return redirect(url_for("main.home"))
        flash("Invalid username or password", "danger")
    return render_template("login.html")


@bp.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


@bp.route("/users", methods=["GET", "POST"])
@roles_required("admin")
def users():
    if request.method == "POST":
        f = request.form
        try:
            if f["role"] not in ROLES or len(f["password"]) < 6:
                raise ValueError("Valid role and password (min 6 chars) required")
            if User.query.filter_by(username=f["username"]).first():
                raise ValueError("Username already exists")
            u = User(username=f["username"].strip(), full_name=f["full_name"].strip(), role=f["role"])
            u.set_password(f["password"])
            db.session.add(u)
            audit(current_user.id, "USER_CREATE", u.username)
            db.session.commit()
            flash("User created", "success")
        except (ValueError, KeyError) as e:
            db.session.rollback()
            flash(str(e), "danger")
    return render_template("users.html", users=User.query.all(), roles=ROLES)
