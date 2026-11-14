"""URL and CSP policy for remotely loaded coordinate files."""

import os
from urllib.parse import urlsplit

DEFAULT_COORDINATE_ORIGINS = (
    "https://www.ebi.ac.uk",
    "https://alphafold.ebi.ac.uk",
)


def _origin(value: str) -> str:
    try:
        parts = urlsplit(value.strip())
        port = parts.port
    except ValueError as error:
        raise ValueError("Coordinate origins must be valid HTTPS origins") from error
    if (
        parts.scheme.lower() != "https"
        or not parts.hostname
        or "*" in parts.hostname
        or parts.username is not None
        or parts.password is not None
        or port not in (None, 443)
        or parts.path not in ("", "/")
        or parts.query
        or parts.fragment
    ):
        raise ValueError("Coordinate origins must be HTTPS origins without paths")
    return f"https://{parts.hostname.lower()}"


def allowed_coordinate_origins() -> tuple[str, ...]:
    """Return built-in and explicitly configured coordinate origins.

    Custom providers must opt in with PDBe_MCP_STRUCTURE_ORIGINS, a
    comma-separated list of HTTPS origins. Wildcards, paths and non-default
    ports are deliberately unsupported.
    """

    configured = os.getenv("PDBe_MCP_STRUCTURE_ORIGINS", "")
    origins = list(DEFAULT_COORDINATE_ORIGINS)
    if configured.strip():
        origins.extend(_origin(item) for item in configured.split(",") if item.strip())
    return tuple(dict.fromkeys(_origin(item) for item in origins))


def validate_coordinate_url(value: str) -> str:
    """Validate a coordinate URL against the exact configured origin list."""

    value = value.strip()
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError as error:
        raise ValueError("Coordinate URL must be a valid HTTPS URL") from error
    if (
        parts.scheme.lower() != "https"
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or port not in (None, 443)
        or parts.query
        or parts.fragment
    ):
        raise ValueError(
            "Coordinate URL must be HTTPS without credentials, query parameters, or a fragment"
        )
    origin = _origin(f"https://{parts.hostname}")
    if origin not in allowed_coordinate_origins():
        raise ValueError(
            f"Coordinate URL origin {origin} is not configured; add it to "
            "PDBe_MCP_STRUCTURE_ORIGINS"
        )
    return value


def app_connect_domains() -> list[str]:
    """CSP domains required by the App, including configured coordinate hosts."""

    domains = [
        "https://www.ebi.ac.uk",
        "https://ebi.ac.uk",
        "https://*.ebi.ac.uk",
        "https://wwpdb.org",
        "https://*.wwpdb.org",
    ]
    domains.extend(allowed_coordinate_origins())
    return list(dict.fromkeys(domains))
