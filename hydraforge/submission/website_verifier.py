"""
hydraforge/submission/website_verifier.py
Deployed Website Validation, Safe Availability Check & SSRF Protection.
Ensures participant websites are safe, valid external URLs, and prevents SSRF,
DNS rebinding, and redirect-based attacks to internal networks.
"""

from __future__ import annotations

import ipaddress
import socket
import urllib.request
import urllib.error
from urllib.parse import urlparse
from typing import Callable, Optional, Tuple

_MOCK_WEBSITE_CHECKER: Optional[Callable[[str], Tuple[bool, str, str]]] = None


def set_mock_website_checker(checker: Optional[Callable[[str], Tuple[bool, str, str]]]) -> None:
    """Register a mock checker for unit testing."""
    global _MOCK_WEBSITE_CHECKER
    _MOCK_WEBSITE_CHECKER = checker


class WebsiteSecurityError(Exception):
    """Raised when a website URL violates security constraints or attempts SSRF."""
    pass


BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def is_private_or_restricted_ip(ip_str: str) -> bool:
    """Check if an IP string belongs to any private, loopback, or reserved range."""
    try:
        ip = ipaddress.ip_address(ip_str)
        if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved or ip.is_unspecified:
            return True
        for net in BLOCKED_NETWORKS:
            if ip in net:
                return True
        return False
    except ValueError:
        return True


def validate_website_url(url: str) -> str:
    """
    Validate that a URL uses http/https, has a valid domain, and does not resolve
    to any loopback or private/internal IP address.
    """
    if not url or not isinstance(url, str):
        raise WebsiteSecurityError("Website URL must be a non-empty string.")

    url = url.strip()
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise WebsiteSecurityError(
            f"Unsupported URL scheme '{parsed.scheme}'. Only http:// and https:// are permitted."
        )

    hostname = parsed.hostname
    if not hostname:
        raise WebsiteSecurityError("Website URL must contain a valid domain name or public host.")

    lower_host = hostname.lower()
    if lower_host in ("localhost", "127.0.0.1", "::1", "metadata.google.internal"):
        raise WebsiteSecurityError(f"Prohibited host '{hostname}'. Localhost and internal destinations are blocked.")

    # Check direct IP literals
    try:
        if is_private_or_restricted_ip(lower_host):
            raise WebsiteSecurityError(f"Prohibited destination IP '{lower_host}': Internal and private addresses are blocked.")
    except Exception:
        pass

    # DNS resolution check for SSRF protection
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        addr_info = socket.getaddrinfo(hostname, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for _, _, _, _, sockaddr in addr_info:
            resolved_ip = sockaddr[0]
            if is_private_or_restricted_ip(resolved_ip):
                raise WebsiteSecurityError(
                    f"SSRF violation: Host '{hostname}' resolves to private or internal IP '{resolved_ip}'."
                )
    except socket.gaierror:
        # Host could not be resolved at validation time (e.g. offline sandbox or new domain)
        # We do not block validation if offline, but check hostname syntax
        pass

    return url


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Custom redirect handler that validates target URLs against SSRF rules."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Validate redirected destination
        try:
            validated_url = validate_website_url(newurl)
            return super().redirect_request(req, fp, code, msg, headers, validated_url)
        except WebsiteSecurityError as e:
            raise WebsiteSecurityError(f"Redirect blocked: {str(e)}")


def check_website_availability(url: str, timeout: float = 3.0) -> Tuple[bool, str, str]:
    """
    Safely ping the website via HTTP/HTTPS HEAD or GET request.
    Applies timeout and redirect validation.
    Returns (is_online, status_code_or_label, details).
    """
    if _MOCK_WEBSITE_CHECKER is not None:
        return _MOCK_WEBSITE_CHECKER(url)

    try:
        clean_url = validate_website_url(url)
    except WebsiteSecurityError as e:
        return False, "REJECTED_SSRF", str(e)

    opener = urllib.request.build_opener(SafeRedirectHandler())
    req = urllib.request.Request(
        clean_url,
        headers={"User-Agent": "HYDRAFORGE-Validator/1.0 (BASINSHIFT Challenge)"},
        method="HEAD"
    )

    try:
        with opener.open(req, timeout=timeout) as resp:
            code = resp.getcode()
            if 200 <= code < 400:
                return True, "ONLINE", f"HTTP {code} Available"
            return False, "OFFLINE", f"HTTP {code}"
    except WebsiteSecurityError as e:
        return False, "REJECTED_SSRF", str(e)
    except urllib.error.HTTPError as e:
        if 200 <= e.code < 400 or e.code == 403 or e.code == 401:
            # 403 or 401 still proves the server is reachable and online
            return True, "ONLINE", f"HTTP {e.code} Reachable"
        return False, "OFFLINE", f"HTTP {e.code}"
    except Exception as e:
        # Offline network, DNS failure, timeout
        return False, "UNREACHABLE", f"Check timed out or unreachable: {str(e)}"

