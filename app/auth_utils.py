from functools import wraps
from flask import abort
from flask_login import current_user, login_required


def roles_required(*roles):
    """Block a route unless the logged-in user has one of the roles (so changing the URL does not help)."""
    def deco(fn):
        @wraps(fn)
        @login_required
        def wrapper(*a, **k):
            if current_user.role not in roles:
                abort(403)
            return fn(*a, **k)
        return wrapper
    return deco
