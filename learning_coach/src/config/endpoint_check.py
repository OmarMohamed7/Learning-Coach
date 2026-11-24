"""Checks for a user-supplied LLM endpoint before the server calls it."""
import ipaddress
import socket
from urllib.parse import urlsplit

import httpx


def public_https_error(url: str) -> str | None:
    """None if `url` is https and resolves only to public addresses; otherwise why not."""
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        return "the URL must start with https://"
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or 443, proto=socket.IPPROTO_TCP)
    except OSError:
        return f"can't resolve {parts.hostname}"
    if not all(ipaddress.ip_address(info[4][0]).is_global for info in infos):
        return "private and local addresses are not allowed"
    return None


async def reachability_error(base_url: str, model: str) -> str | None:
    """None if the endpoint answers and (when it lists models) offers `model`; otherwise why not."""
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
            resp = await client.get(base_url.rstrip("/") + "/models")
    except httpx.HTTPError as e:
        return f"couldn't connect ({type(e).__name__})"
    if resp.status_code >= 500 or resp.status_code in (401, 403):
        return f"the server answered HTTP {resp.status_code}"
    try:
        names = [m.get("id") for m in resp.json().get("data", [])]
    except ValueError:
        return None
    if names and model not in names:
        return f"model '{model}' not found there. Available: {', '.join(n for n in names if n)[:200]}"
    return None
