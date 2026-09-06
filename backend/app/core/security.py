"""Authentication boundary.

This is intentionally minimal: a static bearer-token -> user table read from
settings (`DEV_API_KEYS`), producing a stable UUID per user email. It exists
so every downstream query can be tenant-filtered on a real `owner_id`, which
is the property this project actually cares about demonstrating (see
`app.rag.retrieval` and the security checklist in blueprint section 19).

Swap this module for real OAuth2/JWT/session auth before this is anything
but a portfolio/demo deployment -- nothing else in the codebase assumes a
particular auth mechanism, since everything downstream only depends on
`User.id` and `User.email`.
"""
import hashlib
import uuid
from dataclasses import dataclass
from functools import lru_cache

from fastapi import Depends, Header, HTTPException, status

from app.core.config import Settings, get_settings


@dataclass(frozen=True)
class User:
    id: uuid.UUID
    email: str


def email_to_user_id(email: str) -> uuid.UUID:
    """Deterministic UUID5 so the same dev user always maps to the same id
    across restarts, without persisting a separate users table for v1.
    Public because evaluation/run_eval.py and load-tests/query_vs_ingestion.py
    need to resolve a dev email to the same owner_id the API would use.
    """
    return uuid.uuid5(uuid.NAMESPACE_DNS, f"atlasdocs.user.{email}")


# Backwards-compatible private alias used within this module.
_email_to_uuid = email_to_user_id


@lru_cache
def _load_api_keys(raw: str) -> dict[str, User]:
    table: dict[str, User] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair or ":" not in pair:
            continue
        token, email = pair.split(":", 1)
        table[token.strip()] = User(id=_email_to_uuid(email.strip()), email=email.strip())
    return table


def current_user(
    authorization: str = Header(default=""),
    settings: Settings = Depends(get_settings),
) -> User:
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    users = _load_api_keys(settings.dev_api_keys)
    user = users.get(token)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
    return user


def hash_for_logs(value: str) -> str:
    """Never log raw user identifiers; log a stable short hash instead."""
    return hashlib.sha256(value.encode()).hexdigest()[:12]
