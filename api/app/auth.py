"""Shared-secret checks for the routes that are not public (ADR 0006, ADR 0007)."""

import hmac

from fastapi import Header, HTTPException, status

from .config import settings


def bearer_matches(authorization: str | None, token: str) -> bool:
    """Whether an ``Authorization: Bearer <token>`` header carries ``token``."""
    scheme, _, given = (authorization or "").partition(" ")
    # compare_digest: the time taken does not reveal how much of it matched.
    return scheme.lower() == "bearer" and hmac.compare_digest(given.encode(), token.encode())


def unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_kitchen(authorization: str | None = Header(default=None, include_in_schema=False)) -> None:
    """Only the kitchen dashboard may list orders and change their status.

    The dashboard never holds the token itself: Caddy checks the kitchen login
    at /kitchen and adds the token to the requests it forwards (ADR 0007).
    """
    token = settings.kitchen_api_token
    if token is None:
        # A setup problem on the server, not the caller's fault.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Kitchen access is not set up on this server (KITCHEN_API_TOKEN).",
        )
    if not bearer_matches(authorization, token):
        raise unauthorized()
