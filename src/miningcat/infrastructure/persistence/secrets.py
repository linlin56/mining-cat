"""Secrets kept in the database (the user's API keys), encrypted with Fernet (AES, from the cryptography package) and
a key of their own: user/secret.key, made the first time, readable by the user only. The database alone (a backup,
library/ shared or copied) doesn't give them. It isn't a safe: whoever can read both files can read the secrets."""
import os

from miningcat.config.paths import paths

PREFIX = "fernet:"


class SecretError(RuntimeError):
    pass


def _fernet(create: bool):
    from cryptography.fernet import Fernet
    path = paths.secret_key
    if not path.exists():
        if not create:
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as file:
            file.write(Fernet.generate_key())
    return Fernet(path.read_bytes().strip())


def is_encrypted(value: str) -> bool:
    return value.startswith(PREFIX)


def encrypt(secret: str) -> str:
    """What the database keeps of a secret ("" stays "")."""
    if not secret:
        return ""
    return PREFIX + _fernet(create=True).encrypt(secret.encode()).decode()


def decrypt(value: str) -> str:
    """The secret the database keeps. A value written before secrets were encrypted is given as it is."""
    if not is_encrypted(value):
        return value
    from cryptography.fernet import InvalidToken
    fernet = _fernet(create=False)
    if fernet is None:
        raise SecretError(f"{paths.secret_key} is missing: the saved key can't be read.")
    try:
        return fernet.decrypt(value[len(PREFIX):].encode()).decode()
    except (InvalidToken, ValueError) as exc:
        raise SecretError(f"The saved key can't be read with {paths.secret_key}.") from exc
