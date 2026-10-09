DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 6677


def page_url(port: int = DEFAULT_PORT) -> str:
    return f"http://{DEFAULT_HOST}:{port}/"
