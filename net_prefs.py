# Force IPv4 for DNS lookups (helps on some Windows/ISP setups)
import socket
import contextlib

@contextlib.contextmanager
def prefer_ipv4():
    original_getaddrinfo = socket.getaddrinfo
    def getaddrinfo_ipv4(host, port, family=0, type=0, proto=0, flags=0):
        if family == 0:
            family = socket.AF_INET
        return original_getaddrinfo(host, port, family, type, proto, flags)
    socket.getaddrinfo = getaddrinfo_ipv4
    try:
        yield
    finally:
        socket.getaddrinfo = original_getaddrinfo
