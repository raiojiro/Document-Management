from functools import wraps
from flask import session, redirect, url_for


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session["admin"] == 0:
            return redirect(url_for("main"))
        return f(*args, **kwargs)

    return decorated_function
