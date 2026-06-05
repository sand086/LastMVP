"""URL validator anti-SSRF (R45).

Reglas:
1. Sólo HTTPS (excepto en TESTS o si MYE_WEBHOOK_ALLOW_HTTP=1 — uso de tests/dev).
2. Resolver DNS y rechazar si IP cae en blocklist (loopback, privadas, link-local,
   AWS/GCP metadata).
3. Sólo puertos seguros: 443 default; >1024 con flag explícito.
4. Validación pre-create + por-request (defensa contra DNS rebinding).
"""
from __future__ import annotations
import ipaddress
import os
import socket
from urllib.parse import urlparse

# Rangos prohibidos. ipaddress.ip_address.is_private cubre RFC1918 + loopback +
# link-local; agregamos AWS metadata y GCP metadata explícitamente para claridad.
_EXTRA_BLOCKED_IPS = {
    "169.254.169.254",   # AWS / GCP metadata
    "100.100.100.200",   # Alibaba metadata
    "metadata.google.internal",
}

ALLOWED_PORTS_DEFAULT = {443}


class SsrfBlocked(Exception):
    """Raised when URL fails anti-SSRF checks."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _is_private_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # nombres / IPs inválidas → tratar como privadas
    if ip.is_private or ip.is_loopback or ip.is_link_local:
        return True
    if ip.is_multicast or ip.is_reserved or ip.is_unspecified:
        return True
    return False


def _allow_http() -> bool:
    return os.environ["MYE_WEBHOOK_ALLOW_HTTP"] == "1"


def validate_static(url: str, *, allow_extra_ports: bool = False) -> None:
    """Validación estática (sin DNS). Llamada al CREAR/UPDATE suscripción.

    Levanta `SsrfBlocked` si el URL no es elegible.
    """
    if not url or len(url) > 2000:
        raise SsrfBlocked("ENDPOINT_INVALID", "URL vacío o demasiado largo.")
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("https", "http"):
        raise SsrfBlocked("ENDPOINT_SCHEME_INVALID",
                          "Sólo HTTP/HTTPS permitido.")
    if parsed.scheme == "http" and not _allow_http():
        raise SsrfBlocked("ENDPOINT_HTTP_DISALLOWED",
                          "Sólo HTTPS permitido (R45).")
    host = (parsed.hostname or "").lower()
    if not host:
        raise SsrfBlocked("ENDPOINT_HOST_MISSING", "Host ausente.")
    if host in {"localhost", "0.0.0.0", "::1"} or host in _EXTRA_BLOCKED_IPS:
        raise SsrfBlocked("ENDPOINT_PRIVATE_IP",
                          f"Host bloqueado: {host}.")
    # Si host es IP literal, validar directamente
    try:
        ipaddress.ip_address(host)
        if _is_private_ip(host):
            raise SsrfBlocked("ENDPOINT_PRIVATE_IP",
                              f"IP literal privada/reservada: {host}.")
    except ValueError:
        pass  # nombre DNS — se valida en validate_runtime
    # Puertos
    port = parsed.port
    if port is not None:
        if port == 443 or (allow_extra_ports and port > 1024):
            pass
        else:
            raise SsrfBlocked("ENDPOINT_PORT_DISALLOWED",
                              f"Puerto {port} no permitido (sólo 443 o >1024 con flag).")


def resolve_runtime(url: str) -> str:
    """Resuelve DNS y devuelve el IP usado. Levanta SsrfBlocked si privado.

    Llamada ANTES de cada POST (defensa contra DNS rebinding).
    """
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not host:
        raise SsrfBlocked("ENDPOINT_HOST_MISSING", "Host ausente.")
    # Si es IP literal, no DNS lookup necesario
    try:
        ipaddress.ip_address(host)
        if _is_private_ip(host):
            raise SsrfBlocked("ENDPOINT_PRIVATE_IP",
                              f"IP literal privada: {host}.")
        return host
    except ValueError:
        pass
    # Lookup DNS A/AAAA
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise SsrfBlocked("ENDPOINT_DNS_FAIL",
                          f"DNS no resuelto: {e}.") from e
    seen: list[str] = []
    for fam, _t, _p, _c, sockaddr in infos:
        ip = sockaddr[0]
        seen.append(ip)
        if _is_private_ip(ip):
            raise SsrfBlocked("ENDPOINT_PRIVATE_IP",
                              f"DNS resolvió a IP privada: {host}→{ip}.")
        if ip in _EXTRA_BLOCKED_IPS:
            raise SsrfBlocked("ENDPOINT_PRIVATE_IP",
                              f"DNS resolvió a IP bloqueada: {host}→{ip}.")
    return seen[0] if seen else ""
