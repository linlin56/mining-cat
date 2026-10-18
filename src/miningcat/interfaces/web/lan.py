"""The e-reader's door: the same Flask app, also served on 0.0.0.0:<port> while Settings › E-reader allows it. Its
requests are marked in their WSGI environ (no HTTP header can set that key), and security.guard only lets the
e-reader's routes through them, with the token. The app itself stays on 127.0.0.1."""
import socket
import threading

from flask import Flask
from werkzeug.serving import BaseWSGIServer, make_server

# The WSGI environ key of the requests that came through this door.
LAN_REQUEST = "miningcat.lan"


class LanListener:
    def __init__(self, app: Flask):
        self._app = app
        self._lock = threading.Lock()
        self._server: BaseWSGIServer | None = None
        self.error: str | None = None

    def _wsgi(self, environ, start_response):
        environ[LAN_REQUEST] = True
        return self._app(environ, start_response)

    @property
    def port(self) -> int | None:
        return self._server.server_port if self._server is not None else None

    def apply(self, config: dict) -> None:
        """Opens the door on config["port"] when config["enabled"], closes it otherwise."""
        with self._lock:
            if self._server is not None and config["enabled"] and self._server.server_port == config["port"]:
                return
            self._stop()
            self.error = None
            if not config["enabled"]:
                return
            # The socket is opened here: werkzeug exits the process when it can't open one itself.
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    sock.bind(("0.0.0.0", config["port"]))
                    sock.listen(128)
                    self._server = make_server("0.0.0.0", config["port"], self._wsgi, threaded=True, fd=sock.fileno())
            except OSError as exc:  # the port is taken...
                self.error = f"Port {config['port']} can't be opened: {exc.strerror or exc}"
                return
            threading.Thread(target=self._server.serve_forever, name="miningcat-lan", daemon=True).start()

    def stop(self) -> None:
        with self._lock:
            self._stop()

    def _stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    def state(self) -> dict:
        return {"listening": self._server is not None, "error": self.error}
