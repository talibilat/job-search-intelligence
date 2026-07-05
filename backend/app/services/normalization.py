from __future__ import annotations

import html
import re
import unicodedata

_DOMAIN_PREFIXES = frozenset({"careers", "jobs", "www"})
_DOMAIN_SUFFIXES = frozenset(
    {
        "ai",
        "app",
        "ca",
        "co",
        "com",
        "dev",
        "io",
        "net",
        "org",
        "uk",
        "us",
    }
)
_LEADING_ARTICLES = frozenset({"the"})
_LEGAL_SUFFIXES = frozenset(
    {
        "ag",
        "bv",
        "co",
        "corp",
        "corporation",
        "gmbh",
        "inc",
        "incorporated",
        "limited",
        "llc",
        "ltd",
        "nv",
        "plc",
        "pte",
        "pty",
        "sa",
        "sarl",
        "sas",
    }
)
_DOTTED_LEGAL_SUFFIX_TOKEN_SEQUENCES = tuple(
    tuple(suffix) for suffix in sorted(_LEGAL_SUFFIXES, key=len, reverse=True) if len(suffix) > 1
)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_LEVEL_TOKEN_RE = re.compile(r"(?:[1-9][0-9]*|e[0-9]+|ic[0-9]+|l[0-9]+|m[0-9]+)")
_EMPLOYMENT_PHRASES = (
    re.compile(r"\bfull[-\s]?time\b"),
    re.compile(r"\bremote[-\s]?eligible\b"),
    re.compile(r"\bpart[-\s]?time\b"),
    re.compile(r"\bwork[-\s]?from[-\s]?home\b"),
    re.compile(r"\bon[-\s]?site\b"),
    re.compile(r"\bin[-\s]?office\b"),
)
_PUNCTUATED_TOKEN_REPLACEMENTS = (
    (re.compile(r"(?<![a-z0-9])c\+\+(?![a-z0-9])"), " c plus plus "),
    (re.compile(r"(?<![a-z0-9])c#(?![a-z0-9])"), " c sharp "),
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
        "ca",
        "california",
        "canada",
        "entry",
        "england",
        "grad",
        "graduate",
        "hybrid",
        "intern",
        "internship",
        "kingdom",
        "francisco",
        "jr",
        "junior",
        "lead",
        "level",
        "london",
        "new",
        "ny",
        "nyc",
        "onsite",
        "principal",
        "remote",
        "san",
        "sf",
        "sfo",
        "senior",
        "sr",
        "staff",
        "states",
        "toronto",
        "uk",
        "united",
        "us",
        "usa",
        "wfh",
        "york",
    },
)

type _BaseRole = tuple[frozenset[str], tuple[str, ...], frozenset[str]]

_BASE_ROLES: tuple[_BaseRole, ...] = (
    (
        frozenset({"machine", "learning", "engineer"}),
        ("machine", "learning", "engineer"),
        frozenset({"machine", "learning", "software", "engineer"}),
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


def normalize_company_name(company: str) -> str:
    """Return a deterministic grouping key for extracted company names."""

    tokens = _company_tokens(company)
    if not tokens:
        return ""

    tokens = _drop_leading_terms(tokens, _LEADING_ARTICLES)
    if _looks_like_domain(company):
        tokens = _drop_leading_terms(tokens, _DOMAIN_PREFIXES)
        tokens = _drop_trailing_terms(tokens, _DOMAIN_SUFFIXES)
    tokens = _drop_trailing_legal_suffixes(tokens)

    return " ".join(tokens)


def normalize_role_title(role_title: str | None) -> str | None:
    """Return a deterministic grouping key for an extracted role title.

    The key folds casing, punctuation, seniority, title levels, common
    abbreviations, location noise, and work-arrangement phrases while retaining
    descriptors that distinguish role families.
    """
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


def _company_tokens(company: str) -> list[str]:
    normalized = _strip_combining_marks(html.unescape(company)).casefold()
    normalized = normalized.replace("&", " and ")
    chars = [char if char.isalnum() else " " for char in normalized]
    return "".join(chars).split()


def _strip_combining_marks(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _looks_like_domain(company: str) -> bool:
    return "." in company


def _drop_leading_terms(tokens: list[str], terms: frozenset[str]) -> list[str]:
    trimmed = list(tokens)
    while trimmed and trimmed[0] in terms:
        trimmed.pop(0)
    return trimmed


def _drop_trailing_terms(tokens: list[str], terms: frozenset[str]) -> list[str]:
    trimmed = list(tokens)
    while len(trimmed) > 1 and trimmed[-1] in terms:
        trimmed.pop()
    return trimmed


def _drop_trailing_legal_suffixes(tokens: list[str]) -> list[str]:
    trimmed = list(tokens)
    while len(trimmed) > 1:
        if trimmed[-1] in _LEGAL_SUFFIXES:
            trimmed.pop()
            continue

        dotted_suffix = _matching_trailing_dotted_legal_suffix(trimmed)
        if dotted_suffix is None:
            break
        del trimmed[-len(dotted_suffix) :]

    if len(trimmed) > 1 and trimmed[-1] == "and":
        trimmed.pop()
    return trimmed

def _matching_trailing_dotted_legal_suffix(tokens: list[str]) -> tuple[str, ...] | None:
    for suffix_tokens in _DOTTED_LEGAL_SUFFIX_TOKEN_SEQUENCES:
        trailing_tokens = tuple(tokens[-len(suffix_tokens) :])
        if len(tokens) > len(suffix_tokens) and trailing_tokens == suffix_tokens:
            return suffix_tokens
    return None


def _normalize_tokens(role_title: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKD", role_title)
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower().replace("&", " and ")
    for pattern, replacement in _PUNCTUATED_TOKEN_REPLACEMENTS:
        normalized = pattern.sub(replacement, normalized)
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
    if not {"developer", "engineer"}.intersection(token_set) or not has_software_context:
        return tokens

    coerced: list[str] = []
    for token in tokens:
        if token not in {"developer", "engineer"}:
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
        if token == "plus" and deduped[-1:] == ["plus"]:
            deduped.append(token)
            continue
        if token in seen:
            continue
        deduped.append(token)
        seen.add(token)
    return tuple(deduped)


def _is_level_token(token: str) -> bool:
    return token in {"i", "ii", "iii", "iv", "v", "vi"} or _LEVEL_TOKEN_RE.fullmatch(token) is not None
