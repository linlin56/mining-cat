"""The e-reader's access to MiningCat over the local network (Settings › E-reader): off by default. When it's on, the
server also answers on another port to every device of the network, but only the e-reader's routes (sending a word
to the inbox), and only with the token the user enters in the KOReader plugin.
The token is kept encrypted (infrastructure/persistence/secrets.py)."""
import hmac
import secrets as random

from miningcat.infrastructure.persistence import secrets
from miningcat.infrastructure.persistence.settings_store import settings
from miningcat.infrastructure.system.network import local_addresses

SETTING = "ereader_link"
DEFAULT_PORT = 5051
# Typed on an e-reader's keyboard: lowercase letters and digits, without those that look alike (l/1, o/0, i).
TOKEN_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
TOKEN_LENGTH = 10


class EreaderLinkError(Exception):
    """A setting of the e-reader's access that can't be saved: shown to the user as is."""


def _new_token() -> str:
    token = "".join(random.choice(TOKEN_ALPHABET) for _ in range(TOKEN_LENGTH))
    return f"{token[:5]}-{token[5:]}"


def _stored() -> dict:
    stored = settings.get(SETTING, {})
    return stored if isinstance(stored, dict) else {}


def get_config() -> dict:
    """{enabled, port, token}. The token is made the first time."""
    stored = _stored()
    try:
        token = secrets.decrypt(str(stored.get("token") or ""))
    except secrets.SecretError:
        token = ""
    if not token:
        token = _new_token()
        settings.set(SETTING, {**stored, "token": secrets.encrypt(token)})
    port = stored.get("port")
    return {
        "enabled": stored.get("enabled") is True,
        "port": port if isinstance(port, int) else DEFAULT_PORT,
        "token": token,
    }


def save_config(values: dict) -> dict:
    """Changes `enabled` and `port` (those given)."""
    config = get_config()
    if "enabled" in values:
        config["enabled"] = values["enabled"] is True
    if "port" in values:
        port = values["port"]
        if isinstance(port, str) and port.strip().isdigit():
            port = int(port)
        if not isinstance(port, int) or isinstance(port, bool) or not 1024 <= port <= 65535:
            raise EreaderLinkError("The port is a number between 1024 and 65535.")
        config["port"] = port
    settings.set(SETTING, {"enabled": config["enabled"], "port": config["port"], "token": secrets.encrypt(config["token"])})
    return config


def renew_token() -> dict:
    """A new token: the e-reader needs it to send words again."""
    config = get_config()
    config["token"] = _new_token()
    settings.set(SETTING, {"enabled": config["enabled"], "port": config["port"], "token": secrets.encrypt(config["token"])})
    return config


def check_token(given: str) -> bool:
    token = get_config()["token"]
    return bool(given) and hmac.compare_digest(given.strip().lower().encode(), token.encode())


def addresses(port: int) -> list[str]:
    """What the user enters in the KOReader plugin: this computer's addresses on the local network."""
    return [f"http://{address}:{port}" for address in local_addresses()]
