"""The only module that knows the identity provider is Supabase.

Everything above this layer works with `Session`, `OAuthRedirect` and the errors in
`errors.py`, so the `/api/auth/*` surface stays transparent: callers never see a
Supabase URL, a provider error code, or a token.

OAuth uses PKCE with the verifier held in a short-lived cookie rather than in the
client's in-memory storage, because the authorize request and the callback are two
separate HTTP requests handled by (potentially) different workers.
"""

import base64
import hashlib
import logging
import secrets
from dataclasses import dataclass
from urllib.parse import urlencode
from uuid import UUID

import httpx
from supabase import AsyncClient, AsyncClientOptions, create_async_client
from supabase_auth.errors import AuthError as ProviderAuthError

from ..config import get_settings
from .errors import (
    AuthError,
    ConfirmationLinkInvalid,
    EmailAlreadyRegistered,
    EmailConfirmationRequired,
    EmailNotConfirmed,
    InvalidCredentials,
    OAuthExchangeFailed,
    ProviderUnavailable,
    RateLimited,
    SessionExpired,
    WeakPassword,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Session:
    """A verified identity plus the tokens that prove it."""

    access_token: str
    refresh_token: str
    expires_in: int
    auth_user_id: UUID
    email: str
    # Present on OAuth signups: whatever the IDP told us about the person.
    full_name: str | None = None


@dataclass(frozen=True)
class PendingIdentity:
    """An account that exists at the provider but has no session yet.

    Signing up while the provider requires email confirmation creates the identity and
    stops there. The auth user id is already final, so the profile row can be written
    immediately — only the cookies wait for the confirmation link.
    """

    auth_user_id: UUID
    email: str


@dataclass(frozen=True)
class OAuthRedirect:
    url: str
    code_verifier: str


async def _client() -> AsyncClient:
    """A fresh client per operation: session state must not leak between requests."""
    settings = get_settings()
    return await create_async_client(
        settings.supabase_url,
        settings.supabase_api_key,
        options=AsyncClientOptions(
            flow_type="pkce",
            auto_refresh_token=False,
            persist_session=False,
        ),
    )


def _to_session(response) -> Session:
    session = getattr(response, "session", None)
    if session is None or session.access_token is None:
        raise EmailConfirmationRequired(
            "The identity provider issued no session for this account."
        )
    user = session.user
    metadata = user.user_metadata or {}
    return Session(
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        expires_in=session.expires_in or 3600,
        auth_user_id=UUID(str(user.id)),
        email=user.email or "",
        full_name=metadata.get("full_name") or metadata.get("name"),
    )


def _to_pending(response) -> PendingIdentity:
    user = getattr(response, "user", None)
    if user is None or user.id is None:
        raise EmailConfirmationRequired(
            "The identity provider issued neither a session nor an account."
        )
    return PendingIdentity(auth_user_id=UUID(str(user.id)), email=user.email or "")


def _translate(error: ProviderAuthError) -> AuthError:
    code = getattr(error, "code", None) or ""
    message = str(getattr(error, "message", error))
    if code == "email_not_confirmed":
        return EmailNotConfirmed("This address has not been confirmed yet.")
    if code in {"over_email_send_rate_limit", "over_request_rate_limit"}:
        return RateLimited("Too many attempts. Try again in a moment.")
    if code in {"user_already_exists", "email_exists"}:
        return EmailAlreadyRegistered("That email address already has an account.")
    if code == "weak_password":
        # The provider's own wording would name it in a 400 body; keep ours.
        logger.info("Password rejected by the provider policy: %s", message)
        return WeakPassword("That password is too weak. Choose a longer one.")
    if code in {"invalid_credentials", "invalid_grant"}:
        return InvalidCredentials("Wrong email or password.")
    if "Invalid login credentials" in message:
        return InvalidCredentials("Wrong email or password.")
    if "Email not confirmed" in message:
        return EmailNotConfirmed("This address has not been confirmed yet.")
    logger.warning("Unmapped provider auth error (code=%s): %s", code, message)
    # A rejection we have no name for is still a rejection: the caller sent something
    # the provider refused, which is a 400. Only `_unavailable` means "not reachable".
    return AuthError(message)


def _unavailable(error: Exception) -> AuthError:
    """A transport failure is not an authentication answer — it is a 502."""
    logger.warning("Identity provider unreachable: %s", error)
    return ProviderUnavailable("The identity provider is unavailable.")


async def sign_up(email: str, password: str) -> Session | PendingIdentity:
    """Create the identity.

    Two legitimate outcomes, depending on the provider's confirmation setting: a live
    session, or an identity waiting for its confirmation link. Both carry the auth user
    id, which is what the profile row is linked on.
    """
    client = await _client()
    try:
        response = await client.auth.sign_up({"email": email, "password": password})
    except ProviderAuthError as error:
        raise _translate(error) from error
    except httpx.HTTPError as error:
        raise _unavailable(error) from error

    session = getattr(response, "session", None)
    if session is None or session.access_token is None:
        return _to_pending(response)
    return _to_session(response)


async def confirm_email(token_hash: str) -> Session:
    """Redeem the token hash from a confirmation email for a real session.

    Server-side on purpose: the alternative — letting the provider redirect straight to
    the browser — hands the tokens to page JS, which is exactly what the cookie
    transport exists to avoid.
    """
    client = await _client()
    try:
        response = await client.auth.verify_otp(
            {"token_hash": token_hash, "type": "email"}
        )
    except ProviderAuthError as error:
        raise ConfirmationLinkInvalid("The confirmation link is no longer valid.") from error
    except httpx.HTTPError as error:
        raise _unavailable(error) from error
    return _to_session(response)


async def resend_confirmation(email: str) -> None:
    """Send the confirmation email again.

    Whether the address has an account is not ours to disclose, so anything but a
    throttle is swallowed: the caller is told the same thing either way.
    """
    client = await _client()
    try:
        await client.auth.resend({"type": "signup", "email": email})
    except ProviderAuthError as error:
        translated = _translate(error)
        if isinstance(translated, RateLimited):
            raise translated from error
        logger.info("Confirmation resend declined by the provider: %s", translated)
    except httpx.HTTPError as error:
        raise _unavailable(error) from error


async def sign_in(email: str, password: str) -> Session:
    client = await _client()
    try:
        response = await client.auth.sign_in_with_password(
            {"email": email, "password": password}
        )
    except ProviderAuthError as error:
        raise _translate(error) from error
    except httpx.HTTPError as error:
        raise _unavailable(error) from error
    return _to_session(response)


async def refresh(refresh_token: str) -> Session:
    client = await _client()
    try:
        response = await client.auth.refresh_session(refresh_token)
    except ProviderAuthError as error:
        raise SessionExpired("The session could not be refreshed.") from error
    except httpx.HTTPError as error:
        raise _unavailable(error) from error
    return _to_session(response)


async def sign_out(refresh_token: str, access_token: str = "") -> None:
    """Revoke this session only; other devices stay signed in.

    The access token is the optional half: it expires in an hour while the refresh
    cookie lives for thirty days, so by the time somebody clicks "Abmelden" it is
    usually gone or stale. Spending the refresh token for a fresh one is what makes
    logging out actually revoke the session rather than only clearing the cookies.
    """
    client = await _client()
    try:
        established = False
        if access_token:
            try:
                await client.auth.set_session(access_token, refresh_token)
                established = True
            except ProviderAuthError:
                pass  # Stale access token; fall through to spending the refresh one.
        if not established:
            # Buying a fresh access token also rotates the old refresh token away.
            await client.auth.refresh_session(refresh_token)
        await client.auth.sign_out({"scope": "local"})
    except ProviderAuthError as error:
        # An already-invalid token is not worth surfacing — the caller wanted to be
        # logged out and the cookies are cleared either way — but a token we failed
        # to revoke outlives the logout, so it is a warning, not an aside.
        logger.warning("Could not revoke the session on sign-out: %s", error)
    except httpx.HTTPError as error:
        logger.warning("Identity provider unreachable during sign-out: %s", error)


def build_oauth_redirect(provider: str, redirect_to: str) -> OAuthRedirect:
    """Authorize URL for the provider, with a freshly minted PKCE verifier.

    Built by hand rather than through `sign_in_with_oauth` because that method keeps
    the verifier in the client's storage, which does not survive to the callback
    request. The verifier travels in an HttpOnly cookie instead.

    PKCE alone would already stop an attacker's authorization code from being redeemed
    in somebody else's browser, since the verifier never leaves that browser. `state`
    is carried anyway because the callback is the one state-changing GET in the app —
    the request shape `SameSite=Lax` still sends cookies on — and OAuth 2.0 BCP asks
    for it.
    """
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    query = urlencode(
        {
            "provider": provider,
            "redirect_to": redirect_to,
            "code_challenge": challenge,
            # RFC 7636 spells the method in uppercase.
            "code_challenge_method": "S256",
        }
    )
    base = get_settings().supabase_url.rstrip("/")
    return OAuthRedirect(
        url=f"{base}/auth/v1/authorize?{query}",
        code_verifier=verifier,
    )


async def exchange_code(code: str, code_verifier: str) -> Session:
    client = await _client()
    try:
        response = await client.auth.exchange_code_for_session(
            {"auth_code": code, "code_verifier": code_verifier}
        )
    except ProviderAuthError as error:
        raise OAuthExchangeFailed("The sign-in could not be completed.") from error
    except httpx.HTTPError as error:
        raise _unavailable(error) from error
    return _to_session(response)
