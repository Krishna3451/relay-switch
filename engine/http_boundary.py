"""Browser boundary for the trusted-operator, loopback-only demo servers.

This is not user authentication: local CLI callers are trusted. It rejects DNS
rebinding hosts and cross-origin browser requests before they reach controls.
"""
from urllib.parse import urlsplit

LOOPBACK_HOSTS = {"127.0.0.1", "localhost"}


def _origin(value):
    parsed = urlsplit(value)
    if (parsed.scheme != "http" or parsed.hostname not in LOOPBACK_HOSTS
            or parsed.username is not None or parsed.password is not None
            or parsed.path or parsed.query or parsed.fragment):
        return None
    return parsed.hostname, parsed.port or 80


def permitted_request(host, origin=None, *, method="GET", fetch_site=None):
    try:
        address = _origin("http://" + (host or ""))
        if address is None:
            return False
        if origin is not None and _origin(origin) != address:
            return False
        if method not in {"GET", "HEAD", "OPTIONS"} and fetch_site == "cross-site":
            return False
        return True
    except (ValueError, TypeError):
        return False
