"""This computer on the local network."""
import ipaddress
import socket


def _primary_address() -> str | None:
    """The address of the interface the computer goes out by. Connecting a UDP socket sends nothing: it only picks
    the route."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("10.255.255.255", 1))
            return sock.getsockname()[0]
    except OSError:
        return None


def local_addresses() -> list[str]:
    """The computer's private IPv4 addresses (192.168.x.x, 10.x.x.x...), the one it goes out by first."""
    found = [_primary_address()]
    try:
        found += [info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)]
    except OSError:
        pass
    addresses = []
    for address in found:
        try:
            ip = ipaddress.ip_address(address or "")
        except ValueError:
            continue
        if ip.is_private and not ip.is_loopback and not ip.is_link_local and address not in addresses:
            addresses.append(address)
    return addresses
