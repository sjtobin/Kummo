"""Session transport.

Tokens live in HttpOnly cookies and never reach page JavaScript. That is what keeps
the API transparent: a caller sees `/api/auth/*` and a cookie, never a bearer token
or an identity-provider URL.
"""

from fastapi import Request, Response

from ..config import get_settings
from .service import Session

SESSION_COOKIE = "kummo_session"
REFRESH_COOKIE = "kummo_refresh"
OAUTH_VERIFIER_COOKIE = "kummo_oauth_verifier"

# The refresh cookie outlives the access token; it is what /api/auth/refresh spends.
REFRESH_MAX_AGE = 60 * 60 * 24 * 30
# An OAuth round trip is a redirect or two — minutes, not hours.
OAUTH_STATE_MAX_AGE = 10 * 60


def _base_kwargs() -> dict:
    return {
        "httponly": True,
        "samesite": "lax",
        "path": "/",
        "secure": get_settings().cookie_secure,
    }


def set_session_cookies(response: Response, session: Session) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        session.access_token,
        max_age=session.expires_in,
        **_base_kwargs(),
    )
    response.set_cookie(
        REFRESH_COOKIE,
        session.refresh_token,
        max_age=REFRESH_MAX_AGE,
        **_base_kwargs(),
    )


def _clear(response: Response, name: str) -> None:
    """Expire a cookie with the same attributes it was set with.

    Browsers match a deletion on name, path and domain alone, so the flags are not
    strictly required — but keeping them identical is what lets the set and the clear
    stay in step if the attributes ever change (a `__Secure-` prefix, say).
    """
    response.delete_cookie(name, **_base_kwargs())


def clear_session_cookies(response: Response) -> None:
    for name in (SESSION_COOKIE, REFRESH_COOKIE):
        _clear(response, name)


def set_oauth_verifier(response: Response, code_verifier: str) -> None:
    """Carry the PKCE verifier across the provider redirect.

    Both halves live in one cookie because they share a lifetime and are always read
    and cleared together. `state` is generated from `token_urlsafe`, so it never
    contains the separator.
    """
    response.set_cookie(
        OAUTH_VERIFIER_COOKIE,
        code_verifier,
        max_age=OAUTH_STATE_MAX_AGE,
        **_base_kwargs(),
    )


def clear_oauth_verifier(response: Response) -> None:
    _clear(response, OAUTH_VERIFIER_COOKIE)


def read_access_token(request: Request) -> str:
    return request.cookies.get(SESSION_COOKIE, "")


def read_refresh_token(request: Request) -> str:
    return request.cookies.get(REFRESH_COOKIE, "")


def read_oauth_verifier(request: Request) -> str:
    """The code_verifier set before the redirect, or an empty string."""
    return request.cookies.get(OAUTH_VERIFIER_COOKIE, "")
