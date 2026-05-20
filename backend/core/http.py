"""HTTP request helpers."""
from __future__ import annotations
from fastapi import Request


def get_client_ip(request: Request) -> str:
    """Return the real client IP, honoring X-Forwarded-For when behind a proxy.

    Many platforms (Cloudflare, k8s ingress) terminate TLS upstream and set
    ``request.client.host`` to the hop IP — making per-IP rate limiting
    effectively useless. We trust the *first* entry of X-Forwarded-For when
    present; otherwise we fall back to the socket peer.
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "anon"
