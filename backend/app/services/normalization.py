from __future__ import annotations

import re
import unicodedata

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_LEVEL_TOKEN_RE = re.compile(r"(?:[1-9]|l[1-9])")
_EMPLOYMENT_PHRASES = (
    re.compile(r"\bfull[-\s]?time\b"),
    re.compile(r"\bpart[-\s]?time\b"),
    re.compile(r"\bon[-\s]?site\b"),
)
_TOKEN_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "backend": ("back", "end"),
    "frontend": ("front", "end"),
    "fullstack": ("full", "stack"),
    "ml": ("machine", "learning"),
    "sde": ("software", "engineer"),
    "sre": ("site", "reliability", "engineer"),
    "swe": ("software", "engineer"),
}
_DROP_TOKENS = frozenset(
    {
        "apprentice",
        "associate",
        "entry",
        "grad",
        "graduate",
        "hybrid",
        "intern",
        "internship",
        "jr",
        "junior",
        "lead",
        "level",
        "new",
        "onsite",
        "principal",
        "remote",
        "senior",
        "sr",
        "staff",
    },
)

type _BaseRole = tuple[frozenset[str], tuple[str, ...], frozenset[str]]

_BASE_ROLES: tuple[_BaseRole, ...] = (
    (
        frozenset({"machine", "learning", "engineer"}),
        ("machine", "learning", "engineer"),
        frozenset({"machine", "learning", "engineer"}),
    ),
    (
        frozenset({"software", "engineer"}),
        ("software", "engineer"),
        frozenset({"developer", "development", "engineer", "software"}),
    ),
    (
        frozenset({"data", "scientist"}),
        ("data", "scientist"),
        frozenset({"data", "scientist"}),
    ),
    (
        frozenset({"data", "engineer"}),
        ("data", "engineer"),
        frozenset({"data", "engineer"}),
    ),
    (
        frozenset({"product", "manager"}),
        ("product", "manager"),
        frozenset({"product", "manager"}),
    ),
    (
        frozenset({"project", "manager"}),
        ("project", "manager"),
        frozenset({"project", "manager"}),
    ),
)


def normalize_role_title(role_title: str | None) -> str | None:
    """Return a deterministic grouping key for a role title."""
    if role_title is None:
        return None

    tokens = _normalize_tokens(role_title)
    if not tokens:
        return None

    base_role = _select_base_role(tokens)
    if base_role is None:
        return " ".join(tokens)

    _required_tokens, base_tokens, consumed_tokens = base_role
    descriptor_tokens = [token for token in tokens if token not in consumed_tokens]
    return " ".join(_dedupe_tokens((*descriptor_tokens, *base_tokens)))


def _normalize_tokens(role_title: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKD", role_title)
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower().replace("&", " and ")
    for phrase in _EMPLOYMENT_PHRASES:
        normalized = phrase.sub(" ", normalized)

    raw_tokens = _NON_ALNUM_RE.sub(" ", normalized).split()
    expanded_tokens = _expand_tokens(raw_tokens)
    filtered_tokens = tuple(
        token
        for token in expanded_tokens
        if token not in _DROP_TOKENS and not _is_level_token(token)
    )
    return _coerce_developer_roles(_dedupe_tokens(filtered_tokens))


def _expand_tokens(tokens: list[str]) -> tuple[str, ...]:
    expanded: list[str] = []
    for token in tokens:
        expanded.extend(_TOKEN_EXPANSIONS.get(token, (token,)))
    return tuple(expanded)


def _coerce_developer_roles(tokens: tuple[str, ...]) -> tuple[str, ...]:
    token_set = set(tokens)
    has_software_context = (
        "software" in token_set
        or {"back", "end"}.issubset(token_set)
        or {"front", "end"}.issubset(token_set)
        or {"full", "stack"}.issubset(token_set)
    )
    if "developer" not in token_set or not has_software_context:
        return tokens

    coerced: list[str] = []
    for token in tokens:
        if token != "developer":
            coerced.append(token)
            continue
        if "software" not in token_set:
            coerced.append("software")
        coerced.append("engineer")
    return _dedupe_tokens(coerced)


def _select_base_role(tokens: tuple[str, ...]) -> _BaseRole | None:
    token_set = set(tokens)
    for base_role in _BASE_ROLES:
        required_tokens, _base_tokens, _consumed_tokens = base_role
        if required_tokens.issubset(token_set):
            return base_role
    return None


def _dedupe_tokens(tokens: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    deduped: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token in seen:
            continue
        deduped.append(token)
        seen.add(token)
    return tuple(deduped)


def _is_level_token(token: str) -> bool:
    return (
        token in {"i", "ii", "iii", "iv", "v", "vi"}
        or _LEVEL_TOKEN_RE.fullmatch(token) is not None
    )
