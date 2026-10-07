"""Canonical URL handling for discovery and identity matching."""

from __future__ import annotations

import re
from typing import Iterable
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit


DEFAULT_TRACKING_PARAMETERS = frozenset(
    {
        "fbclid",
        "gclid",
        "dclid",
        "msclkid",
        "mc_cid",
        "mc_eid",
        "ref",
        "referrer",
        "source",
        "campaign",
        "trackingid",
        "trk",
    }
)
REDIRECT_PARAMETERS = (
    "url",
    "u",
    "target",
    "dest",
    "destination",
    "redirect",
    "redirect_url",
    "redirect_uri",
)


def _looks_like_absolute_url(value: str) -> bool:
    candidate = unquote(value).strip()
    return candidate.startswith(("http://", "https://", "//"))


def _unwrap_redirect(url: str) -> str:
    parsed = urlsplit(url)
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    path_hint = parsed.path.casefold()
    host_hint = (parsed.hostname or "").casefold()
    likely_wrapper = any(
        marker in path_hint or marker in host_hint
        for marker in ("redirect", "out", "link", "click", "track")
    )
    for key, value in pairs:
        if key.casefold() in REDIRECT_PARAMETERS and _looks_like_absolute_url(value):
            if likely_wrapper or len(pairs) <= 3:
                target = unquote(value).strip()
                return "https:" + target if target.startswith("//") else target
    return url


def normalize_url(
    url: str | None,
    *,
    tracking_parameters: Iterable[str] = (),
    keep_parameters: Iterable[str] = (),
    unwrap_redirects: bool = True,
) -> str | None:
    """Return a stable HTTP(S) URL while retaining meaningful query fields.

    The function removes fragments, default ports, repeated path slashes, and
    common tracking parameters.  It never performs network requests.  Unknown
    query parameters are retained because applicant-tracking systems often use
    them as the actual requisition identifier.
    """

    if url is None:
        return None
    value = str(url).strip()
    if not value:
        return None
    value = re.sub(r"^(https?://)(?:https?://)+", r"\1", value, flags=re.I)
    if value.startswith("//"):
        value = "https:" + value
    if not re.match(r"^[a-z][a-z0-9+.-]*://", value, re.I):
        value = "https://" + value
    if unwrap_redirects:
        for _ in range(3):
            unwrapped = _unwrap_redirect(value)
            if unwrapped == value:
                break
            value = unwrapped

    parsed = urlsplit(value)
    scheme = parsed.scheme.casefold()
    if scheme not in {"http", "https"}:
        return value
    host = (parsed.hostname or "").casefold().rstrip(".")
    if not host:
        return None
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        pass
    try:
        port = parsed.port
    except ValueError:
        return None
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    else:
        netloc = host
    if parsed.username or parsed.password:
        # Credentials never belong in a canonical public job URL.
        netloc = host if port is None else netloc

    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")

    blocked = {item.casefold() for item in DEFAULT_TRACKING_PARAMETERS}
    blocked.update(item.casefold() for item in tracking_parameters)
    kept = {item.casefold() for item in keep_parameters}
    query: list[tuple[str, str]] = []
    for key, item in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.casefold()
        if lowered in kept:
            query.append((key, item))
            continue
        if lowered.startswith("utm_") or lowered in blocked:
            continue
        query.append((key, item))
    query.sort(key=lambda pair: (pair[0].casefold(), pair[1]))
    return urlunsplit((scheme, netloc, path, urlencode(query, doseq=True), ""))


canonicalize_url = normalize_url


def urls_equal(first: str | None, second: str | None) -> bool:
    left = normalize_url(first)
    right = normalize_url(second)
    return bool(left and right and left == right)
