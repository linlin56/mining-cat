"""What every request goes through: the server only answers to this computer, and other websites open in the browser
can't drive its API. The e-reader's door (lan.py) only opens the e-reader's routes, with its token."""
from urllib.parse import urlparse

from flask import jsonify, redirect, request

from miningcat.application import ereader_link, study_language
from miningcat.interfaces.web.lan import LAN_REQUEST

# Mutating requests must carry this header. A web page from another site can't add it without
# a CORS preflight, which this server never approves: it protects the local API from other tabs.
CSRF_HEADER = "X-MiningCat"
LOCAL_HOSTNAMES = {"localhost", "127.0.0.1", "::1"}
# Pages that need a language: without one, they send the user to the home page to choose it.
LANGUAGE_PAGES = ("/converter/", "/reader/", "/clipboard/", "/inbox/", "/player/", "/settings/")
# What the e-reader may do through its door: look a word up, send it, and check that it reaches MiningCat.
LAN_ROUTES = {("POST", "/api/inbox"), ("POST", "/api/inbox/lookup"), ("GET", "/api/inbox/ping")}


def lan_guard():
    """The requests of the e-reader's door. Its token replaces the MiningCat header: like it, a web page can't add an
    Authorization header to another site's request without a CORS preflight."""
    if (request.method, request.path) not in LAN_ROUTES:
        return jsonify(error="Only the e-reader's routes answer on this port."), 403
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not ereader_link.check_token(token):
        return jsonify(title="E-reader", error="Wrong token: copy it from MiningCat's Settings › E-reader."), 401
    return None


def guard():
    """before_request hook."""
    if request.environ.get(LAN_REQUEST):
        return lan_guard()
    host = urlparse(f"//{request.host}").hostname or ""
    if host not in LOCAL_HOSTNAMES:
        return jsonify(error="MiningCat only answers on localhost."), 403
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get(CSRF_HEADER) != "1":
        return jsonify(error="Missing MiningCat header."), 403
    if request.method == "GET" and request.path.startswith(LANGUAGE_PAGES) and "/api/" not in request.path:
        if study_language.current() is None:
            return redirect(f"/?next={request.path}")
    return None
