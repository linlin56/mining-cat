"""What every request goes through: the server only answers to this computer, and other websites open in the browser
can't drive its API."""
from urllib.parse import urlparse

from flask import jsonify, redirect, request

from miningcat.application import study_language

# Mutating requests must carry this header. A web page from another site can't add it without
# a CORS preflight, which this server never approves: it protects the local API from other tabs.
CSRF_HEADER = "X-MiningCat"
LOCAL_HOSTNAMES = {"localhost", "127.0.0.1", "::1"}
# Pages that need a language: without one, they send the user to the home page to choose it.
LANGUAGE_PAGES = ("/converter/", "/reader/", "/clipboard/", "/player/", "/settings/")


def guard():
    """before_request hook."""
    host = urlparse(f"//{request.host}").hostname or ""
    if host not in LOCAL_HOSTNAMES:
        return jsonify(error="MiningCat only answers on localhost."), 403
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get(CSRF_HEADER) != "1":
        return jsonify(error="Missing MiningCat header."), 403
    if request.method == "GET" and request.path.startswith(LANGUAGE_PAGES) and "/api/" not in request.path:
        if study_language.current() is None:
            return redirect(f"/?next={request.path}")
    return None
