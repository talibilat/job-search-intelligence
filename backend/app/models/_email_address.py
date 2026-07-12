from __future__ import annotations


def email_address_domain(value: object) -> str | None:
    """Return the lowercased domain of a formatted email address, if any."""

    if value is None:
        return None
    address = str(value).strip().rstrip(">")
    _local_part, separator, domain = address.rpartition("@")
    if not separator:
        return None
    normalized_domain = domain.strip().lower()
    return normalized_domain or None
